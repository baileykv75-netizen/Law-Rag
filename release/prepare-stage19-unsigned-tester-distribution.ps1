param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,
    [Parameter(Mandatory = $true)]
    [string]$OutputDir,
    [string]$GuidePath = (Join-Path $PSScriptRoot "..\docs\STAGE19_UNSIGNED_TESTER_DISTRIBUTION.md"),
    [string]$FeedbackPath = (Join-Path $PSScriptRoot "..\docs\STAGE19_TESTER_FEEDBACK_TEMPLATE.md"),
    [string]$EvidencePath = ""
)

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Unsigned tester distribution preparation is Windows-only." }

$ExpectedSourceSha = "8c05ddd91712d5d9cdbdafe90e77cc9de03b8593"
$ExpectedReleaseLabel = "0.8.0-rc3"
$ExpectedPortableName = "Law-Rag-0.8.0-rc3-windows-x64.zip"
$ExpectedInstallerName = "Law-Rag-0.8.0-rc3-windows-x64-setup.exe"
$ExpectedPortableSha = "9ba6c15cab5aa97820311ee97589ed338d88b9fad81ab6b96d06ff6162b6e796"
$ExpectedInstallerSha = "cc94adf002984c7bfd7d2c0b7c7fc30e4bf19a95add655c448ace8a5deeb1ef8"
$RetainedArtifactId = "9491794952"
$RetainedRunId = "32633906191"
$RetainedArtifactDigest = "sha256:af32108fb2989269d73c1ffd28c3633cdab1bb747d4f96bcbb65d14264dfe36c"
$RetainedUntilUtc = "2026-11-21T10:29:51Z"

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
}

function Find-OneFile([string]$Root, [string]$Name, [string]$Label) {
    $Matches = @(Get-ChildItem -Path $Root -Recurse -File -Filter $Name)
    if ($Matches.Count -ne 1) {
        throw "Expected exactly one $Label named '$Name' under '$Root', found $($Matches.Count)."
    }
    return $Matches[0].FullName
}

$SourceDir = (Resolve-Path $SourceDir).Path
if (-not (Test-Path $GuidePath -PathType Leaf)) { throw "Tester guide is missing: $GuidePath" }
if (-not (Test-Path $FeedbackPath -PathType Leaf)) { throw "Tester feedback template is missing: $FeedbackPath" }

$PortablePath = Find-OneFile -Root $SourceDir -Name $ExpectedPortableName -Label "frozen portable"
$InstallerPath = Find-OneFile -Root $SourceDir -Name $ExpectedInstallerName -Label "frozen installer"
$PackageEvidencePath = Find-OneFile -Root $SourceDir -Name "STAGE19-4-FINAL-PACKAGE-EVIDENCE.json" -Label "Stage 19.4 final-package evidence"
$RcManifestPath = Find-OneFile -Root $SourceDir -Name "RC-MANIFEST.json" -Label "RC manifest"
$SumsPath = Find-OneFile -Root $SourceDir -Name "SHA256SUMS.txt" -Label "RC SHA256SUMS"

$PortableSha = Get-Sha256 $PortablePath
$InstallerSha = Get-Sha256 $InstallerPath
if ($PortableSha -ne $ExpectedPortableSha) { throw "Frozen portable SHA-256 mismatch: $PortableSha" }
if ($InstallerSha -ne $ExpectedInstallerSha) { throw "Frozen installer SHA-256 mismatch: $InstallerSha" }

