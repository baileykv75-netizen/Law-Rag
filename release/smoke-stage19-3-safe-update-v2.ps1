param(
    [string]$InstallerPath = (Join-Path $PSScriptRoot "installer-dist\Law-Rag-0.8.0-rc2-windows-x64-setup.exe"),
    [string]$OutputDir = (Join-Path $PSScriptRoot "update-dist")
)

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Stage 19.3 safe-update smoke is Windows-only." }

$InstallerPath = (Resolve-Path $InstallerPath).Path
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path

function Add-CertificateToStore {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [System.Security.Cryptography.X509Certificates.StoreName]$StoreName
    )
    $Store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        $StoreName,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $Store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $Store.Add($Certificate)
    }
    finally {
        $Store.Close()
    }
}

function New-DotNetCiSigner {
    param([string]$Subject)

    $Rsa = [System.Security.Cryptography.RSA]::Create(2048)
    $Transient = $null
    try {
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
        [void]$Eku.Add([System.Security.Cryptography.Oid]::new("1.3.6.1.5.5.7.3.3", "Code Signing"))
        $Request.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($Eku, $true)
        )

        $Transient = $Request.CreateSelfSigned(
            [DateTimeOffset]::UtcNow.AddMinutes(-5),
            [DateTimeOffset]::UtcNow.AddDays(2)
        )
        $Password = [Guid]::NewGuid().ToString("N")
        $Pfx = $Transient.Export(
            [System.Security.Cryptography.X509Certificates.X509ContentType]::Pfx,
            $Password
        )
        $Flags = (
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::UserKeySet -bor
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
        )
        $Persisted = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
            $Pfx,
            $Password,
            $Flags
        )
        Add-CertificateToStore -Certificate $Persisted -StoreName My
        Add-CertificateToStore -Certificate $Persisted -StoreName Root
        Add-CertificateToStore -Certificate $Persisted -StoreName TrustedPublisher

        $Stored = Get-Item "Cert:\CurrentUser\My\$($Persisted.Thumbprint)" -ErrorAction Stop
        if (-not $Stored.HasPrivateKey) { throw "Persisted CI signer lost its private key." }
        return $Stored
    }
    finally {
        if ($null -ne $Transient) { $Transient.Dispose() }
        $Rsa.Dispose()
    }
}

function Sign-FileChecked {
    param(
        [string]$Path,
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [string]$Label
    )
    Write-Host "[Law-Rag][Stage19.3] Signing $Label"
    $Signed = Set-AuthenticodeSignature -FilePath $Path -Certificate $Certificate -HashAlgorithm SHA256
    if ($Signed.Status -ne 'Valid') {
        throw "$Label signature did not validate: $($Signed.Status) $($Signed.StatusMessage)"
    }
}

function Invoke-ExpectedRefusal {
    param([scriptblock]$Action, [string]$Label)
    $Refused = $false
    try { & $Action }
    catch {
        $Refused = $true
        Write-Host "[Law-Rag][Stage19.3] Expected $Label refusal: $($_.Exception.Message)"
    }
    if (-not $Refused) { throw "Stage 19.3 negative case unexpectedly passed: $Label" }
}

function Read-Evidence {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Expected evidence was not written: $Path" }
    return (Get-Content $Path -Raw | ConvertFrom-Json)
}

function New-SignedManifest {
    param(
        [string]$Artifact,
        [string]$Version,
        [string]$Url,
        [string]$SignerThumbprint,
        [string]$Directory
    )
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $Manifest = Join-Path $Directory 'manifest.json'
    $Cms = Join-Path $Directory 'manifest.p7s'
    ./release/new-stage19-3-update-manifest.ps1 `
        -InstallerPath $Artifact `
        -CandidateVersion $Version `
        -ArtifactUrl $Url `
        -SignerThumbprint $SignerThumbprint `
        -ManifestPath $Manifest `
        -SignaturePath $Cms
    return [pscustomobject]@{ Manifest = $Manifest; Cms = $Cms }
}

