param(
    [string]$PortableDir = (Join-Path $PSScriptRoot "rc-stage19-4"),
    [string]$InstallerPath = (Join-Path $PSScriptRoot "installer-dist\Law-Rag-0.8.0-rc3-windows-x64-setup.exe"),
    [string]$InstallerEvidencePath = (Join-Path $PSScriptRoot "installer-dist\STAGE19-1-INSTALLER-EVIDENCE.json"),
    [string]$SigningEvidencePath = (Join-Path $PSScriptRoot "final-package\STAGE19-4-SIGNING-EVIDENCE.json"),
    [string]$EvidencePath = (Join-Path $PSScriptRoot "final-package\STAGE19-4-FINAL-PACKAGE-EVIDENCE.json"),
    [string]$ExpectedReleaseLabel = "0.8.0-rc3"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ($env:OS -ne "Windows_NT") { throw "Stage 19.4 final-package evidence is Windows-only." }

function Read-JsonFile {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "$Label is missing: $Path" }
    return (Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
}

$SourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $SourceSha -notmatch '^[0-9a-f]{40}$') { throw "Could not resolve exact source SHA." }

$ManifestPath = Join-Path $PortableDir "RC-MANIFEST.json"
$SumsPath = Join-Path $PortableDir "SHA256SUMS.txt"
$Manifest = Read-JsonFile -Path $ManifestPath -Label "RC3 portable manifest"
if ([string]$Manifest.rc_version -ne $ExpectedReleaseLabel) { throw "Portable RC version mismatch." }
if ([string]$Manifest.source_commit_sha -ne $SourceSha) { throw "Portable RC source SHA mismatch." }
if ([string]$Manifest.publication_state -ne "NOT_PUBLISHED") { throw "Portable RC must remain NOT_PUBLISHED in Stage 19.4." }
if ([string]$Manifest.target -ne "windows-x64") { throw "Portable RC target mismatch." }
$ExpectedZipName = "Law-Rag-$ExpectedReleaseLabel-windows-x64.zip"
if ([string]$Manifest.artifact.filename -ne $ExpectedZipName) { throw "Portable RC filename mismatch." }
$ZipPath = Join-Path $PortableDir $ExpectedZipName
if (-not (Test-Path $ZipPath -PathType Leaf)) { throw "Portable RC ZIP is missing: $ZipPath" }
$ZipSha = Get-Sha256 $ZipPath
$ZipSize = (Get-Item $ZipPath).Length
if ($ZipSha -ne [string]$Manifest.artifact.sha256) { throw "Portable RC SHA-256 mismatch." }
if ($ZipSize -ne [int64]$Manifest.artifact.size_bytes) { throw "Portable RC byte-size mismatch." }
if (-not (Test-Path $SumsPath -PathType Leaf)) { throw "SHA256SUMS.txt is missing." }
$SumsText = Get-Content $SumsPath -Raw -Encoding UTF8
if ($SumsText -notmatch [regex]::Escape("$ZipSha  $ExpectedZipName")) { throw "SHA256SUMS.txt does not bind the RC3 ZIP." }

$Installer = (Resolve-Path $InstallerPath).Path
$InstallerEvidence = Read-JsonFile -Path $InstallerEvidencePath -Label "RC3 installer evidence"
if ([string]$InstallerEvidence.source_sha -ne $SourceSha) { throw "Installer evidence source SHA mismatch." }
if ([string]$InstallerEvidence.release_label -ne $ExpectedReleaseLabel) { throw "Installer release label mismatch." }
if ([string]$InstallerEvidence.application_version -ne "0.8.0") { throw "Installer application version mismatch." }
if ([string]$InstallerEvidence.installer.filename -ne (Split-Path $Installer -Leaf)) { throw "Installer evidence filename mismatch." }
if ([string]$InstallerEvidence.installer.sha256 -ne (Get-Sha256 $Installer)) { throw "Installer evidence SHA-256 mismatch." }
if ([int64]$InstallerEvidence.installer.size_bytes -ne (Get-Item $Installer).Length) { throw "Installer evidence byte-size mismatch." }
if ([string]$InstallerEvidence.publication_state -ne "VALIDATION_ONLY_UNSIGNED" -or [string]$InstallerEvidence.code_signing -ne "NOT_APPLIED") {
    throw "Stage 19.4 installer must remain an unsigned validation candidate before final acceptance."
}
if (-not $InstallerEvidence.user_data_separated_from_app -or -not $InstallerEvidence.uninstall_preserves_runtime) {
    throw "Installer data-ownership guarantees are missing."
}
if ($InstallerEvidence.provider_network_uat_executed -or $InstallerEvidence.private_expert_evidence_executed) {
    throw "Stage 19.4 crossed a forbidden external-evidence boundary."
}

