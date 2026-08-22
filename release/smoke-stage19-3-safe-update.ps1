param(
    [string]$InstallerPath = (Join-Path $PSScriptRoot "installer-dist\Law-Rag-0.8.0-rc2-windows-x64-setup.exe"),
    [string]$OutputDir = (Join-Path $PSScriptRoot "update-dist")
)

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "Stage 19.3 safe-update smoke is Windows-only."
}

$InstallerPath = (Resolve-Path $InstallerPath).Path
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path

function Trust-CertificateForCurrentUser {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate)

    foreach ($StoreName in @(
        [System.Security.Cryptography.X509Certificates.StoreName]::Root,
        [System.Security.Cryptography.X509Certificates.StoreName]::TrustedPublisher
    )) {
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
}

function New-CiSigner {
    param([string]$Subject)

    $Certificate = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $Subject `
        -CertStoreLocation 'Cert:\CurrentUser\My' `
        -HashAlgorithm SHA256 `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -KeyExportPolicy NonExportable `
        -NotAfter (Get-Date).AddDays(2)
    Trust-CertificateForCurrentUser -Certificate $Certificate
    return $Certificate
}

function Invoke-ExpectedRefusal {
    param(
        [scriptblock]$Action,
        [string]$Label
    )
    $Refused = $false
    try {
        & $Action
    }
    catch {
        $Refused = $true
        Write-Host "[Law-Rag][Stage19.3] Expected $Label refusal: $($_.Exception.Message)"
    }
    if (-not $Refused) {
        throw "Stage 19.3 negative case unexpectedly passed: $Label"
    }
}

function Read-Evidence {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Expected evidence was not written: $Path" }
    return (Get-Content $Path -Raw | ConvertFrom-Json)
}