$Primary = $null
$Other = $null
try {
    Write-Host "[Law-Rag][Stage19.3] Creating .NET CI-only signing identities"
    $Primary = New-DotNetCiSigner -Subject 'CN=Law-Rag Stage 19.3 CI Primary ONLY'
    $Other = New-DotNetCiSigner -Subject 'CN=Law-Rag Stage 19.3 CI Mismatch ONLY'
    $PrimaryThumbprint = $Primary.Thumbprint.ToUpperInvariant()
    $OtherThumbprint = $Other.Thumbprint.ToUpperInvariant()
    if ($PrimaryThumbprint -eq $OtherThumbprint) { throw "CI signing identities unexpectedly share a thumbprint." }
    $env:LAW_RAG_RELEASE_SIGNER_THUMBPRINT = $PrimaryThumbprint

    # Strong release-artifact path: the real installer must be accepted only when
    # signed by the expected signer, and byte tampering must invalidate both hash
    # and Authenticode. These are the only negative checks that need the large
    # installer bytes.
    Write-Host "[Law-Rag][Stage19.3] Validating real installer positive path"
    $Candidate = Join-Path $OutputDir 'Law-Rag-0.8.0-rc3-windows-x64-setup.exe'
    Copy-Item $InstallerPath $Candidate -Force
    Sign-FileChecked -Path $Candidate -Certificate $Primary -Label 'real update installer'

    $ReleaseManifest = New-SignedManifest `
        -Artifact $Candidate `
        -Version '0.8.0-rc3' `
        -Url 'https://updates.example.invalid/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -Directory (Join-Path $OutputDir 'release-positive')
    $PositiveEvidence = Join-Path $OutputDir 'STAGE19-3-POSITIVE.json'
    ./release/verify-stage19-3-update.ps1 `
        -ManifestPath $ReleaseManifest.Manifest `
        -ManifestSignaturePath $ReleaseManifest.Cms `
        -InstallerPath $Candidate `
        -CurrentVersion '0.8.0-rc2' `
        -ExpectedSignerThumbprint $PrimaryThumbprint `
        -EvidencePath $PositiveEvidence `
        -RequireEligible
    $Positive = Read-Evidence $PositiveEvidence
    if (-not $Positive.eligible -or $Positive.decision -ne 'UPDATE_ELIGIBLE') { throw "Positive signed candidate was not eligible." }
    if ($Positive.manifest.cms_status -ne 'VALID') { throw "Positive manifest CMS signature did not validate." }
    if ($Positive.artifact.authenticode.status -ne 'Valid') { throw "Positive installer Authenticode signature did not validate." }
    if ($Positive.provider_network_uat_executed -or $Positive.private_expert_evidence_executed) { throw "Stage 19.3 crossed a forbidden external-evidence boundary." }

    Write-Host "[Law-Rag][Stage19.3] Validating real installer tamper rejection"
    $TamperedDir = Join-Path $OutputDir 'tampered-artifact'
    New-Item -ItemType Directory -Path $TamperedDir -Force | Out-Null
    $TamperedCandidate = Join-Path $TamperedDir 'Law-Rag-0.8.0-rc3-windows-x64-setup.exe'
    Copy-Item $Candidate $TamperedCandidate -Force
    $Stream = [IO.File]::Open($TamperedCandidate, [IO.FileMode]::Append, [IO.FileAccess]::Write)
    try { $Stream.WriteByte(0x00) } finally { $Stream.Dispose() }
    $TamperedEvidence = Join-Path $OutputDir 'STAGE19-3-ARTIFACT-TAMPER.json'
    Invoke-ExpectedRefusal -Label 'installer-tamper' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $ReleaseManifest.Manifest -ManifestSignaturePath $ReleaseManifest.Cms -InstallerPath $TamperedCandidate -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $TamperedEvidence -RequireEligible
    }
    $Tampered = Read-Evidence $TamperedEvidence
    if ($Tampered.rejection_reasons -notcontains 'ARTIFACT_SHA256_MISMATCH') { throw "Installer tamper did not report SHA-256 mismatch." }
    if ($Tampered.rejection_reasons -notcontains 'INSTALLER_AUTHENTICODE_NOT_VALID') { throw "Installer tamper did not invalidate Authenticode." }

    # Logic-only negative cases use a small signed Windows PE fixture. They still
    # execute the exact production manifest generator and verifier, but avoid
    # repeatedly hashing the large OCR-bearing release installer for conditions
    # unrelated to artifact size.
    Write-Host "[Law-Rag][Stage19.3] Preparing small signed fixture for logic-only negative cases"
    $FixtureSource = Join-Path $env:SystemRoot 'System32\where.exe'
    if (-not (Test-Path $FixtureSource -PathType Leaf)) { throw "Windows signed-fixture source is unavailable: $FixtureSource" }
    $Fixture = Join-Path $OutputDir 'Law-Rag-stage19-3-fixture.exe'
    Copy-Item $FixtureSource $Fixture -Force
    Sign-FileChecked -Path $Fixture -Certificate $Primary -Label 'primary negative-case fixture'
    $FixtureManifest = New-SignedManifest `
        -Artifact $Fixture `
        -Version '0.8.0-rc3' `
        -Url 'https://updates.example.invalid/Law-Rag-stage19-3-fixture.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -Directory (Join-Path $OutputDir 'fixture-positive')

    Write-Host "[Law-Rag][Stage19.3] Validating manifest tamper rejection"
    $TamperedManifest = Join-Path $OutputDir 'UPDATE-MANIFEST-TAMPERED.json'
    Copy-Item $FixtureManifest.Manifest $TamperedManifest -Force
    [IO.File]::AppendAllText($TamperedManifest, ' ')
    $ManifestTamperEvidence = Join-Path $OutputDir 'STAGE19-3-MANIFEST-TAMPER.json'
    Invoke-ExpectedRefusal -Label 'manifest-tamper' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $TamperedManifest -ManifestSignaturePath $FixtureManifest.Cms -InstallerPath $Fixture -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $ManifestTamperEvidence -RequireEligible
    }
    if ((Read-Evidence $ManifestTamperEvidence).rejection_reasons -notcontains 'MANIFEST_CMS_INVALID') { throw "Manifest tamper did not fail at the CMS boundary." }

    Write-Host "[Law-Rag][Stage19.3] Validating signer mismatch rejection"
    $MismatchFixture = Join-Path $OutputDir 'Law-Rag-stage19-3-mismatch.exe'
    Copy-Item $FixtureSource $MismatchFixture -Force
    Sign-FileChecked -Path $MismatchFixture -Certificate $Other -Label 'mismatched-signer fixture'
    $MismatchManifest = New-SignedManifest `
        -Artifact $MismatchFixture `
        -Version '0.8.0-rc3' `
        -Url 'https://updates.example.invalid/Law-Rag-stage19-3-mismatch.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -Directory (Join-Path $OutputDir 'signer-mismatch')
    $MismatchEvidence = Join-Path $OutputDir 'STAGE19-3-SIGNER-MISMATCH.json'
    Invoke-ExpectedRefusal -Label 'signer-mismatch' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $MismatchManifest.Manifest -ManifestSignaturePath $MismatchManifest.Cms -InstallerPath $MismatchFixture -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $MismatchEvidence -RequireEligible
    }
    if ((Read-Evidence $MismatchEvidence).rejection_reasons -notcontains 'INSTALLER_SIGNER_MISMATCH') { throw "Signer mismatch was not detected." }

    Write-Host "[Law-Rag][Stage19.3] Validating version monotonicity rejection"
    $SameManifest = New-SignedManifest `
        -Artifact $Fixture `
        -Version '0.8.0-rc2' `
        -Url 'https://updates.example.invalid/Law-Rag-stage19-3-fixture.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -Directory (Join-Path $OutputDir 'same-version')
    $SameEvidence = Join-Path $OutputDir 'STAGE19-3-SAME-VERSION.json'
    Invoke-ExpectedRefusal -Label 'same-version' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $SameManifest.Manifest -ManifestSignaturePath $SameManifest.Cms -InstallerPath $Fixture -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $SameEvidence -RequireEligible
    }
    if ((Read-Evidence $SameEvidence).rejection_reasons -notcontains 'CANDIDATE_VERSION_NOT_NEWER') { throw "Same-version candidate was not rejected." }

    Write-Host "[Law-Rag][Stage19.3] Validating HTTPS boundary rejection"
    $HttpManifest = New-SignedManifest `
        -Artifact $Fixture `
        -Version '0.8.0-rc3' `
        -Url 'http://updates.example.invalid/Law-Rag-stage19-3-fixture.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -Directory (Join-Path $OutputDir 'http-url')
    $HttpEvidence = Join-Path $OutputDir 'STAGE19-3-HTTP-URL.json'
    Invoke-ExpectedRefusal -Label 'http-url' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $HttpManifest.Manifest -ManifestSignaturePath $HttpManifest.Cms -InstallerPath $Fixture -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $HttpEvidence -RequireEligible
    }
    if ((Read-Evidence $HttpEvidence).rejection_reasons -notcontains 'ARTIFACT_URL_NOT_SAFE_HTTPS') { throw "HTTP candidate was not rejected." }

    Write-Host "[Law-Rag] Stage 19.3 safe-update trust chain PASS"
    Write-Host "[Law-Rag] real installer positive + byte-tamper paths PASS"
    Write-Host "[Law-Rag] manifest/signer/version/HTTPS negative paths PASS"
    Write-Host "[Law-Rag] provider/network calls: 0"
}
finally {
    Remove-Item Env:LAW_RAG_RELEASE_SIGNER_THUMBPRINT -ErrorAction SilentlyContinue
    foreach ($Certificate in @($Primary, $Other)) {
        if ($null -eq $Certificate) { continue }
        $Thumbprint = $Certificate.Thumbprint
        foreach ($StoreName in @('My', 'Root', 'TrustedPublisher')) {
            Remove-Item "Cert:\CurrentUser\$StoreName\$Thumbprint" -Force -ErrorAction SilentlyContinue
        }
    }
}
