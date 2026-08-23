param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "stage19-final-acceptance-config.json"),
    [string]$EngineeringEvidencePath = "",
    [string]$SigningEvidencePath = "",
    [string]$Stage16EvidencePath = "",
    [string]$WindowsSmokeEvidencePath = "",
    [string]$ReleaseChannel = "",
    [string]$PublicationUrl = "",
    [string]$OutputPath = "",
    [switch]$RequireComplete
)

$ErrorActionPreference = "Stop"

function Read-JsonFile {
    param([string]$Path, [string]$Label)
    if (-not $Path) { return $null }
    if (-not (Test-Path $Path -PathType Leaf)) { throw "$Label is missing: $Path" }
    return Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function New-Gate {
    param([string]$Name, [string]$Status, [string]$Reason)
    return [ordered]@{ name = $Name; status = $Status; reason = $Reason }
}

function Is-Sha256([string]$Value) {
    return [bool]($Value -match '^[0-9a-fA-F]{64}$')
}

$Config = Read-JsonFile -Path $ConfigPath -Label "Final acceptance config"
if ([string]$Config.schema_version -ne "1.0.0") { throw "Unsupported final acceptance config schema." }
$Baseline = $Config.engineering_candidate
$ExpectedSourceSha = ([string]$Baseline.source_sha).ToLowerInvariant()
$ExpectedReleaseLabel = [string]$Baseline.release_label
$ExpectedPortableSha = ([string]$Baseline.portable.sha256).ToLowerInvariant()
$ExpectedInstallerSha = ([string]$Baseline.installer.sha256).ToLowerInvariant()

if ($ExpectedSourceSha -notmatch '^[0-9a-f]{40}$') { throw "Configured engineering source SHA is invalid." }
if (-not (Is-Sha256 $ExpectedPortableSha) -or -not (Is-Sha256 $ExpectedInstallerSha)) {
    throw "Configured Stage 19.4 artifact hashes are invalid."
}
if ($Config.external_action_policy.production_signing_automatic -or
    $Config.external_action_policy.provider_network_calls_automatic -or
    $Config.external_action_policy.private_expert_execution_automatic -or
    $Config.external_action_policy.publication_automatic) {
    throw "Final acceptance config must not authorize automatic external/signing/publication actions."
}

$Gates = New-Object System.Collections.Generic.List[object]

if (-not $EngineeringEvidencePath) {
    $EngineeringGate = New-Gate "ENGINEERING_BASELINE" "PENDING" "Stage 19.4 final package evidence was not supplied to this run."
} else {
    $Engineering = Read-JsonFile -Path $EngineeringEvidencePath -Label "Stage 19.4 engineering evidence"
    $EngineeringOk = (
        ([string]$Engineering.source_sha).ToLowerInvariant() -eq $ExpectedSourceSha -and
        [string]$Engineering.release_label -eq $ExpectedReleaseLabel -and
        [string]$Engineering.engineering_state -eq "READY_FOR_FINAL_ACCEPTANCE" -and
        [string]$Engineering.publication_state -eq "FINAL_ACCEPTANCE_PENDING" -and
        ([string]$Engineering.portable.sha256).ToLowerInvariant() -eq $ExpectedPortableSha -and
        ([string]$Engineering.installer.sha256).ToLowerInvariant() -eq $ExpectedInstallerSha -and
        -not [bool]$Engineering.production_signing_executed -and
        -not [bool]$Engineering.public_release_published -and
        -not [bool]$Engineering.provider_network_uat_executed -and
        -not [bool]$Engineering.private_expert_evidence_executed
    )
    $EngineeringGate = if ($EngineeringOk) {
        New-Gate "ENGINEERING_BASELINE" "PASS" "Exact Stage 19.4 unsigned engineering baseline matches the frozen source and file hashes."
    } else {
        New-Gate "ENGINEERING_BASELINE" "FAIL" "Stage 19.4 evidence does not match the frozen engineering baseline."
    }
}
$Gates.Add($EngineeringGate)

$Signing = $null
if (-not $SigningEvidencePath) {
    $SigningGate = New-Gate "PRODUCTION_SIGNING" "PENDING" "No production Authenticode verification evidence supplied."
} else {
    $Signing = Read-JsonFile -Path $SigningEvidencePath -Label "Production signing evidence"
    $ExpectedThumbprint = ([string]$Signing.expected_signer_thumbprint).ToUpperInvariant()
    $SigningOk = (
        [string]$Signing.schema_version -eq "1.0.0" -and
        ([string]$Signing.source_sha).ToLowerInvariant() -eq $ExpectedSourceSha -and
        [string]$Signing.verification -eq "WINDOWS_AUTHENTICODE" -and
        [bool]$Signing.expected_release_signer_configured -and
        [bool]$Signing.publication_allowed -and
        [string]$Signing.publication_state -eq "SIGNED_TRUSTED_RELEASE_CANDIDATE" -and
        [string]$Signing.executable.authenticode_status -eq "Valid" -and
        [string]$Signing.installer.authenticode_status -eq "Valid" -and
        (Is-Sha256 ([string]$Signing.executable.sha256)) -and
        (Is-Sha256 ([string]$Signing.installer.sha256)) -and
        $ExpectedThumbprint -and
        ([string]$Signing.executable.signer_thumbprint).ToUpperInvariant() -eq $ExpectedThumbprint -and
        ([string]$Signing.installer.signer_thumbprint).ToUpperInvariant() -eq $ExpectedThumbprint -and
        -not [bool]$Signing.provider_network_uat_executed -and
        -not [bool]$Signing.private_expert_evidence_executed
    )
    $SigningGate = if ($SigningOk) {
        New-Gate "PRODUCTION_SIGNING" "PASS" "Signed executable and installer are Authenticode-valid under the explicitly configured production signer."
    } else {
        New-Gate "PRODUCTION_SIGNING" "FAIL" "Production signing evidence is present but not publishable under the configured signer identity."
    }
}
$Gates.Add($SigningGate)

if (-not $ReleaseChannel -or -not $PublicationUrl) {
    $ChannelGate = New-Gate "RELEASE_CHANNEL" "PENDING" "Final release channel and HTTPS publication URL have not both been supplied."
} else {
    $ParsedUrl = $null
    $UrlOk = [Uri]::TryCreate($PublicationUrl, [UriKind]::Absolute, [ref]$ParsedUrl) -and $ParsedUrl.Scheme -eq "https"
    if ($UrlOk) {
        $ChannelGate = New-Gate "RELEASE_CHANNEL" "PASS" "Final release channel and HTTPS publication URL are explicitly recorded; no publication was performed."
    } else {
        $ChannelGate = New-Gate "RELEASE_CHANNEL" "FAIL" "Publication URL must be an absolute HTTPS URL."
    }
}
$Gates.Add($ChannelGate)

$Stage16 = $null
if (-not $Stage16EvidencePath) {
    $PrivateGate = New-Gate "PRIVATE_EXPERT" "PENDING" "No Stage 16 complete-evidence matrix supplied."
    $UatGate = New-Gate "REAL_PROVIDER_UAT" "PENDING" "No Stage 16 complete-evidence matrix supplied."
    $Stage16Gate = New-Gate "STAGE16_COMPLETE_EVIDENCE" "PENDING" "Stage 16 complete-evidence closure has not been supplied."
} else {
    $Stage16 = Read-JsonFile -Path $Stage16EvidencePath -Label "Stage 16 evidence matrix"
    $Stage16SchemaOk = ([string]$Stage16.schema_version -eq "1.0.0" -and [string]$Stage16.evaluator_version -eq "stage16e-1.0.0")
    $Items = @{}
    $DuplicateClass = $false
    foreach ($Item in @($Stage16.evidence)) {
        $Class = [string]$Item.evidence_class
        if ($Items.ContainsKey($Class)) { $DuplicateClass = $true }
        $Items[$Class] = $Item
    }
    $ExpectedClasses = @("PUBLIC_REGRESSION", "PRIVATE_EXPERT", "REAL_PROVIDER_UAT")
    $ClassShapeOk = (-not $DuplicateClass -and @($Stage16.evidence).Count -eq 3)
    foreach ($Class in $ExpectedClasses) {
        if (-not $Items.ContainsKey($Class)) { $ClassShapeOk = $false }
    }

    $PublicItem = $Items["PUBLIC_REGRESSION"]
    $PrivateItem = $Items["PRIVATE_EXPERT"]
    $UatItem = $Items["REAL_PROVIDER_UAT"]
    $PublicStatus = [string]$PublicItem.status
    $PrivateStatus = [string]$PrivateItem.status
    $UatStatus = [string]$UatItem.status

    $PrivateGate = switch ($PrivateStatus) {
        "PRESENT" { New-Gate "PRIVATE_EXPERT" "PASS" "Sanitized real private expert evidence is present in the Stage 16 matrix." }
        "PENDING" { New-Gate "PRIVATE_EXPERT" "PENDING" "Real private expert evidence remains pending." }
        default { New-Gate "PRIVATE_EXPERT" "FAIL" "Private expert evidence is absent, invalid, or structurally unusable." }
    }
    $UatGate = switch ($UatStatus) {
        "PASS" { New-Gate "REAL_PROVIDER_UAT" "PASS" "Real-provider ISSUE_V1 UAT evidence passed Stage 16 validation." }
        "PENDING" { New-Gate "REAL_PROVIDER_UAT" "PENDING" "Real-provider ISSUE_V1 UAT remains pending." }
        default { New-Gate "REAL_PROVIDER_UAT" "FAIL" "Real-provider UAT evidence is present but did not pass Stage 16 validation." }
    }

    $FingerprintsOk = (
        (Is-Sha256 ([string]$PublicItem.source_fingerprint)) -and
        (Is-Sha256 ([string]$PrivateItem.source_fingerprint)) -and
        (Is-Sha256 ([string]$UatItem.source_fingerprint))
    )
    $CompleteOk = (
        $Stage16SchemaOk -and
        $ClassShapeOk -and
        [bool]$Stage16.engineering_ready -and
        [bool]$Stage16.stage16_evidence_complete -and
        @($Stage16.pending_evidence_classes).Count -eq 0 -and
        $PublicStatus -eq "PASS" -and
        $PrivateStatus -eq "PRESENT" -and
        $UatStatus -eq "PASS" -and
        $FingerprintsOk
    )
    if ($CompleteOk) {
        $Stage16Gate = New-Gate "STAGE16_COMPLETE_EVIDENCE" "PASS" "Stage 16 matrix has the pinned schema/evaluator, exact evidence classes, source fingerprints and complete public/private/UAT closure."
    } elseif (-not $Stage16SchemaOk -or -not $ClassShapeOk -or $PublicStatus -eq "FAIL" -or $PrivateStatus -eq "FAIL" -or $UatStatus -eq "FAIL") {
        $Stage16Gate = New-Gate "STAGE16_COMPLETE_EVIDENCE" "FAIL" "Stage 16 matrix is invalid or contains failed evidence."
    } else {
        $Stage16Gate = New-Gate "STAGE16_COMPLETE_EVIDENCE" "PENDING" "Stage 16 matrix is structurally recognized but required external evidence is still incomplete."
    }
}
$Gates.Add($PrivateGate)
$Gates.Add($UatGate)
$Gates.Add($Stage16Gate)

$Smoke = $null
if (-not $WindowsSmokeEvidencePath) {
    $SmokeGate = New-Gate "FINAL_WINDOWS_SMOKE" "PENDING" "No final signed-distribution Windows smoke evidence supplied."
} else {
    $Smoke = Read-JsonFile -Path $WindowsSmokeEvidencePath -Label "Final Windows smoke evidence"
    $SmokeThumbprint = ([string]$Smoke.expected_signer_thumbprint).ToUpperInvariant()
    $SmokeChangedPaths = @($Smoke.transformation.changed_paths)
    $SmokeOk = (
        [string]$Smoke.schema_version -eq "1.0.0" -and
        [string]$Smoke.stage -eq "19-final-windows-smoke" -and
        ([string]$Smoke.source_sha).ToLowerInvariant() -eq $ExpectedSourceSha -and
        [string]$Smoke.release_label -eq $ExpectedReleaseLabel -and
        [bool]$Smoke.passed -and
        [int]$Smoke.provider_network_calls -eq 0 -and
        [bool]$Smoke.production_signed -and
        $SmokeThumbprint -and
        ([string]$Smoke.engineering_baseline.portable_sha256).ToLowerInvariant() -eq $ExpectedPortableSha -and
        ([string]$Smoke.engineering_baseline.installer_sha256).ToLowerInvariant() -eq $ExpectedInstallerSha -and
        [bool]$Smoke.transformation.exact_baseline_portable_verified -and
        [bool]$Smoke.transformation.file_list_identical -and
        $SmokeChangedPaths.Count -eq 1 -and
        [string]$SmokeChangedPaths[0] -eq "Law-Rag.exe" -and
        [bool]$Smoke.transformation.only_authenticode_target_changed -and
        [bool]$Smoke.transformation.installer_built_from_same_signed_executable -and
        [bool]$Smoke.checks.baseline_to_signed_transformation -and
        [bool]$Smoke.checks.installer_contains_same_signed_executable -and
        (Is-Sha256 ([string]$Smoke.distribution_candidate.portable.sha256)) -and
        (Is-Sha256 ([string]$Smoke.distribution_candidate.executable.sha256)) -and
        (Is-Sha256 ([string]$Smoke.distribution_candidate.installer.sha256)) -and
        ([string]$Smoke.distribution_candidate.portable.sha256).ToLowerInvariant() -ne $ExpectedPortableSha -and
        ([string]$Smoke.distribution_candidate.installer.sha256).ToLowerInvariant() -ne $ExpectedInstallerSha -and
        [string]$Smoke.distribution_candidate.executable.authenticode_status -eq "Valid" -and
        [string]$Smoke.distribution_candidate.installer.authenticode_status -eq "Valid" -and
        ([string]$Smoke.distribution_candidate.executable.signer_thumbprint).ToUpperInvariant() -eq $SmokeThumbprint -and
        ([string]$Smoke.distribution_candidate.installer.signer_thumbprint).ToUpperInvariant() -eq $SmokeThumbprint -and
        -not [bool]$Smoke.external_actions.signing_executed_by_this_script -and
        -not [bool]$Smoke.external_actions.provider_calls_executed_by_this_script -and
        -not [bool]$Smoke.external_actions.publication_executed_by_this_script
    )
    if ($SmokeOk -and $null -ne $Signing) {
        $SigningThumbprint = ([string]$Signing.expected_signer_thumbprint).ToUpperInvariant()
        $SmokeOk = (
            $SmokeThumbprint -eq $SigningThumbprint -and
            ([string]$Smoke.distribution_candidate.executable.sha256).ToLowerInvariant() -eq ([string]$Signing.executable.sha256).ToLowerInvariant() -and
            ([string]$Smoke.distribution_candidate.installer.sha256).ToLowerInvariant() -eq ([string]$Signing.installer.sha256).ToLowerInvariant()
        )
    }
    $SmokeGate = if ($SmokeOk) {
        New-Gate "FINAL_WINDOWS_SMOKE" "PASS" "Final Windows smoke passed on one signed distribution candidate and proves exact Stage 19.4 baseline-to-signed provenance."
    } else {
        New-Gate "FINAL_WINDOWS_SMOKE" "FAIL" "Final Windows smoke evidence is invalid, lacks exact baseline provenance, or does not match the production signing evidence."
    }
}
$Gates.Add($SmokeGate)

$AnyFail = @($Gates | Where-Object { $_.status -eq "FAIL" }).Count -gt 0
$AllPass = @($Gates | Where-Object { $_.status -ne "PASS" }).Count -eq 0
$AcceptanceState = if ($AnyFail) {
    "FINAL_ACCEPTANCE_FAILED"
} elseif ($AllPass) {
    "FINAL_ACCEPTANCE_COMPLETE_NOT_PUBLISHED"
} else {
    "FINAL_ACCEPTANCE_PENDING"
}

$Report = [ordered]@{
    schema_version = "1.0.0"
    acceptance_id = [string]$Config.acceptance_id
    engineering_candidate = [ordered]@{
        source_sha = $ExpectedSourceSha
        release_label = $ExpectedReleaseLabel
        unsigned_portable_sha256 = $ExpectedPortableSha
        unsigned_installer_sha256 = $ExpectedInstallerSha
    }
    acceptance_state = $AcceptanceState
    complete = $AllPass
    gates = @($Gates)
    distribution_candidate = if ($null -ne $Smoke) { $Smoke.distribution_candidate } else { $null }
    release_channel = if ($ReleaseChannel) { $ReleaseChannel } else { $null }
    publication_url = if ($PublicationUrl) { $PublicationUrl } else { $null }
    external_actions = [ordered]@{
        production_signing_executed_by_this_script = $false
        provider_network_calls_executed_by_this_script = $false
        private_expert_evaluation_executed_by_this_script = $false
        publication_executed_by_this_script = $false
    }
    warnings = @(
        "Stage 19.4 hashes identify the unsigned engineering baseline. Production Authenticode signing changes distribution bytes and therefore creates new signed candidate hashes.",
        "Final acceptance completion is an evidence state; this verifier never performs the publication action.",
        "DeepSeek/Kimi completion evidence and private expert evidence remain separate Stage 16 evidence classes and are not converted into an overall legal-accuracy score."
    )
}

$Rendered = $Report | ConvertTo-Json -Depth 12
if ($OutputPath) {
    $Parent = Split-Path $OutputPath -Parent
    if ($Parent) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
    $Rendered | Set-Content -Encoding UTF8 $OutputPath
}
Write-Host $Rendered

if ($AnyFail) { exit 2 }
if ($RequireComplete -and -not $AllPass) { exit 1 }
exit 0