$PackageEvidence = Get-Content $PackageEvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$PackageEvidence.source_sha -ne $ExpectedSourceSha) { throw "Stage 19.4 evidence source SHA mismatch." }
if ([string]$PackageEvidence.release_label -ne $ExpectedReleaseLabel) { throw "Stage 19.4 release label mismatch." }
if ([string]$PackageEvidence.engineering_state -ne "READY_FOR_FINAL_ACCEPTANCE") { throw "Stage 19.4 engineering state mismatch." }
if ([string]$PackageEvidence.publication_state -ne "FINAL_ACCEPTANCE_PENDING") { throw "Stage 19.4 publication state mismatch." }
if ([string]$PackageEvidence.portable.sha256 -ne $ExpectedPortableSha) { throw "Stage 19.4 evidence portable hash mismatch." }
if ([string]$PackageEvidence.installer.sha256 -ne $ExpectedInstallerSha) { throw "Stage 19.4 evidence installer hash mismatch." }
if ([string]$PackageEvidence.installer.code_signing -ne "NOT_APPLIED") { throw "Tester installer is not the frozen unsigned candidate." }
if ([bool]$PackageEvidence.production_signing_executed) { throw "Stage 19.4 evidence unexpectedly claims production signing." }
if ([bool]$PackageEvidence.public_release_published) { throw "Stage 19.4 evidence unexpectedly claims publication." }

$RcManifest = Get-Content $RcManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$RcManifest.source_commit_sha -ne $ExpectedSourceSha) { throw "RC manifest source SHA mismatch." }
if ([string]$RcManifest.rc_version -ne $ExpectedReleaseLabel) { throw "RC manifest version mismatch." }
if ([string]$RcManifest.publication_state -ne "NOT_PUBLISHED") { throw "RC manifest must remain NOT_PUBLISHED." }
if ([string]$RcManifest.artifact.filename -ne $ExpectedPortableName) { throw "RC manifest portable filename mismatch." }
if ([string]$RcManifest.artifact.sha256 -ne $ExpectedPortableSha) { throw "RC manifest portable hash mismatch." }
$SumsText = Get-Content $SumsPath -Raw -Encoding UTF8
if ($SumsText -notmatch [regex]::Escape("$ExpectedPortableSha  $ExpectedPortableName")) { throw "RC SHA256SUMS does not bind the frozen portable." }

$InstallerSignature = Get-AuthenticodeSignature $InstallerPath
if ([string]$InstallerSignature.Status -ne "NotSigned") {
    throw "Tester installer must remain unsigned; actual Authenticode status is '$($InstallerSignature.Status)'."
}

