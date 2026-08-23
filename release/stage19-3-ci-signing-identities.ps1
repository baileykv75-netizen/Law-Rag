param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        'CreatePrimary',
        'TrustPrimaryRoot',
        'TrustPrimaryPublisher',
        'CreateMismatch',
        'TrustMismatchRoot',
        'TrustMismatchPublisher',
        'Finalize',
        'Cleanup'
    )]
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

function Get-SourceSha {
    $SourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $SourceSha -notmatch '^[0-9a-f]{40}$') {
        throw 'Could not resolve exact source SHA for Stage 19.3 CI signing state.'
    }
    return $SourceSha
}

function Add-CertificateToStore {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [System.Security.Cryptography.X509Certificates.StoreName]$StoreName,
        [string]$Label
    )
    Write-Host "[Law-Rag][Stage19.3] START store add: $Label -> CurrentUser/$StoreName"
    $Store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        $StoreName,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $Store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $Store.Add($Certificate)
    }
    finally { $Store.Close() }
    Write-Host "[Law-Rag][Stage19.3] PASS store add: $Label -> CurrentUser/$StoreName"
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

function Read-State {
    if (-not (Test-Path $StatePath -PathType Leaf)) {
        throw "Stage 19.3 CI signing state is missing: $StatePath"
    }
    return (Get-Content $StatePath -Raw | ConvertFrom-Json)
}

function Write-RoleState {
    param([ValidateSet('primary', 'mismatch')][string]$Role, [string]$Thumbprint)

    $Primary = ''
    $Other = ''
    $CreatedAt = [DateTimeOffset]::UtcNow.ToString('o')
    if (Test-Path $StatePath -PathType Leaf) {
        $Existing = Read-State
        $Primary = Normalize-Thumbprint ([string]$Existing.primary_thumbprint)
        $Other = Normalize-Thumbprint ([string]$Existing.other_thumbprint)
        if ([string]$Existing.created_at) { $CreatedAt = [string]$Existing.created_at }
    }

    if ($Role -eq 'primary') { $Primary = Normalize-Thumbprint $Thumbprint }
    else { $Other = Normalize-Thumbprint $Thumbprint }

    $State = [ordered]@{
        schema_version = '1.0.0'
        source_commit_sha = Get-SourceSha
        primary_thumbprint = $Primary
        other_thumbprint = $Other
        created_at = $CreatedAt
        finalized = $false
    }
    $State | ConvertTo-Json -Depth 4 | Set-Content -Path $StatePath -Encoding UTF8
}

function Get-RoleThumbprint {
    param([ValidateSet('primary', 'mismatch')][string]$Role)
    $State = Read-State
    $Thumbprint = if ($Role -eq 'primary') {
        Normalize-Thumbprint ([string]$State.primary_thumbprint)
    } else {
        Normalize-Thumbprint ([string]$State.other_thumbprint)
    }
    if ($Thumbprint.Length -ne 40 -and $Thumbprint.Length -ne 64) {
        throw "Stage 19.3 $Role signer thumbprint is not available in partial state."
    }
    return $Thumbprint
}

function New-CiSignerInMyStore {
    param([string]$Subject, [ValidateSet('primary', 'mismatch')][string]$Role)

    Write-Host "[Law-Rag][Stage19.3] PHASE create $Role signer"
    $Rsa = $null
    $Transient = $null
    $Persisted = $null
    try {
        Write-Host "[Law-Rag][Stage19.3] START RSA key generation: $Role"
        $Rsa = [System.Security.Cryptography.RSA]::Create(2048)
        Write-Host "[Law-Rag][Stage19.3] PASS RSA key generation: $Role"

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

        Write-Host "[Law-Rag][Stage19.3] START self-signed certificate creation: $Role"
        $Transient = $Request.CreateSelfSigned(
            [DateTimeOffset]::UtcNow.AddMinutes(-5),
            [DateTimeOffset]::UtcNow.AddDays(2)
        )
        Write-Host "[Law-Rag][Stage19.3] PASS self-signed certificate creation: $Role"

        $Password = [Guid]::NewGuid().ToString('N')
        $Pfx = $Transient.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Pfx, $Password)
        $Flags = (
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::UserKeySet -bor
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
        )
        Write-Host "[Law-Rag][Stage19.3] START PFX private-key persistence: $Role"
        $Persisted = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($Pfx, $Password, $Flags)
        if (-not $Persisted.HasPrivateKey) { throw "Persisted CI signer lost its private key before My-store insertion: $Role" }
        $Thumbprint = Normalize-Thumbprint $Persisted.Thumbprint
        if ($Thumbprint.Length -ne 40 -and $Thumbprint.Length -ne 64) { throw "Unexpected CI signer thumbprint: $Role" }
        Write-Host "[Law-Rag][Stage19.3] PASS PFX private-key persistence: $Role ($Thumbprint)"

        # Journal before the first certificate-store mutation so Cleanup survives a killed/failed setup step.
        Record-CleanupThumbprint -Thumbprint $Thumbprint
        Add-CertificateToStore -Certificate $Persisted -StoreName My -Label "$Role private signer"

        $Stored = Get-Item "Cert:\CurrentUser\My\$Thumbprint" -ErrorAction Stop
        if (-not $Stored.HasPrivateKey) { throw "Stored CI signer has no private key: $Role" }
        Write-RoleState -Role $Role -Thumbprint $Thumbprint
        Write-Host "[Law-Rag][Stage19.3] PHASE create $Role signer PASS ($Thumbprint)"
    }
    finally {
        if ($null -ne $Persisted) { $Persisted.Dispose() }
        if ($null -ne $Transient) { $Transient.Dispose() }
        if ($null -ne $Rsa) { $Rsa.Dispose() }
    }
}

