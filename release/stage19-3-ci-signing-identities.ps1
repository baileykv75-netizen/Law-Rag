param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Setup', 'Cleanup')]
    [string]$Phase,
    [string]$StatePath = (Join-Path $PSScriptRoot '.stage19-3-ci-state.json'),
    [string]$CleanupJournalPath = (Join-Path $PSScriptRoot '.stage19-3-ci-cleanup.json')
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Stage 19.3 CI signing identity setup is Windows-only.' }

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Normalize-Thumbprint {
    param([string]$Value)
    if (-not $Value) { return '' }
    return (($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

function Add-CertificateToStore {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [System.Security.Cryptography.X509Certificates.StoreName]$StoreName,
        [string]$Label
    )
    Write-Host "[Law-Rag][Stage19.3] START trust-store add: $Label -> CurrentUser/$StoreName"
    $Store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        $StoreName,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $Store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $Store.Add($Certificate)
    }
    finally { $Store.Close() }
    Write-Host "[Law-Rag][Stage19.3] PASS trust-store add: $Label -> CurrentUser/$StoreName"
}

function Remove-CertificateFromStore {
    param([string]$Thumbprint, [System.Security.Cryptography.X509Certificates.StoreName]$StoreName)
    $Normalized = Normalize-Thumbprint $Thumbprint
    if (-not $Normalized) { return }
    $Store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        $StoreName,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $Store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $Matches = @($Store.Certificates | Where-Object { (Normalize-Thumbprint $_.Thumbprint) -eq $Normalized })
        foreach ($Certificate in $Matches) { $Store.Remove($Certificate) }
    }
    finally { $Store.Close() }
}

function Read-CleanupThumbprints {
    if (-not (Test-Path $CleanupJournalPath -PathType Leaf)) { return @() }
    $Journal = Get-Content $CleanupJournalPath -Raw | ConvertFrom-Json
    return @($Journal.thumbprints | ForEach-Object { Normalize-Thumbprint ([string]$_) } | Where-Object { $_ })
}

function Record-CleanupThumbprint {
    param([string]$Thumbprint)
    $Normalized = Normalize-Thumbprint $Thumbprint
    if (-not $Normalized) { throw 'Refusing to journal an empty CI signing thumbprint.' }
    $Existing = @(Read-CleanupThumbprints)
    $Thumbprints = @($Existing + @($Normalized) | Sort-Object -Unique)
    $Journal = [ordered]@{
        schema_version = '1.0.0'
        thumbprints = $Thumbprints
        updated_at = [DateTimeOffset]::UtcNow.ToString('o')
    }
    $Journal | ConvertTo-Json -Depth 4 | Set-Content -Path $CleanupJournalPath -Encoding UTF8
    Write-Host "[Law-Rag][Stage19.3] Cleanup journal recorded signer $Normalized"
}

function New-CiSigner {
    param([string]$Subject, [string]$Label)

    Write-Host "[Law-Rag][Stage19.3] START create signer: $Label"
    $Rsa = $null
    $Transient = $null
    $Persisted = $null
    $PublicCertificate = $null
    try {
        Write-Host "[Law-Rag][Stage19.3] START RSA key generation: $Label"
        $Rsa = [System.Security.Cryptography.RSA]::Create(2048)
        Write-Host "[Law-Rag][Stage19.3] PASS RSA key generation: $Label"

        $Request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
            $Subject,
            $Rsa,
            [System.Security.Cryptography.HashAlgorithmName]::SHA256,
            [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
        )
        $Request.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
                [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature,
                $true
            )
        )
        $Eku = [System.Security.Cryptography.OidCollection]::new()
        [void]$Eku.Add([System.Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.3', 'Code Signing'))
        $Request.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($Eku, $true)
        )

        Write-Host "[Law-Rag][Stage19.3] START self-signed certificate creation: $Label"
        $Transient = $Request.CreateSelfSigned(
            [DateTimeOffset]::UtcNow.AddMinutes(-5),
            [DateTimeOffset]::UtcNow.AddDays(2)
        )
        Write-Host "[Law-Rag][Stage19.3] PASS self-signed certificate creation: $Label"

        $Password = [Guid]::NewGuid().ToString('N')
        $Pfx = $Transient.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Pfx, $Password)
        $Flags = (
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::UserKeySet -bor
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
        )
        Write-Host "[Law-Rag][Stage19.3] START PFX private-key persistence: $Label"
        $Persisted = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($Pfx, $Password, $Flags)
        if (-not $Persisted.HasPrivateKey) { throw "Persisted CI signer lost its private key before store insertion: $Label" }
        $Thumbprint = Normalize-Thumbprint $Persisted.Thumbprint
        if ($Thumbprint.Length -ne 40 -and $Thumbprint.Length -ne 64) { throw "Unexpected CI signer thumbprint: $Label" }
        Write-Host "[Law-Rag][Stage19.3] PASS PFX private-key persistence: $Label ($Thumbprint)"

        # Journal before the first store mutation so Cleanup can recover even if Setup dies mid-way.
        Record-CleanupThumbprint -Thumbprint $Thumbprint

        # Keep private key material only in CurrentUser/My. Trust stores receive a public-only clone.
        Add-CertificateToStore -Certificate $Persisted -StoreName My -Label "$Label private signer"
        $PublicBytes = $Persisted.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
        $PublicCertificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($PublicBytes)
        if ($PublicCertificate.HasPrivateKey) { throw "Public trust-store clone unexpectedly retained a private key: $Label" }
        Add-CertificateToStore -Certificate $PublicCertificate -StoreName Root -Label "$Label public trust anchor"
        Add-CertificateToStore -Certificate $PublicCertificate -StoreName TrustedPublisher -Label "$Label public publisher"

        $Stored = Get-Item "Cert:\CurrentUser\My\$Thumbprint" -ErrorAction Stop
        if (-not $Stored.HasPrivateKey) { throw "Stored CI signer has no private key: $Label" }
        Write-Host "[Law-Rag][Stage19.3] PASS create signer: $Label ($Thumbprint)"
        return $Thumbprint
    }
    finally {
        if ($null -ne $PublicCertificate) { $PublicCertificate.Dispose() }
        if ($null -ne $Persisted) { $Persisted.Dispose() }
        if ($null -ne $Transient) { $Transient.Dispose() }
        if ($null -ne $Rsa) { $Rsa.Dispose() }
    }
}

