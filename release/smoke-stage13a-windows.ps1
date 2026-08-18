param(
    [Parameter(Mandatory = $true)]
    [string]$BundleDir,
    [int]$Port = 8786
)

$ErrorActionPreference = "Stop"
$Exe = Join-Path $BundleDir "Law-Rag.exe"
$SmokePdf = Join-Path $PSScriptRoot ".build\smoke-native.pdf"
$Runtime = Join-Path $env:RUNNER_TEMP ("law-rag-stage13a-runtime-" + [guid]::NewGuid().ToString("N"))
$PreviousRuntime = $env:LAW_RAG_RUNTIME_DIR

if (-not (Test-Path $Exe)) { throw "Law-Rag.exe not found at $Exe" }
if (-not (Test-Path $SmokePdf)) { throw "Synthetic native PDF smoke fixture not found at $SmokePdf" }

$env:LAW_RAG_RUNTIME_DIR = $Runtime
$Process = $null

function Start-LawRag {
    $Process = Start-Process -FilePath $Exe -ArgumentList @("--no-browser", "--port", "$Port") -PassThru
    $BaseUrl = "http://127.0.0.1:$Port"
    for ($Attempt = 1; $Attempt -le 40; $Attempt++) {
        if ($Process.HasExited) {
            throw "Law-Rag.exe exited during Stage 13 provider-boundary startup. Exit code: $($Process.ExitCode)"
        }
        try {
            $Health = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/health" -TimeoutSec 2
            if ($Health.StatusCode -eq 200) {
                return @{ Process = $Process; BaseUrl = $BaseUrl }
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    throw "Stage 13 packaged server did not become ready on $BaseUrl"
}

function Wait-PipelineStatus {
    param(
        [string]$BaseUrl,
        [string]$JobId,
        [string[]]$Expected,
        [int]$Attempts = 180
    )
    $Last = $null
    for ($Attempt = 1; $Attempt -le $Attempts; $Attempt++) {
        $Pipeline = Invoke-RestMethod -Uri "$BaseUrl/api/documents/$JobId/pipeline" -Method Get -TimeoutSec 10
        $Last = $Pipeline
        if ($Expected -contains $Pipeline.status) { return $Pipeline }
        if ($Pipeline.status -eq "FAILED") {
            throw "Stage 13 pipeline failed unexpectedly: $($Pipeline.failure_code) $($Pipeline.failure_detail)"
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Stage 13 pipeline did not reach expected status $($Expected -join ', '); last=$($Last.status)/$($Last.failure_code)"
}

try {
    $Started = Start-LawRag
    $Process = $Started.Process
    $BaseUrl = $Started.BaseUrl

    # REQUIRE_APPROVAL must win before the Audit Planner's first outbound call.
    # This proves the packaged product owns the provider boundary instead of
    # relying on a missing provider key as an accidental safety mechanism.
    $Upload = Invoke-RestMethod -Uri "$BaseUrl/api/documents" -Method Post -Form @{ file = Get-Item $SmokePdf } -TimeoutSec 20
    if (-not $Upload.job_id) { throw "Stage 13 upload did not return job_id." }

    $PipelineBody = @{
        as_of = (Get-Date).ToString("yyyy-MM-dd")
        use_semantic = $false
        provider_mode = "REQUIRE_APPROVAL"
    } | ConvertTo-Json
    Invoke-RestMethod -Uri "$BaseUrl/api/documents/$($Upload.job_id)/pipeline" -Method Post -ContentType "application/json" -Body $PipelineBody -TimeoutSec 10 | Out-Null

    $Paused = Wait-PipelineStatus -BaseUrl $BaseUrl -JobId $Upload.job_id -Expected @("PAUSED_BEFORE_PROVIDER")
    if ($Paused.current_stage -ne "AUDIT_PLAN" -or $Paused.failure_code -ne "PROVIDER_APPROVAL_REQUIRED") {
        throw "Packaged Stage 13 pipeline did not pause before the Audit Planner's first provider call."
    }
    if ($Paused.progress_percent -ne 48) {
        throw "Packaged Stage 13 provider boundary must occur after local RULES at 48 percent; observed $($Paused.progress_percent)."
    }

    $Control = Invoke-RestMethod -Uri "$BaseUrl/api/documents/$($Upload.job_id)/pipeline/control" -Method Get -TimeoutSec 10
    if ($Control.provider_mode -ne "REQUIRE_APPROVAL" -or $Control.provider_approved -or $Control.active_provider) {
        throw "Stage 13 persisted control state is inconsistent before approval."
    }

    $Cancel = Invoke-RestMethod -Uri "$BaseUrl/api/documents/$($Upload.job_id)/pipeline/cancel" -Method Post -TimeoutSec 10
    if ($Cancel.provider_in_flight) {
        throw "Cancellation at a paused boundary incorrectly reported an in-flight provider request."
    }
    $Cancelled = Wait-PipelineStatus -BaseUrl $BaseUrl -JobId $Upload.job_id -Expected @("CANCELLED")
    if ($Cancelled.failure_code -ne "PIPELINE_CANCELLED") {
        throw "Packaged Stage 13 cancellation did not persist the expected terminal state."
    }

    Invoke-RestMethod -Uri "$BaseUrl/api/documents/$($Upload.job_id)/pipeline/resume" -Method Post -TimeoutSec 10 | Out-Null
    $PausedAgain = Wait-PipelineStatus -BaseUrl $BaseUrl -JobId $Upload.job_id -Expected @("PAUSED_BEFORE_PROVIDER")
    if ($PausedAgain.current_stage -ne "AUDIT_PLAN" -or $PausedAgain.progress_percent -ne 48 -or $PausedAgain.failure_code -ne "PROVIDER_APPROVAL_REQUIRED") {
        throw "Explicit resume bypassed or moved the original Audit Planner provider approval boundary."
    }

    Write-Host "[Law-Rag] Packaged Stage 13 Audit Planner boundary pause/cancel/resume smoke passed without provider keys or paid calls."
}
finally {
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        $Process.WaitForExit()
    }
    if ($null -eq $PreviousRuntime) {
        Remove-Item Env:LAW_RAG_RUNTIME_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:LAW_RAG_RUNTIME_DIR = $PreviousRuntime
    }
    if (Test-Path $Runtime) { Remove-Item $Runtime -Recurse -Force }
}