$ProbeDir = Join-Path ([IO.Path]::GetTempPath()) ("law-rag-stage19-tester-probe-" + [Guid]::NewGuid().ToString("N"))
try {
    Expand-Archive -Path $PortablePath -DestinationPath $ProbeDir -Force
    $PortableExe = Find-OneFile -Root $ProbeDir -Name "Law-Rag.exe" -Label "portable Law-Rag.exe"
    $PortableExeSignature = Get-AuthenticodeSignature $PortableExe
    if ([string]$PortableExeSignature.Status -ne "NotSigned") {
        throw "Portable Law-Rag.exe must remain unsigned; actual Authenticode status is '$($PortableExeSignature.Status)'."
    }
}
finally {
    Remove-Item $ProbeDir -Recurse -Force -ErrorAction SilentlyContinue
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DistributionHeadSha = (& git -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $DistributionHeadSha -notmatch '^[0-9a-f]{40}$') { throw "Could not resolve distribution tooling head SHA." }

if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
$InstallerOutDir = Join-Path $OutputDir "installer"
$PortableOutDir = Join-Path $OutputDir "portable"
New-Item -ItemType Directory -Path $InstallerOutDir -Force | Out-Null
New-Item -ItemType Directory -Path $PortableOutDir -Force | Out-Null

Copy-Item $InstallerPath (Join-Path $InstallerOutDir $ExpectedInstallerName) -Force
Copy-Item $PortablePath (Join-Path $PortableOutDir $ExpectedPortableName) -Force
foreach ($TargetDir in @($InstallerOutDir, $PortableOutDir)) {
    Copy-Item $GuidePath (Join-Path $TargetDir "TESTER-README.md") -Force
    Copy-Item $FeedbackPath (Join-Path $TargetDir "TESTER-FEEDBACK.md") -Force
    Copy-Item $PackageEvidencePath (Join-Path $TargetDir "STAGE19-4-FINAL-PACKAGE-EVIDENCE.json") -Force
}

$InstallerSumText = "$ExpectedInstallerSha  $ExpectedInstallerName`n"
$PortableSumText = "$ExpectedPortableSha  $ExpectedPortableName`n"
[IO.File]::WriteAllText((Join-Path $InstallerOutDir "SHA256SUMS-TESTER.txt"), $InstallerSumText, [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $PortableOutDir "SHA256SUMS-TESTER.txt"), $PortableSumText, [Text.UTF8Encoding]::new($false))

$Evidence = [ordered]@{
    schema_version = "1.0.0"
    stage = "19-unsigned-tester-distribution"
    distribution_state = "READY_FOR_LIMITED_UNSIGNED_TESTING"
    distribution_scope = "INVITED_TESTERS_ONLY"
    release_label = $ExpectedReleaseLabel
    target = "windows-x64"
    engineering_candidate = [ordered]@{
        source_sha = $ExpectedSourceSha
        retained_workflow_run_id = $RetainedRunId
        retained_artifact_id = $RetainedArtifactId
        retained_artifact_digest = $RetainedArtifactDigest
        retained_until_utc = $RetainedUntilUtc
        portable = [ordered]@{
            filename = $ExpectedPortableName
            sha256 = $ExpectedPortableSha
            authenticode_state = "UNSIGNED_CONTAINER_WITH_UNSIGNED_LAW_RAG_EXE"
        }
        installer = [ordered]@{
            filename = $ExpectedInstallerName
            sha256 = $ExpectedInstallerSha
            authenticode_status = [string]$InstallerSignature.Status
        }
    }
    tester_handoff = [ordered]@{
        tooling_head_sha = $DistributionHeadSha
        binaries_modified = $false
        application_rebuilt = $false
        installer_rebuilt = $false
        production_signing_executed = $false
        detached_cms_signing_executed = $false
        public_release_published = $false
        update_channel_published = $false
        provider_network_uat_executed = $false
        private_expert_evidence_executed = $false
    }
    expected_windows_behavior = [ordered]@{
        unknown_publisher_possible = $true
        smartscreen_warning_possible = $true
        hash_verification_required_before_bypass = $true
    }
    production_release = [ordered]@{
        final_acceptance_state = "FINAL_ACCEPTANCE_PENDING"
        production_signer_deferred = $true
        production_signing_required_before_public_trusted_release = $true
    }
}

if (-not $EvidencePath) { $EvidencePath = Join-Path $OutputDir "STAGE19-UNSIGNED-TESTER-DISTRIBUTION-EVIDENCE.json" }
$Evidence | ConvertTo-Json -Depth 12 | Set-Content -Path $EvidencePath -Encoding UTF8
foreach ($TargetDir in @($InstallerOutDir, $PortableOutDir)) {
    Copy-Item $EvidencePath (Join-Path $TargetDir "STAGE19-UNSIGNED-TESTER-DISTRIBUTION-EVIDENCE.json") -Force
}

if ((Get-Sha256 (Join-Path $InstallerOutDir $ExpectedInstallerName)) -ne $ExpectedInstallerSha) { throw "Installer changed during tester handoff." }
if ((Get-Sha256 (Join-Path $PortableOutDir $ExpectedPortableName)) -ne $ExpectedPortableSha) { throw "Portable changed during tester handoff." }

Write-Host "[Law-Rag] unsigned tester distribution: READY_FOR_LIMITED_UNSIGNED_TESTING"
Write-Host "[Law-Rag] binaries modified: false"
Write-Host "[Law-Rag] production signing executed: false"
Write-Host "[Law-Rag] public release published: false"
Write-Host "[Law-Rag] production Final Acceptance: FINAL_ACCEPTANCE_PENDING"
Write-Host "[Law-Rag] installer output: $InstallerOutDir"
Write-Host "[Law-Rag] portable output: $PortableOutDir"
