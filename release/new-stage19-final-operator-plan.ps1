param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "stage19-final-acceptance-config.json"),
    [string]$ExpectedSignerThumbprint = "",
    [string]$ReleaseChannel = "",
    [string]$PublicationUrl = "",
    [string]$OutputPath = (Join-Path $PSScriptRoot "final-acceptance\STAGE19-FINAL-OPERATOR-PLAN.json"),
    [switch]$RequireOwnerInputs
)

$ErrorActionPreference = "Stop"

function Normalize-Thumbprint([string]$Value) {
    if (-not $Value) { return "" }
    return (($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

function Test-SafeInstallerUrl([string]$Url, [string]$ExpectedFilename) {
    if (-not $Url) { return $false }
    $Uri = $null
    $Valid = (
        [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$Uri) -and
        $Uri.Scheme -eq "https" -and
        [bool]$Uri.Host -and
        -not $Uri.UserInfo -and
        -not $Uri.Query -and
        -not $Uri.Fragment
    )
    if (-not $Valid) { return $false }
    return ([Uri]::UnescapeDataString([IO.Path]::GetFileName($Uri.AbsolutePath)) -eq $ExpectedFilename)
}

if (-not (Test-Path $ConfigPath -PathType Leaf)) {
    throw "Final acceptance config is missing: $ConfigPath"
}
$Config = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$Config.schema_version -ne "1.0.0") { throw "Unsupported final acceptance config schema." }

$Baseline = $Config.engineering_candidate
$ExpectedSourceSha = ([string]$Baseline.source_sha).ToLowerInvariant()
$ExpectedReleaseLabel = [string]$Baseline.release_label
$ExpectedPortableFilename = [string]$Baseline.portable.filename
$ExpectedPortableSha = ([string]$Baseline.portable.sha256).ToLowerInvariant()
$ExpectedInstallerFilename = [string]$Baseline.installer.filename
$ExpectedInstallerSha = ([string]$Baseline.installer.sha256).ToLowerInvariant()
$SourceRunId = [string]$Baseline.source_workflow_run_id
$SourceArtifactId = [string]$Baseline.source_artifact_id
$RetainedArtifactId = [string]$Baseline.retained_artifact_id
$RetainedUntil = [string]$Baseline.retained_until

if ($ExpectedSourceSha -notmatch '^[0-9a-f]{40}$') { throw "Configured source SHA is invalid." }
if ($ExpectedPortableSha -notmatch '^[0-9a-f]{64}$') { throw "Configured portable SHA-256 is invalid." }
if ($ExpectedInstallerSha -notmatch '^[0-9a-f]{64}$') { throw "Configured installer SHA-256 is invalid." }
if ($ExpectedPortableFilename -ne [IO.Path]::GetFileName($ExpectedPortableFilename)) { throw "Configured portable filename is invalid." }
if ($ExpectedInstallerFilename -ne [IO.Path]::GetFileName($ExpectedInstallerFilename)) { throw "Configured installer filename is invalid." }
if ($Config.external_action_policy.production_signing_automatic -or
    $Config.external_action_policy.provider_network_calls_automatic -or
    $Config.external_action_policy.private_expert_execution_automatic -or
    $Config.external_action_policy.publication_automatic) {
    throw "Final acceptance config unexpectedly authorizes automatic external actions."
}

$Signer = Normalize-Thumbprint $ExpectedSignerThumbprint
if ($ExpectedSignerThumbprint -and $Signer.Length -ne 40 -and $Signer.Length -ne 64) {
    throw "ExpectedSignerThumbprint must normalize to a 40- or 64-character certificate thumbprint."
}
if ($ReleaseChannel -and $ReleaseChannel -notmatch '^[A-Za-z0-9._-]{1,64}$') {
    throw "ReleaseChannel must use only letters, digits, dot, underscore or hyphen and be at most 64 characters."
}
if ($PublicationUrl -and -not (Test-SafeInstallerUrl -Url $PublicationUrl -ExpectedFilename $ExpectedInstallerFilename)) {
    throw "PublicationUrl must be safe absolute HTTPS with no credentials/query/fragment and must end with the exact RC3 installer filename."
}

$OwnerInputsComplete = [bool]($Signer -and $ReleaseChannel -and $PublicationUrl)
$OwnerInputsAny = [bool]($ExpectedSignerThumbprint -or $ReleaseChannel -or $PublicationUrl)
$PlanState = if ($OwnerInputsComplete) { "OWNER_INPUTS_STRUCTURALLY_VALID" } elseif ($OwnerInputsAny) { "OWNER_INPUTS_PARTIAL" } else { "OWNER_INPUTS_PENDING" }

$Steps = @(
    [ordered]@{ order = 1; id = "RETRIEVE_EXACT_ENGINEERING_BASELINE"; classification = "SAFE_PRE_AUTH"; executes_external_action = $false; note = "Retrieve the exact source or retained Stage 19.4 artifact; do not rebuild." },
    [ordered]@{ order = 2; id = "VERIFY_UNSIGNED_BASELINE_HASHES"; classification = "SAFE_PRE_AUTH"; executes_external_action = $false; note = "Verify source SHA and frozen portable/installer SHA-256 identities." },
    [ordered]@{ order = 3; id = "EXTRACT_UNSIGNED_PORTABLE"; classification = "SAFE_PRE_AUTH"; executes_external_action = $false; note = "Extract the exact frozen portable to obtain the signing onedir." },
    [ordered]@{ order = 4; id = "SIGN_LAW_RAG_EXE"; classification = "AUTHORIZATION_REQUIRED_PRODUCTION_SIGNING"; executes_external_action = $true; note = "Externally Authenticode-sign only Law-Rag.exe with the authorized production signer." },
    [ordered]@{ order = 5; id = "PACKAGE_SIGNED_PORTABLE"; classification = "SAFE_AFTER_SIGNING"; executes_external_action = $false; note = "Repackage the already-signed onedir with package-rc.ps1; do not rebuild the app." },
    [ordered]@{ order = 6; id = "BUILD_INSTALLER_FROM_SIGNED_ONEDIR"; classification = "SAFE_AFTER_SIGNING"; executes_external_action = $false; note = "Build installer from the exact same signed onedir and preserve EvidenceSourceSha." },
    [ordered]@{ order = 7; id = "SIGN_INSTALLER"; classification = "AUTHORIZATION_REQUIRED_PRODUCTION_SIGNING"; executes_external_action = $true; note = "Externally Authenticode-sign the installer with the same authorized production signer." },
    [ordered]@{ order = 8; id = "VERIFY_PRODUCTION_SIGNING"; classification = "SAFE_AFTER_SIGNING"; executes_external_action = $false; note = "Run verify-stage19-2-signing.ps1 with RequirePublishable and the frozen source SHA." },
    [ordered]@{ order = 9; id = "FINAL_WINDOWS_SMOKE"; classification = "SAFE_AFTER_SIGNING"; executes_external_action = $false; note = "Prove exact baseline-to-signed transformation and installer/portable EXE identity." },
    [ordered]@{ order = 10; id = "SIGN_UPDATE_MANIFEST_CMS"; classification = "AUTHORIZATION_REQUIRED_PRODUCTION_SIGNING"; executes_external_action = $true; note = "new-stage19-3-update-manifest.ps1 uses the certificate private key to create detached CMS." },
    [ordered]@{ order = 11; id = "VERIFY_RELEASE_CHANNEL"; classification = "SAFE_AFTER_SIGNING"; executes_external_action = $false; note = "Verify CMS, Authenticode, exact signed installer hash, safe HTTPS URL, source and version without publishing." },
    [ordered]@{ order = 12; id = "PRIVATE_EXPERT_EVIDENCE"; classification = "AUTHORIZATION_REQUIRED_PRIVATE_EVIDENCE"; executes_external_action = $true; note = "Use only real sanitized private expert evidence under the existing Stage 16 protocol." },
    [ordered]@{ order = 13; id = "REAL_PROVIDER_ISSUE_V1_UAT"; classification = "AUTHORIZATION_REQUIRED_PAID_NETWORK"; executes_external_action = $true; note = "Run real DeepSeek/Kimi ISSUE_V1 UAT only after explicit authorization; capture persisted artifacts afterward." },
    [ordered]@{ order = 14; id = "BUILD_STAGE16_COMPLETE_MATRIX"; classification = "SAFE_AFTER_EXTERNAL_EVIDENCE"; executes_external_action = $false; note = "release_evidence_cli consumes existing artifacts and never invokes providers." },
    [ordered]@{ order = 15; id = "VERIFY_FINAL_ACCEPTANCE"; classification = "SAFE_EVIDENCE_ONLY"; executes_external_action = $false; note = "Final verifier may produce FINAL_ACCEPTANCE_COMPLETE_NOT_PUBLISHED only if every gate passes." },
    [ordered]@{ order = 16; id = "PUBLICATION"; classification = "AUTHORIZATION_REQUIRED_PUBLICATION"; executes_external_action = $true; note = "Publication is a separate owner-authorized action and is not performed by the final verifier." }
)

$Plan = [ordered]@{
    schema_version = "1.0.0"
    stage = "19-final-operator-handoff"
    plan_state = $PlanState
    authorization_state = "NOT_EVALUATED_BY_THIS_SCRIPT"
    executes_external_actions = $false
    engineering_baseline = [ordered]@{
        source_sha = $ExpectedSourceSha
        release_label = $ExpectedReleaseLabel
        source_workflow_run_id = $SourceRunId
        source_artifact_id = $SourceArtifactId
        retained_artifact_id = $RetainedArtifactId
        retained_until = $RetainedUntil
        portable = [ordered]@{ filename = $ExpectedPortableFilename; sha256 = $ExpectedPortableSha }
        installer = [ordered]@{ filename = $ExpectedInstallerFilename; sha256 = $ExpectedInstallerSha }
    }
    owner_inputs = [ordered]@{
        expected_signer_thumbprint = $(if ($Signer) { $Signer } else { $null })
        release_channel = $(if ($ReleaseChannel) { $ReleaseChannel } else { $null })
        publication_url = $(if ($PublicationUrl) { $PublicationUrl } else { $null })
        complete = $OwnerInputsComplete
    }
    steps = $Steps
    boundaries = [ordered]@{
        production_signing_executed_by_this_script = $false
        cms_signing_executed_by_this_script = $false
        provider_network_calls_executed_by_this_script = $false
        private_expert_evaluation_executed_by_this_script = $false
        publication_executed_by_this_script = $false
    }
}

$Parent = Split-Path $OutputPath -Parent
if ($Parent) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
$Plan | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 $OutputPath
Write-Host "[Law-Rag] Stage 19 final operator plan: $PlanState"
Write-Host "[Law-Rag] Frozen source SHA: $ExpectedSourceSha"
Write-Host "[Law-Rag] External actions executed: false"
Write-Host "[Law-Rag] Plan: $OutputPath"

if ($RequireOwnerInputs -and -not $OwnerInputsComplete) { exit 1 }
exit 0