function Invoke-Cleanup {
    Write-Host '[Law-Rag][Stage19.3] PHASE Cleanup'
    $Thumbprints = [System.Collections.Generic.List[string]]::new()

    foreach ($Thumbprint in (Read-CleanupThumbprints)) {
        if ($Thumbprint -and -not $Thumbprints.Contains($Thumbprint)) { $Thumbprints.Add($Thumbprint) }
    }

    if (Test-Path $StatePath -PathType Leaf) {
        try {
            $State = Get-Content $StatePath -Raw | ConvertFrom-Json
            foreach ($Raw in @($State.primary_thumbprint, $State.other_thumbprint)) {
                $Thumbprint = Normalize-Thumbprint ([string]$Raw)
                if ($Thumbprint -and -not $Thumbprints.Contains($Thumbprint)) { $Thumbprints.Add($Thumbprint) }
            }
        }
        catch {
            Write-Warning "Could not parse final Stage 19.3 state during cleanup: $($_.Exception.Message)"
        }
    }

    $Failures = [System.Collections.Generic.List[string]]::new()
    foreach ($Thumbprint in $Thumbprints) {
        foreach ($StoreName in @('My', 'Root', 'TrustedPublisher')) {
            try {
                Write-Host "[Law-Rag][Stage19.3] START cleanup signer $Thumbprint from CurrentUser/$StoreName"
                Remove-CertificateFromStore -Thumbprint $Thumbprint -StoreName $StoreName
                Write-Host "[Law-Rag][Stage19.3] PASS cleanup signer $Thumbprint from CurrentUser/$StoreName"
            }
            catch {
                $Failures.Add("${Thumbprint}@${StoreName}: $($_.Exception.Message)")
            }
        }
    }

    Remove-Item $StatePath -Force -ErrorAction SilentlyContinue
    Remove-Item $CleanupJournalPath -Force -ErrorAction SilentlyContinue

    if ($Failures.Count -gt 0) {
        throw "Stage 19.3 CI signing cleanup was incomplete: $($Failures -join '; ')"
    }
    Write-Host '[Law-Rag][Stage19.3] PHASE Cleanup PASS'
}

switch ($Phase) {
    'Setup' {
        Write-Host '[Law-Rag][Stage19.3] PHASE Setup'
        if (Test-Path $StatePath -PathType Leaf) { throw "Refusing to overwrite stale Stage 19.3 CI state: $StatePath" }
        if (Test-Path $CleanupJournalPath -PathType Leaf) { throw "Refusing to overwrite stale Stage 19.3 cleanup journal: $CleanupJournalPath" }

        $PrimaryThumbprint = New-CiSigner -Subject 'CN=Law-Rag Stage 19.3 CI Primary ONLY' -Label 'primary'
        $OtherThumbprint = New-CiSigner -Subject 'CN=Law-Rag Stage 19.3 CI Mismatch ONLY' -Label 'mismatch'
        if ($PrimaryThumbprint -eq $OtherThumbprint) { throw 'CI signing identities unexpectedly share a thumbprint.' }

        $SourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
        if ($LASTEXITCODE -ne 0 -or $SourceSha -notmatch '^[0-9a-f]{40}$') { throw 'Could not resolve exact source SHA for Stage 19.3 CI signing state.' }
        $State = [ordered]@{
            schema_version = '1.0.0'
            source_commit_sha = $SourceSha
            primary_thumbprint = $PrimaryThumbprint
            other_thumbprint = $OtherThumbprint
            created_at = [DateTimeOffset]::UtcNow.ToString('o')
        }
        $State | ConvertTo-Json -Depth 4 | Set-Content -Path $StatePath -Encoding UTF8
        Write-Host '[Law-Rag][Stage19.3] PHASE Setup PASS'
    }
    'Cleanup' {
        Invoke-Cleanup
    }
}
