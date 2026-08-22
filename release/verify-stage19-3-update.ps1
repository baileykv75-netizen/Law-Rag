param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$ManifestSignaturePath,
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$CurrentVersion,
    [string]$ExpectedSignerThumbprint = $env:LAW_RAG_RELEASE_SIGNER_THUMBPRINT,
    [string]$ExpectedApplicationId = "law-rag",
    [string]$ExpectedTarget = "windows-x64",
    [string]$EvidencePath = (Join-Path $PSScriptRoot "update-dist\STAGE19-3-UPDATE-EVIDENCE.json"),
    [switch]$RequireEligible
)

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "Stage 19.3 update verification is Windows-only."
}

Add-Type -AssemblyName System.Security.Cryptography.Pkcs

function Normalize-Thumbprint {
    param([string]$Value)
    if (-not $Value) { return "" }
    return (($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

function Parse-SemVer {
    param([string]$Value)
    if ($Value -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$') {
        return $null
    }
    return [pscustomobject]@{
        major = [int64]$Matches[1]
        minor = [int64]$Matches[2]
        patch = [int64]$Matches[3]
        prerelease = [string]$Matches[4]
        original = $Value
    }
}

function Compare-PrereleaseIdentifier {
    param([string]$Left, [string]$Right)
    $LeftNumeric = $Left -match '^[0-9]+$'
    $RightNumeric = $Right -match '^[0-9]+$'
    if ($LeftNumeric -and $RightNumeric) {
        $L = [System.Numerics.BigInteger]::Parse($Left)
        $R = [System.Numerics.BigInteger]::Parse($Right)
        return $L.CompareTo($R)
    }
    if ($LeftNumeric -and -not $RightNumeric) { return -1 }
    if (-not $LeftNumeric -and $RightNumeric) { return 1 }

    # The historical Law-Rag RC line uses rc2/rc3 rather than rc.2/rc.3.
    if ($Left -match '^([A-Za-z-]+)([0-9]+)$') {
        $LeftPrefix = $Matches[1]
        $LeftNumber = [System.Numerics.BigInteger]::Parse($Matches[2])
        if ($Right -match '^([A-Za-z-]+)([0-9]+)$') {
            $RightPrefix = $Matches[1]
            $RightNumber = [System.Numerics.BigInteger]::Parse($Matches[2])
            if ([string]::Equals($LeftPrefix, $RightPrefix, [StringComparison]::Ordinal)) {
                return $LeftNumber.CompareTo($RightNumber)
            }
        }
    }
    return [string]::CompareOrdinal($Left, $Right)
}

function Compare-SemVer {
    param($Left, $Right)
    foreach ($Field in @('major', 'minor', 'patch')) {
        $Comparison = $Left.$Field.CompareTo($Right.$Field)
        if ($Comparison -ne 0) { return $Comparison }
    }

    $LeftPre = [string]$Left.prerelease
    $RightPre = [string]$Right.prerelease
    if (-not $LeftPre -and -not $RightPre) { return 0 }
    if (-not $LeftPre) { return 1 }
    if (-not $RightPre) { return -1 }

    $LeftParts = $LeftPre.Split('.')
    $RightParts = $RightPre.Split('.')
    $Count = [Math]::Max($LeftParts.Count, $RightParts.Count)
    for ($Index = 0; $Index -lt $Count; $Index++) {
        if ($Index -ge $LeftParts.Count) { return -1 }
        if ($Index -ge $RightParts.Count) { return 1 }
        $Comparison = Compare-PrereleaseIdentifier -Left $LeftParts[$Index] -Right $RightParts[$Index]
        if ($Comparison -ne 0) { return $Comparison }
    }
    return 0
}

function Get-AuthenticodeRecord {
    param([string]$Path)
    $Signature = Get-AuthenticodeSignature -FilePath $Path
    $Certificate = $Signature.SignerCertificate
    return [ordered]@{
        status = [string]$Signature.Status
        status_message = [string]$Signature.StatusMessage
        signer_present = ($null -ne $Certificate)
        signer_thumbprint = $(if ($null -ne $Certificate) { Normalize-Thumbprint ([string]$Certificate.Thumbprint) } else { "" })
        signer_subject = $(if ($null -ne $Certificate) { [string]$Certificate.Subject } else { "" })
    }
}

$Rejections = [System.Collections.Generic.List[string]]::new()
function Reject {
    param([string]$Reason)
    if (-not $Rejections.Contains($Reason)) { $Rejections.Add($Reason) }
}

$ExpectedSigner = Normalize-Thumbprint $ExpectedSignerThumbprint
if (-not $ExpectedSigner) {
    Reject "NO_EXPECTED_RELEASE_SIGNER"
} elseif ($ExpectedSigner.Length -ne 40 -and $ExpectedSigner.Length -ne 64) {
    Reject "EXPECTED_SIGNER_THUMBPRINT_INVALID"
}

$ManifestPath = (Resolve-Path $ManifestPath).Path
$ManifestSignaturePath = (Resolve-Path $ManifestSignaturePath).Path
$InstallerPath = (Resolve-Path $InstallerPath).Path

$ManifestBytes = [IO.File]::ReadAllBytes($ManifestPath)
$ManifestSha256 = (Get-FileHash -Algorithm SHA256 $ManifestPath).Hash.ToLowerInvariant()
$SignatureSha256 = (Get-FileHash -Algorithm SHA256 $ManifestSignaturePath).Hash.ToLowerInvariant()
$InstallerSha256 = (Get-FileHash -Algorithm SHA256 $InstallerPath).Hash.ToLowerInvariant()
$InstallerSize = [int64](Get-Item $InstallerPath).Length

$ManifestSignerThumbprint = ""
$ManifestSignerSubject = ""
$CmsStatus = "INVALID"
try {
    $ContentInfo = [System.Security.Cryptography.Pkcs.ContentInfo]::new($ManifestBytes)
    $SignedCms = [System.Security.Cryptography.Pkcs.SignedCms]::new($ContentInfo, $true)
    $SignedCms.Decode([IO.File]::ReadAllBytes($ManifestSignaturePath))
    if ($SignedCms.SignerInfos.Count -ne 1) {
        throw "Expected exactly one CMS signer; observed $($SignedCms.SignerInfos.Count)."
    }
    $SignedCms.CheckSignature($false)
    $CmsCertificate = $SignedCms.SignerInfos[0].Certificate
    if ($null -eq $CmsCertificate) { throw "Detached CMS signer certificate is missing." }
    $ManifestSignerThumbprint = Normalize-Thumbprint ([string]$CmsCertificate.Thumbprint)
    $ManifestSignerSubject = [string]$CmsCertificate.Subject
    $CmsStatus = "VALID"
}
catch {
    $CmsStatus = "INVALID"
    Reject "MANIFEST_CMS_INVALID"
}

$Manifest = $null
try {
    $ManifestText = [Text.UTF8Encoding]::new($false, $true).GetString($ManifestBytes)
    $Manifest = $ManifestText | ConvertFrom-Json -ErrorAction Stop
}
catch {
    Reject "MANIFEST_JSON_INVALID"
}

$CandidateVersion = ""
$DeclaredSigner = ""
$ArtifactUrl = ""
if ($null -ne $Manifest) {
    if ([string]$Manifest.schema_version -ne "1.0.0") { Reject "MANIFEST_SCHEMA_UNSUPPORTED" }
    if ([string]$Manifest.application_id -ne $ExpectedApplicationId) { Reject "APPLICATION_ID_MISMATCH" }
    if ([string]$Manifest.target -ne $ExpectedTarget) { Reject "TARGET_MISMATCH" }
    if ([string]$Manifest.source_commit_sha -notmatch '^[0-9a-fA-F]{40}$') { Reject "SOURCE_SHA_INVALID" }

    $Published = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse([string]$Manifest.published_at, [ref]$Published)) {
        Reject "PUBLISHED_AT_INVALID"
    }

    $CandidateVersion = [string]$Manifest.version
    $ParsedCurrent = Parse-SemVer $CurrentVersion
    $ParsedCandidate = Parse-SemVer $CandidateVersion
    if ($null -eq $ParsedCurrent) { Reject "CURRENT_VERSION_INVALID" }
    if ($null -eq $ParsedCandidate) { Reject "CANDIDATE_VERSION_INVALID" }
    if ($null -ne $ParsedCurrent -and $null -ne $ParsedCandidate) {
        if ((Compare-SemVer -Left $ParsedCandidate -Right $ParsedCurrent) -le 0) {
            Reject "CANDIDATE_VERSION_NOT_NEWER"
        }
    }

    if ($null -eq $Manifest.artifact) {
        Reject "ARTIFACT_METADATA_MISSING"
    }
    else {
        $ArtifactFilename = [string]$Manifest.artifact.filename
        if (-not $ArtifactFilename -or $ArtifactFilename -ne [IO.Path]::GetFileName($ArtifactFilename) -or $ArtifactFilename.Contains('/') -or $ArtifactFilename.Contains('\')) {
            Reject "ARTIFACT_FILENAME_INVALID"
        }
        if ($ArtifactFilename -ne [IO.Path]::GetFileName($InstallerPath)) {
            Reject "ARTIFACT_FILENAME_MISMATCH"
        }

        $ArtifactUrl = [string]$Manifest.artifact.url
        $Uri = $null
        if (-not [Uri]::TryCreate($ArtifactUrl, [UriKind]::Absolute, [ref]$Uri) -or $Uri.Scheme -ne 'https' -or -not $Uri.Host -or $Uri.UserInfo -or $Uri.Query -or $Uri.Fragment) {
            Reject "ARTIFACT_URL_NOT_SAFE_HTTPS"
        }
        elseif ([Uri]::UnescapeDataString([IO.Path]::GetFileName($Uri.AbsolutePath)) -ne $ArtifactFilename) {
            Reject "ARTIFACT_URL_FILENAME_MISMATCH"
        }

        $DeclaredHash = ([string]$Manifest.artifact.sha256).ToLowerInvariant()
        if ($DeclaredHash -notmatch '^[0-9a-f]{64}$') { Reject "ARTIFACT_SHA256_INVALID" }
        elseif ($DeclaredHash -ne $InstallerSha256) { Reject "ARTIFACT_SHA256_MISMATCH" }

        $DeclaredSize = 0L
        try { $DeclaredSize = [int64]$Manifest.artifact.size_bytes } catch { $DeclaredSize = -1 }
        if ($DeclaredSize -le 0) { Reject "ARTIFACT_SIZE_INVALID" }
        elseif ($DeclaredSize -ne $InstallerSize) { Reject "ARTIFACT_SIZE_MISMATCH" }

        $DeclaredSigner = Normalize-Thumbprint ([string]$Manifest.artifact.authenticode_signer_thumbprint)
        if ($DeclaredSigner.Length -ne 40 -and $DeclaredSigner.Length -ne 64) {
            Reject "MANIFEST_SIGNER_THUMBPRINT_INVALID"
        }
    }
}

if ($ExpectedSigner -and $ManifestSignerThumbprint -and $ManifestSignerThumbprint -ne $ExpectedSigner) {
    Reject "MANIFEST_SIGNER_MISMATCH"
}
if ($ExpectedSigner -and $DeclaredSigner -and $DeclaredSigner -ne $ExpectedSigner) {
    Reject "DECLARED_SIGNER_MISMATCH"
}
if ($ManifestSignerThumbprint -and $DeclaredSigner -and $ManifestSignerThumbprint -ne $DeclaredSigner) {
    Reject "MANIFEST_AND_DECLARED_SIGNER_MISMATCH"
}

$InstallerSignature = Get-AuthenticodeRecord -Path $InstallerPath
if ($InstallerSignature.status -ne "Valid") {
    Reject "INSTALLER_AUTHENTICODE_NOT_VALID"
}
if ($ExpectedSigner -and $InstallerSignature.signer_thumbprint -ne $ExpectedSigner) {
    Reject "INSTALLER_SIGNER_MISMATCH"
}
if ($DeclaredSigner -and $InstallerSignature.signer_thumbprint -ne $DeclaredSigner) {
    Reject "INSTALLER_SIGNER_DOES_NOT_MATCH_MANIFEST"
}

$Eligible = ($Rejections.Count -eq 0)
$Evidence = [ordered]@{
    schema_version = "1.0.0"
    stage = "19.3"
    current_version = $CurrentVersion
    candidate_version = $CandidateVersion
    application_id = $ExpectedApplicationId
    target = $ExpectedTarget
    expected_signer_thumbprint = $ExpectedSigner
    eligible = $Eligible
    decision = $(if ($Eligible) { "UPDATE_ELIGIBLE" } else { "UPDATE_REJECTED" })
    rejection_reasons = @($Rejections)
    manifest = [ordered]@{
        path = $ManifestPath
        sha256 = $ManifestSha256
        signature_path = $ManifestSignaturePath
        signature_sha256 = $SignatureSha256
        cms_status = $CmsStatus
        signer_thumbprint = $ManifestSignerThumbprint
        signer_subject = $ManifestSignerSubject
    }
    artifact = [ordered]@{
        path = $InstallerPath
        url = $ArtifactUrl
        sha256 = $InstallerSha256
        size_bytes = $InstallerSize
        authenticode = $InstallerSignature
    }
    provider_network_uat_executed = $false
    private_expert_evidence_executed = $false
}

$EvidenceDir = Split-Path $EvidencePath -Parent
if ($EvidenceDir) { New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null }
$Evidence | ConvertTo-Json -Depth 10 | Set-Content -Path $EvidencePath -Encoding UTF8

Write-Host "[Law-Rag] Stage 19.3 update decision: $($Evidence.decision)"
if (-not $Eligible) { Write-Host "[Law-Rag] Rejections: $($Rejections -join ', ')" }
Write-Host "[Law-Rag] Evidence: $EvidencePath"

if ($RequireEligible -and -not $Eligible) {
    throw "Stage 19.3 refused the update candidate: $($Rejections -join ', ')"
}
