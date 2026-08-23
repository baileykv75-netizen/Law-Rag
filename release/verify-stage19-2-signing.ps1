param(
    [string]$BundleDir = (Join-Path $PSScriptRoot "dist\Law-Rag"),
    [string]$InstallerPath = (Join-Path $PSScriptRoot "installer-dist\Law-Rag-0.8.0-rc2-windows-x64-setup.exe"),
    [string]$EvidencePath = (Join-Path $PSScriptRoot "installer-dist\STAGE19-2-SIGNING-EVIDENCE.json"),
    [string]$ExpectedSignerThumbprint = $env:LAW_RAG_RELEASE_SIGNER_THUMBPRINT,
    [string]$EvidenceSourceSha = "",
    [switch]$RequirePublishable
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($env:OS -ne "Windows_NT") {
    throw "Stage 19.2 Authenticode verification is Windows-only."
}

$BundleDir = (Resolve-Path $BundleDir).Path
$ExePath = Join-Path $BundleDir "Law-Rag.exe"
if (-not (Test-Path $ExePath -PathType Leaf)) {
    throw "Frozen Law-Rag executable is missing: $ExePath"
}
$InstallerPath = (Resolve-Path $InstallerPath).Path
if (-not (Test-Path $InstallerPath -PathType Leaf)) {
    throw "Stage 19.1 installer is missing: $InstallerPath"
}

function Normalize-Thumbprint {
    param([string]$Value)
    if (-not $Value) { return "" }
    return (($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

function Get-SignatureRecord {
    param([string]$Path)

    $Signature = Get-AuthenticodeSignature -FilePath $Path
    $Certificate = $Signature.SignerCertificate
    $Thumbprint = ""
    $Subject = ""
    if ($null -ne $Certificate) {
        $Thumbprint = Normalize-Thumbprint ([string]$Certificate.Thumbprint)
        $Subject = [string]$Certificate.Subject
    }

    return [ordered]@{
        path = $Path
        sha256 = (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
        size_bytes = (Get-Item $Path).Length
        authenticode_status = [string]$Signature.Status
        authenticode_status_message = [string]$Signature.StatusMessage
        signer_present = ($null -ne $Certificate)
        signer_thumbprint = $Thumbprint
        signer_subject = $Subject
    }
}

$Expected = Normalize-Thumbprint $ExpectedSignerThumbprint
if ($Expected -and $Expected.Length -ne 40 -and $Expected.Length -ne 64) {
    throw "LAW_RAG_RELEASE_SIGNER_THUMBPRINT must be a normalized SHA-1 or SHA-256 certificate thumbprint."
}

$Executable = Get-SignatureRecord -Path $ExePath
$Installer = Get-SignatureRecord -Path $InstallerPath
$SignerConfigured = [bool]$Expected
$BothValid = ($Executable.authenticode_status -eq "Valid" -and $Installer.authenticode_status -eq "Valid")
$SignerMatches = $false
if ($SignerConfigured -and $BothValid) {
    $SignerMatches = (
        $Executable.signer_thumbprint -eq $Expected -and
        $Installer.signer_thumbprint -eq $Expected
    )
}
$PublicationAllowed = ($SignerConfigured -and $BothValid -and $SignerMatches)

if (-not $SignerConfigured) {
    $DecisionReason = "NO_EXPECTED_RELEASE_SIGNER"
} elseif (-not $BothValid) {
    $DecisionReason = "AUTHENTICODE_NOT_VALID"
} elseif (-not $SignerMatches) {
    $DecisionReason = "SIGNER_THUMBPRINT_MISMATCH"
} else {
    $DecisionReason = "AUTHENTICODE_VALID_EXPECTED_SIGNER"
}

if ($EvidenceSourceSha) {
    $SourceSha = $EvidenceSourceSha.Trim().ToLowerInvariant()
    if ($SourceSha -notmatch '^[0-9a-f]{40}$') {
        throw "EvidenceSourceSha must be a full 40-character Git SHA when supplied."
    }
} else {
    $SourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $SourceSha -notmatch '^[0-9a-f]{40}$') {
        throw "Could not resolve exact source SHA for Stage 19.2 signing evidence."
    }
}

$Evidence = [ordered]@{
    schema_version = "1.0.0"
    stage = "19.2"
    source_sha = $SourceSha
    verification = "WINDOWS_AUTHENTICODE"
    signing_performed_by_stage19_2 = $false
    expected_release_signer_configured = $SignerConfigured
    publication_allowed = $PublicationAllowed
    publication_state = $(if ($PublicationAllowed) { "SIGNED_TRUSTED_RELEASE_CANDIDATE" } else { "VALIDATION_ONLY_NOT_PUBLISHABLE" })
    decision_reason = $DecisionReason
    expected_signer_thumbprint = $Expected
    executable = $Executable
    installer = $Installer
    provider_network_uat_executed = $false
    private_expert_evidence_executed = $false
}

$EvidenceDir = Split-Path $EvidencePath -Parent
if ($EvidenceDir) { New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null }
$Evidence | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $EvidencePath

Write-Host "[Law-Rag] Stage 19.2 Authenticode state: $($Evidence.publication_state)"
Write-Host "[Law-Rag] Publication allowed: $PublicationAllowed"
Write-Host "[Law-Rag] Decision reason: $DecisionReason"
Write-Host "[Law-Rag] Evidence source SHA: $SourceSha"
Write-Host "[Law-Rag] Executable signature: $($Executable.authenticode_status)"
Write-Host "[Law-Rag] Installer signature: $($Installer.authenticode_status)"
Write-Host "[Law-Rag] Evidence: $EvidencePath"

if ($RequirePublishable -and -not $PublicationAllowed) {
    throw "Publication gate refused this build: $DecisionReason. A trusted Authenticode signature from the explicitly configured release signer is required."
}