$SigningEvidence = Read-JsonFile -Path $SigningEvidencePath -Label "Stage 19.4 signing evidence"
if ([string]$SigningEvidence.source_sha -ne $SourceSha) { throw "Signing evidence source SHA mismatch." }
if ($SigningEvidence.publication_allowed) { throw "Stage 19.4 must not be publishable without the final production signer." }
if ([string]$SigningEvidence.publication_state -ne "VALIDATION_ONLY_NOT_PUBLISHABLE") { throw "Unexpected Stage 19.4 publication state." }
if ($SigningEvidence.provider_network_uat_executed -or $SigningEvidence.private_expert_evidence_executed) {
    throw "Signing validation crossed a forbidden external-evidence boundary."
}

$EvidenceDir = Split-Path $EvidencePath -Parent
if ($EvidenceDir) { New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null }
$Evidence = [ordered]@{
    schema_version = "1.0.0"
    stage = "19.4"
    source_sha = $SourceSha
    release_label = $ExpectedReleaseLabel
    target = "windows-x64"
    engineering_state = "READY_FOR_FINAL_ACCEPTANCE"
    publication_state = "FINAL_ACCEPTANCE_PENDING"
    portable = [ordered]@{
        filename = $ExpectedZipName
        sha256 = $ZipSha
        size_bytes = $ZipSize
        manifest_sha256 = (Get-Sha256 $ManifestPath)
        sums_sha256 = (Get-Sha256 $SumsPath)
        manifest_publication_state = [string]$Manifest.publication_state
    }
    installer = [ordered]@{
        filename = (Split-Path $Installer -Leaf)
        sha256 = (Get-Sha256 $Installer)
        size_bytes = (Get-Item $Installer).Length
        validation_publication_state = [string]$InstallerEvidence.publication_state
        code_signing = [string]$InstallerEvidence.code_signing
        user_data_separated_from_app = [bool]$InstallerEvidence.user_data_separated_from_app
        uninstall_preserves_runtime = [bool]$InstallerEvidence.uninstall_preserves_runtime
    }
    signing_gate = [ordered]@{
        publication_allowed = [bool]$SigningEvidence.publication_allowed
        publication_state = [string]$SigningEvidence.publication_state
        decision_reason = [string]$SigningEvidence.decision_reason
    }
    production_signing_executed = $false
    public_release_published = $false
    provider_network_uat_executed = $false
    private_expert_evidence_executed = $false
    pending_final_acceptance_gates = @(
        "PRODUCTION_RELEASE_SIGNER_AND_PUBLISHABLE_AUTHENTICODE",
        "FINAL_RELEASE_CHANNEL_AND_PUBLICATION_URL",
        "PRIVATE_EXPERT_EVIDENCE",
        "REAL_PROVIDER_UAT",
        "STAGE16_REQUIRE_COMPLETE_EVIDENCE",
        "FINAL_PACKAGED_WINDOWS_ACCEPTANCE"
    )
}
$Evidence | ConvertTo-Json -Depth 10 | Set-Content -Path $EvidencePath -Encoding UTF8
Write-Host "[Law-Rag] Stage 19.4 package engineering: READY_FOR_FINAL_ACCEPTANCE"
Write-Host "[Law-Rag] Publication state: FINAL_ACCEPTANCE_PENDING"
Write-Host "[Law-Rag] Evidence: $EvidencePath"
