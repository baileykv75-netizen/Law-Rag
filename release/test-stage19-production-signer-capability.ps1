param(
    [Parameter(Mandatory = $true)]
    [string]$SignerThumbprint,
    [string]$OutputPath = (Join-Path $PSScriptRoot "final-acceptance\STAGE19-PRODUCTION-SIGNER-PREFLIGHT.json"),
    [switch]$RequireTrustedAuthenticode,
    [switch]$KeepProbeArtifacts
)

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "Stage 19 production signer capability preflight is Windows-only."
}

Add-Type -AssemblyName System.Security.Cryptography.Pkcs

function Normalize-Thumbprint {
    param([string]$Value)
    if (-not $Value) { return "" }
    return (($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

function Get-CodeSigningEkuState {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate)

    $EnhancedKeyUsageExtension = @($Certificate.Extensions | Where-Object {
        $_ -is [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]
    } | Select-Object -First 1)

    if ($EnhancedKeyUsageExtension.Count -eq 0) {
        return [ordered]@{
            extension_present = $false
            code_signing_present = $false
            eku_oids = @()
        }
    }

    $Oids = @($EnhancedKeyUsageExtension[0].EnhancedKeyUsages | ForEach-Object { [string]$_.Value })
    return [ordered]@{
        extension_present = $true
        code_signing_present = ($Oids -contains "1.3.6.1.5.5.7.3.3")
        eku_oids = $Oids
    }
}

$NormalizedSigner = Normalize-Thumbprint $SignerThumbprint
if ($NormalizedSigner.Length -ne 40 -and $NormalizedSigner.Length -ne 64) {
    throw "SignerThumbprint must normalize to a 40- or 64-character certificate thumbprint."
}

$CertificatePath = "Cert:\CurrentUser\My\$NormalizedSigner"
$Certificate = Get-Item $CertificatePath -ErrorAction Stop
$ResolvedThumbprint = Normalize-Thumbprint ([string]$Certificate.Thumbprint)
if ($ResolvedThumbprint -ne $NormalizedSigner) {
    throw "Resolved certificate thumbprint does not match the requested signer."
}
if (-not $Certificate.HasPrivateKey) {
    throw "Signer certificate is present but no private key is available through the Windows certificate provider."
}

$Now = [DateTimeOffset]::UtcNow
$NotBefore = [DateTimeOffset]$Certificate.NotBefore
$NotAfter = [DateTimeOffset]$Certificate.NotAfter
$TimeValid = ($Now -ge $NotBefore.ToUniversalTime() -and $Now -lt $NotAfter.ToUniversalTime())
if (-not $TimeValid) {
    throw "Signer certificate is outside its validity interval."
}

$Eku = Get-CodeSigningEkuState -Certificate $Certificate
if (-not $Eku.code_signing_present) {
    throw "Signer certificate does not contain the Code Signing EKU 1.3.6.1.5.5.7.3.3."
}

$ProbeRoot = Join-Path ([IO.Path]::GetTempPath()) ("law-rag-stage19-signer-preflight-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $ProbeRoot -Force | Out-Null

$AuthenticodeProbePath = Join-Path $ProbeRoot "LAW-RAG-SIGNER-PREFLIGHT.ps1"
$CmsPayloadPath = Join-Path $ProbeRoot "LAW-RAG-CMS-PREFLIGHT.txt"
$CmsSignaturePath = Join-Path $ProbeRoot "LAW-RAG-CMS-PREFLIGHT.p7s"

$AuthenticodeResult = $null
$AuthenticodeStatus = "NOT_RUN"
$AuthenticodeSignerThumbprint = ""
$AuthenticodeSignerMatches = $false
$CmsComputeSucceeded = $false
$CmsSignatureOnlyValid = $false
$CmsSignerThumbprint = ""
$CmsSignerMatches = $false
$CmsSignatureSizeBytes = [int64]0
$FailureReason = $null

try {
    Set-Content -Path $AuthenticodeProbePath -Encoding UTF8 -NoNewline -Value "Write-Output 'Law-Rag Stage 19 signer capability preflight'"

    $AuthenticodeResult = Set-AuthenticodeSignature `
        -FilePath $AuthenticodeProbePath `
        -Certificate $Certificate `
        -HashAlgorithm SHA256

    $ObservedAuthenticode = Get-AuthenticodeSignature -FilePath $AuthenticodeProbePath
    $AuthenticodeStatus = [string]$ObservedAuthenticode.Status
    if ($null -ne $ObservedAuthenticode.SignerCertificate) {
        $AuthenticodeSignerThumbprint = Normalize-Thumbprint ([string]$ObservedAuthenticode.SignerCertificate.Thumbprint)
    }
    $AuthenticodeSignerMatches = ($AuthenticodeSignerThumbprint -eq $NormalizedSigner)

    if ($null -eq $ObservedAuthenticode.SignerCertificate -or -not $AuthenticodeSignerMatches) {
        throw "Authenticode probe did not resolve to the requested signer."
    }
    if ($RequireTrustedAuthenticode -and $AuthenticodeStatus -ne "Valid") {
        throw "Authenticode probe status is '$AuthenticodeStatus'; trusted production signing requires 'Valid'."
    }

    $CmsPayload = [Text.UTF8Encoding]::new($false).GetBytes("Law-Rag Stage 19 detached CMS signer capability preflight v1")
    [IO.File]::WriteAllBytes($CmsPayloadPath, $CmsPayload)

    $ContentInfo = [System.Security.Cryptography.Pkcs.ContentInfo]::new($CmsPayload)
    $SignedCms = [System.Security.Cryptography.Pkcs.SignedCms]::new($ContentInfo, $true)
    $CmsSigner = [System.Security.Cryptography.Pkcs.CmsSigner]::new(
        [System.Security.Cryptography.Pkcs.SubjectIdentifierType]::IssuerAndSerialNumber,
        $Certificate
    )
    $CmsSigner.IncludeOption = [System.Security.Cryptography.X509Certificates.X509IncludeOption]::EndCertOnly
    $SignedCms.ComputeSignature($CmsSigner, $false)
    $CmsBytes = $SignedCms.Encode()
    [IO.File]::WriteAllBytes($CmsSignaturePath, $CmsBytes)
    $CmsComputeSucceeded = $true
    $CmsSignatureSizeBytes = [int64]$CmsBytes.Length

    $VerifyContent = [System.Security.Cryptography.Pkcs.ContentInfo]::new($CmsPayload)
    $VerifyCms = [System.Security.Cryptography.Pkcs.SignedCms]::new($VerifyContent, $true)
    $VerifyCms.Decode($CmsBytes)
    $VerifyCms.CheckSignature($true)
    $CmsSignatureOnlyValid = $true

    if ($VerifyCms.SignerInfos.Count -ne 1) {
        throw "Detached CMS probe must contain exactly one signer."
    }
    if ($null -ne $VerifyCms.SignerInfos[0].Certificate) {
        $CmsSignerThumbprint = Normalize-Thumbprint ([string]$VerifyCms.SignerInfos[0].Certificate.Thumbprint)
    }
    $CmsSignerMatches = ($CmsSignerThumbprint -eq $NormalizedSigner)
    if (-not $CmsSignerMatches) {
        throw "Detached CMS probe signer does not match the requested signer."
    }
} catch {
    $FailureReason = $_.Exception.Message
}

$InterfaceCapable = (
    $Certificate.HasPrivateKey -and
    $TimeValid -and
    $Eku.code_signing_present -and
    $AuthenticodeSignerMatches -and
    $CmsComputeSucceeded -and
    $CmsSignatureOnlyValid -and
    $CmsSignerMatches -and
    (-not $RequireTrustedAuthenticode -or $AuthenticodeStatus -eq "Valid") -and
    -not $FailureReason
)

$Evidence = [ordered]@{
    schema_version = "1.0.0"
    stage = "19-final-production-signer-preflight"
    candidate_touched = $false
    engineering_candidate_source_sha = "8c05ddd91712d5d9cdbdafe90e77cc9de03b8593"
    authorization_evaluated_by_this_script = $false
    production_candidate_signing_executed = $false
    signer = [ordered]@{
        thumbprint = $NormalizedSigner
        has_private_key = [bool]$Certificate.HasPrivateKey
        time_valid = $TimeValid
        not_before_utc = $NotBefore.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ", [Globalization.CultureInfo]::InvariantCulture)
        not_after_utc = $NotAfter.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ", [Globalization.CultureInfo]::InvariantCulture)
        code_signing_eku_present = [bool]$Eku.code_signing_present
        eku_oids = @($Eku.eku_oids)
    }
    authenticode_probe = [ordered]@{
        status = $AuthenticodeStatus
        signer_thumbprint = $(if ($AuthenticodeSignerThumbprint) { $AuthenticodeSignerThumbprint } else { $null })
        signer_matches_requested = $AuthenticodeSignerMatches
        trusted_status_required = [bool]$RequireTrustedAuthenticode
    }
    detached_cms_probe = [ordered]@{
        compute_succeeded = $CmsComputeSucceeded
        signature_only_valid = $CmsSignatureOnlyValid
        signer_thumbprint = $(if ($CmsSignerThumbprint) { $CmsSignerThumbprint } else { $null })
        signer_matches_requested = $CmsSignerMatches
        signature_size_bytes = $CmsSignatureSizeBytes
    }
    signer_interface_capable = $InterfaceCapable
    preflight_state = $(if ($InterfaceCapable) { "SIGNING_INTERFACE_CAPABLE" } else { "SIGNING_INTERFACE_INCOMPATIBLE" })
    failure_reason = $FailureReason
}

$Parent = Split-Path $OutputPath -Parent
if ($Parent) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
$Evidence | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $OutputPath

if (-not $KeepProbeArtifacts) {
    Remove-Item -LiteralPath $ProbeRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "[Law-Rag] Stage 19 signer interface preflight: $($Evidence.preflight_state)"
Write-Host "[Law-Rag] Candidate touched: false"
Write-Host "[Law-Rag] Authenticode probe: $AuthenticodeStatus"
Write-Host "[Law-Rag] Detached CMS probe: $CmsSignatureOnlyValid"
Write-Host "[Law-Rag] Evidence: $OutputPath"

if (-not $InterfaceCapable) {
    throw "Production signer interface preflight failed: $FailureReason"
}