function Trust-RoleSigner {
    param(
        [ValidateSet('primary', 'mismatch')][string]$Role,
        [ValidateSet('Root', 'TrustedPublisher')][string]$TargetStore
    )

    Write-Host "[Law-Rag][Stage19.3] PHASE trust $Role signer in $TargetStore"
    $Thumbprint = Get-RoleThumbprint -Role $Role
    $Signer = Get-Item "Cert:\CurrentUser\My\$Thumbprint" -ErrorAction Stop
    if (-not $Signer.HasPrivateKey) { throw "CI $Role signer in My store has no private key." }

    $PublicCertificate = $null
    try {
        $PublicBytes = $Signer.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
        $PublicCertificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($PublicBytes)
        if ($PublicCertificate.HasPrivateKey) { throw "Public trust-store clone unexpectedly retained a private key: $Role" }
        Add-CertificateToStore -Certificate $PublicCertificate -StoreName $TargetStore -Label "$Role public certificate"
    }
    finally {
        if ($null -ne $PublicCertificate) { $PublicCertificate.Dispose() }
    }
    Write-Host "[Law-Rag][Stage19.3] PHASE trust $Role signer in $TargetStore PASS"
}

function Finalize-State {
    Write-Host '[Law-Rag][Stage19.3] PHASE finalize signing state'
    $State = Read-State
    $Primary = Normalize-Thumbprint ([string]$State.primary_thumbprint)
    $Other = Normalize-Thumbprint ([string]$State.other_thumbprint)
    if (($Primary.Length -ne 40 -and $Primary.Length -ne 64) -or ($Other.Length -ne 40 -and $Other.Length -ne 64)) {
        throw 'Both Stage 19.3 CI signer thumbprints must exist before finalization.'
    }
    if ($Primary -eq $Other) { throw 'CI signing identities unexpectedly share a thumbprint.' }

    foreach ($Pair in @(@('primary', $Primary), @('mismatch', $Other))) {
        $Label = $Pair[0]
        $Thumbprint = $Pair[1]
        $Stored = Get-Item "Cert:\CurrentUser\My\$Thumbprint" -ErrorAction Stop
        if (-not $Stored.HasPrivateKey) { throw "Finalization found no private key for $Label signer." }
    }

    $FinalState = [ordered]@{
        schema_version = '1.0.0'
        source_commit_sha = Get-SourceSha
        primary_thumbprint = $Primary
        other_thumbprint = $Other
        created_at = [string]$State.created_at
        finalized = $true
        finalized_at = [DateTimeOffset]::UtcNow.ToString('o')
    }
    $FinalState | ConvertTo-Json -Depth 4 | Set-Content -Path $StatePath -Encoding UTF8
    Write-Host '[Law-Rag][Stage19.3] PHASE finalize signing state PASS'
}

function Invoke-Cleanup {
    Write-Host '[Law-Rag][Stage19.3] PHASE Cleanup'
    $Thumbprints = [System.Collections.Generic.List[string]]::new()

    try {
        foreach ($Thumbprint in (Read-CleanupThumbprints)) {
            if ($Thumbprint -and -not $Thumbprints.Contains($Thumbprint)) { $Thumbprints.Add($Thumbprint) }
        }
    }
    catch {
        Write-Warning "Could not parse Stage 19.3 cleanup journal: $($_.Exception.Message)"
    }

    if (Test-Path $StatePath -PathType Leaf) {
        try {
            $State = Read-State
            foreach ($Raw in @($State.primary_thumbprint, $State.other_thumbprint)) {
                $Thumbprint = Normalize-Thumbprint ([string]$Raw)
                if ($Thumbprint -and -not $Thumbprints.Contains($Thumbprint)) { $Thumbprints.Add($Thumbprint) }
            }
        }
        catch {
            Write-Warning "Could not parse Stage 19.3 state during cleanup: $($_.Exception.Message)"
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
    'CreatePrimary' {
        if (Test-Path $StatePath -PathType Leaf) { throw "Refusing to start primary signer over stale Stage 19.3 state: $StatePath" }
        if (Test-Path $CleanupJournalPath -PathType Leaf) { throw "Refusing to start primary signer over stale cleanup journal: $CleanupJournalPath" }
        New-CiSignerInMyStore -Subject 'CN=Law-Rag Stage 19.3 CI Primary ONLY' -Role primary
    }
    'TrustPrimaryRoot' { Trust-RoleSigner -Role primary -TargetStore Root }
    'TrustPrimaryPublisher' { Trust-RoleSigner -Role primary -TargetStore TrustedPublisher }
    'CreateMismatch' {
        $ExistingOther = ''
        if (Test-Path $StatePath -PathType Leaf) {
            $ExistingOther = Normalize-Thumbprint ([string](Read-State).other_thumbprint)
        }
        if ($ExistingOther) { throw 'Refusing to overwrite an existing Stage 19.3 mismatch signer.' }
        New-CiSignerInMyStore -Subject 'CN=Law-Rag Stage 19.3 CI Mismatch ONLY' -Role mismatch
    }
    'TrustMismatchRoot' { Trust-RoleSigner -Role mismatch -TargetStore Root }
    'TrustMismatchPublisher' { Trust-RoleSigner -Role mismatch -TargetStore TrustedPublisher }
    'Finalize' { Finalize-State }
    'Cleanup' { Invoke-Cleanup }
}