$Primary = $null
$Other = $null
try {
    $Primary = New-CiSigner -Subject 'CN=Law-Rag Stage 19.3 CI Primary ONLY'
    $Other = New-CiSigner -Subject 'CN=Law-Rag Stage 19.3 CI Mismatch ONLY'
    $PrimaryThumbprint = $Primary.Thumbprint.ToUpperInvariant()
    $OtherThumbprint = $Other.Thumbprint.ToUpperInvariant()
    if ($PrimaryThumbprint -eq $OtherThumbprint) { throw "CI signing identities unexpectedly share a thumbprint." }

    $env:LAW_RAG_RELEASE_SIGNER_THUMBPRINT = $PrimaryThumbprint
    Write-Host "[Law-Rag][Stage19.3] Ephemeral CI-only signers ready. No private key leaves CurrentUser certificate storage."

    $Candidate = Join-Path $OutputDir 'Law-Rag-0.8.0-rc3-windows-x64-setup.exe'
    Copy-Item $InstallerPath $Candidate -Force
    $Signed = Set-AuthenticodeSignature -FilePath $Candidate -Certificate $Primary -HashAlgorithm SHA256
    if ($Signed.Status -ne 'Valid') {
        throw "Positive CI installer signature did not validate: $($Signed.Status) $($Signed.StatusMessage)"
    }

    $Manifest = Join-Path $OutputDir 'UPDATE-MANIFEST.json'
    $ManifestSignature = Join-Path $OutputDir 'UPDATE-MANIFEST.p7s'
    ./release/new-stage19-3-update-manifest.ps1 `
        -InstallerPath $Candidate `
        -CandidateVersion '0.8.0-rc3' `
        -ArtifactUrl 'https://updates.example.invalid/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -ManifestPath $Manifest `
        -SignaturePath $ManifestSignature

    $PositiveEvidence = Join-Path $OutputDir 'STAGE19-3-POSITIVE.json'
    ./release/verify-stage19-3-update.ps1 `
        -ManifestPath $Manifest `
        -ManifestSignaturePath $ManifestSignature `
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

    $TamperedManifest = Join-Path $OutputDir 'UPDATE-MANIFEST-TAMPERED.json'
    Copy-Item $Manifest $TamperedManifest -Force
    [IO.File]::AppendAllText($TamperedManifest, ' ')
    $TamperedManifestEvidence = Join-Path $OutputDir 'STAGE19-3-MANIFEST-TAMPER.json'
    Invoke-ExpectedRefusal -Label 'manifest-tamper' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $TamperedManifest -ManifestSignaturePath $ManifestSignature -InstallerPath $Candidate -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $TamperedManifestEvidence -RequireEligible
    }
    $TamperedManifestResult = Read-Evidence $TamperedManifestEvidence
    if ($TamperedManifestResult.rejection_reasons -notcontains 'MANIFEST_CMS_INVALID') { throw "Manifest tamper did not fail at the CMS boundary." }

    $TamperedDir = Join-Path $OutputDir 'tampered-artifact'
    New-Item -ItemType Directory -Path $TamperedDir -Force | Out-Null
    $TamperedCandidate = Join-Path $TamperedDir 'Law-Rag-0.8.0-rc3-windows-x64-setup.exe'
    Copy-Item $Candidate $TamperedCandidate -Force
    $Stream = [IO.File]::Open($TamperedCandidate, [IO.FileMode]::Append, [IO.FileAccess]::Write)
    try { $Stream.WriteByte(0x00) } finally { $Stream.Dispose() }
    $TamperedArtifactEvidence = Join-Path $OutputDir 'STAGE19-3-ARTIFACT-TAMPER.json'
    Invoke-ExpectedRefusal -Label 'installer-tamper' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $Manifest -ManifestSignaturePath $ManifestSignature -InstallerPath $TamperedCandidate -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $TamperedArtifactEvidence -RequireEligible
    }
    $TamperedArtifactResult = Read-Evidence $TamperedArtifactEvidence
    if ($TamperedArtifactResult.rejection_reasons -notcontains 'ARTIFACT_SHA256_MISMATCH') { throw "Installer tamper did not report SHA-256 mismatch." }
    if ($TamperedArtifactResult.rejection_reasons -notcontains 'INSTALLER_AUTHENTICODE_NOT_VALID') { throw "Installer tamper did not invalidate Authenticode." }

    $MismatchDir = Join-Path $OutputDir 'signer-mismatch'
    New-Item -ItemType Directory -Path $MismatchDir -Force | Out-Null
    $MismatchCandidate = Join-Path $MismatchDir 'Law-Rag-0.8.0-rc3-windows-x64-setup.exe'
    Copy-Item $InstallerPath $MismatchCandidate -Force
    $MismatchSigned = Set-AuthenticodeSignature -FilePath $MismatchCandidate -Certificate $Other -HashAlgorithm SHA256
    if ($MismatchSigned.Status -ne 'Valid') { throw "Mismatch CI installer signature did not validate: $($MismatchSigned.Status)" }
    $MismatchManifest = Join-Path $MismatchDir 'manifest.json'
    $MismatchCms = Join-Path $MismatchDir 'manifest.p7s'
    ./release/new-stage19-3-update-manifest.ps1 -InstallerPath $MismatchCandidate -CandidateVersion '0.8.0-rc3' -ArtifactUrl 'https://updates.example.invalid/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' -SignerThumbprint $PrimaryThumbprint -ManifestPath $MismatchManifest -SignaturePath $MismatchCms
    $MismatchEvidence = Join-Path $OutputDir 'STAGE19-3-SIGNER-MISMATCH.json'
    Invoke-ExpectedRefusal -Label 'signer-mismatch' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $MismatchManifest -ManifestSignaturePath $MismatchCms -InstallerPath $MismatchCandidate -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $MismatchEvidence -RequireEligible
    }
    $MismatchResult = Read-Evidence $MismatchEvidence
    if ($MismatchResult.rejection_reasons -notcontains 'INSTALLER_SIGNER_MISMATCH') { throw "Signer mismatch was not detected against the configured trusted signer." }

    $SameDir = Join-Path $OutputDir 'same-version'
    New-Item -ItemType Directory -Path $SameDir -Force | Out-Null
    $SameManifest = Join-Path $SameDir 'manifest.json'
    $SameCms = Join-Path $SameDir 'manifest.p7s'
    ./release/new-stage19-3-update-manifest.ps1 -InstallerPath $Candidate -CandidateVersion '0.8.0-rc2' -ArtifactUrl 'https://updates.example.invalid/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' -SignerThumbprint $PrimaryThumbprint -ManifestPath $SameManifest -SignaturePath $SameCms
    $SameEvidence = Join-Path $OutputDir 'STAGE19-3-SAME-VERSION.json'
    Invoke-ExpectedRefusal -Label 'same-version' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $SameManifest -ManifestSignaturePath $SameCms -InstallerPath $Candidate -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $SameEvidence -RequireEligible
    }
    $SameResult = Read-Evidence $SameEvidence
    if ($SameResult.rejection_reasons -notcontains 'CANDIDATE_VERSION_NOT_NEWER') { throw "Same-version candidate was not rejected by monotonicity." }

    $HttpDir = Join-Path $OutputDir 'http-url'
    New-Item -ItemType Directory -Path $HttpDir -Force | Out-Null
    $HttpManifest = Join-Path $HttpDir 'manifest.json'
    $HttpCms = Join-Path $HttpDir 'manifest.p7s'
    ./release/new-stage19-3-update-manifest.ps1 -InstallerPath $Candidate -CandidateVersion '0.8.0-rc3' -ArtifactUrl 'http://updates.example.invalid/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' -SignerThumbprint $PrimaryThumbprint -ManifestPath $HttpManifest -SignaturePath $HttpCms
    $HttpEvidence = Join-Path $OutputDir 'STAGE19-3-HTTP-URL.json'
    Invoke-ExpectedRefusal -Label 'http-url' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $HttpManifest -ManifestSignaturePath $HttpCms -InstallerPath $Candidate -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $HttpEvidence -RequireEligible
    }
    $HttpResult = Read-Evidence $HttpEvidence
    if ($HttpResult.rejection_reasons -notcontains 'ARTIFACT_URL_NOT_SAFE_HTTPS') { throw "HTTP candidate was not rejected by the HTTPS boundary." }

    Write-Host "[Law-Rag] Stage 19.3 positive trust chain and all negative safe-update cases passed."
}
finally {
    Remove-Item Env:LAW_RAG_RELEASE_SIGNER_THUMBPRINT -ErrorAction SilentlyContinue
    foreach ($Certificate in @($Primary, $Other)) {
        if ($null -eq $Certificate) { continue }
        $Thumbprint = $Certificate.Thumbprint
        foreach ($StoreName in @('My', 'Root', 'TrustedPublisher')) {
            $Path = "Cert:\CurrentUser\$StoreName\$Thumbprint"
            Remove-Item $Path -Force -ErrorAction SilentlyContinue
        }
    }
}
