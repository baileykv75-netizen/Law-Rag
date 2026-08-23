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

# Frozen Stage 19.4 engineering prerequisite.
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
        -not [bool]$Engineering.public_release_published
    )
    $EngineeringGate = if ($EngineeringOk) {
        New-Gate "ENGINEERING_BASELINE" "PASS" "Exact Stage 19.4 unsigned engineering baseline matches the frozen source and file hashes."
    } else {
        New-Gate "ENGINEERING_BASELINE" "FAIL" "Stage 19.4 evidence does not match the frozen engineering baseline."
    }
}
$Gates.Add($EngineeringGate)

# Production signing is evidence consumption only. This script never signs a file.
$Signing = $null
if (-not $SigningEvidencePath) {
    $SigningGate = New-Gate "PRODUCTION_SIGNING" "PENDING" "No production Authenticode verification evidence supplied."
} else {
    $Signing = Read-JsonFile -Path $SigningEvidencePath -Label "Production signing evidence"
    $ExpectedThumbprint = ([string]$Signing.expected_signer_thumbprint).ToUpperInvariant()
    $SigningOk = (
        ([string]$Signing.source_sha).ToLowerInvariant() -eq $ExpectedSourceSha -and
        [string]$Signing.verification -eq "WINDOWS_AUTHENTICODE" -and
        [bool]$Signing.expected_release_signer_configured -and
        [bool]$Signing.publication_allowed -and
        [string]$Signing.publication_state -eq "SIGNED_TRUSTED_RELEASE_CANDIDATE" -and
        [string]$Signing.executable.authenticode_status -eq "Valid" -and
        [string]$Signing.installer.authenticode_status -eq "Valid" -and
        $ExpectedThumbprint -and
        ([string]$Signing.executable.signer_thumbprint).ToUpperInvariant() -eq $ExpectedThumbprint -and
        ([string]$Signing.installer.signer_thumbprint).ToUpperInvariant() -eq $ExpectedThumbprint
    )
    $SigningGate = if ($SigningOk) {
        New-Gate "PRODUCTION_SIGNING" "PASS" "Signed executable and installer are Authenticode-valid under the explicitly configured production signer."
    } else {
        New-Gate "PRODUCTION_SIGNING" "FAIL" "Production signing evidence is present but not publishable under the configured signer identity."
    }
}
$Gates.Add($SigningGate)

# Release channel / URL decision is explicit input. This script never publishes.
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

# Stage 16 matrix owns expert/UAT truth. Synthetic evidence cannot be promoted here.
$Stage16 = $null
if (-not $Stage16EvidencePath) {
    $PrivateGate = New-Gate "PRIVATE_EXPERT" "PENDING" "No Stage 16 complete-evidence matrix supplied."
    $UatGate = New-Gate "REAL_PROVIDER_UAT" "PENDING" "No Stage 16 complete-evidence matrix supplied."
    $Stage16Gate = New-Gate "STAGE16_COMPLETE_EVIDENCE" "PENDING" "Stage 16 complete-evidence closure has not been supplied."
} else {
    $Stage16 = Read-JsonFile -Path $Stage16EvidencePath -Label "Stage 16 evidence matrix"
    $Items = @{}
    foreach ($Item in @($Stage16.evidence)) {
        $Items[[string]$Item.evidence_class] = [string]$Item.status
    }

    $PrivateStatus = [string]$Items["PRIVATE_EXPERT"]
    $UatStatus = [string]$Items["REAL_PROVIDER_UAT"]
    $PublicStatus = [string]$Items["PUBLIC_REGRESSION"]

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

    $CompleteOk = (
        [bool]$Stage16.engineering_ready -and
        [bool]$Stage16.stage16_evidence_complete -and
        $PublicStatus -eq "PASS" -and
        $PrivateStatus -eq "PRESENT" -and
        $UatStatus -eq "PASS"
    )
    if ($CompleteOk) {
        $Stage16Gate = New-Gate "STAGE16_COMPLETE_EVIDENCE" "PASS" "Stage 16 public, private-expert, and real-provider evidence closure is complete."
    } elseif ($PublicStatus -eq "FAIL" -or $PrivateStatus -eq "FAIL" -or $UatStatus -eq "FAIL") {
        $Stage16Gate = New-Gate "STAGE16_COMPLETE_EVIDENCE" "FAIL" "Stage 16 matrix contains failed evidence."
    } else {
        $Stage16Gate = New-Gate "STAGE16_COMPLETE_EVIDENCE" "PENDING" "Stage 16 matrix is structurally valid but external evidence is still incomplete."
    }
}
$Gates.Add($PrivateGate)
$Gates.Add($UatGate)
$Gates.Add($Stage16Gate)

# Final Windows smoke must describe the signed distribution candidate, not the unsigned Stage 19.4 bytes.
$Smoke = $null
if (-not $WindowsSmokeEvidencePath) {
    $SmokeGate = New-Gate "FINAL_WINDOWS_SMOKE" "PENDING" "No final signed-distribution Windows smoke evidence supplied."
} else {
    $Smoke = Read-JsonFile -Path $WindowsSmokeEvidencePath -Label "Final Windows smoke evidence"
    $SmokeOk = (
        [string]$Smoke.stage -eq "19-final-windows-smoke" -and
        ([string]$Smoke.source_sha).ToLowerInvariant() -eq $ExpectedSourceSha -and
        [string]$Smoke.release_label -eq $ExpectedReleaseLabel -and
        [bool]$Smoke.passed -and
        [int]$Smoke.provider_network_calls -eq 0 -and
        [bool]$Smoke.production_signed -and
        (Is-Sha256 ([string]$Smoke.distribution_candidate.portable.sha256)) -and
        (Is-Sha256 ([string]$Smoke.distribution_candidate.executable.sha256)) -and
        (Is-Sha256 ([string]$Smoke.distribution_candidate.installer.sha256))
    )
    if ($SmokeOk -and $null -ne $Signing) {
        $SmokeOk = (
            ([string]$Smoke.distribution_candidate.executable.sha256).ToLowerInvariant() -eq ([string]$Signing.executable.sha256).ToLowerInvariant() -and
            ([string]$Smoke.distribution_candidate.installer.sha256).ToLowerInvariant() -eq ([string]$Signing.installer.sha256).ToLowerInvariant()
        )
    }
    $SmokeGate = if ($SmokeOk) {
        New-Gate "FINAL_WINDOWS_SMOKE" "PASS" "Final Windows smoke passed on the signed distribution candidate and is source-bound to the Stage 19.4 baseline."
    } else {
        New-Gate "FINAL_WINDOWS_SMOKE" "FAIL" "Final Windows smoke evidence is invalid, failed, or does not match the signing evidence."
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
