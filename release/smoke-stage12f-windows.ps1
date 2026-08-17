param(
    [Parameter(Mandatory = $true)]
    [string]$BundleDir,
    [int]$Port = 8770
)

$ErrorActionPreference = "Stop"
$Exe = Join-Path $BundleDir "Law-Rag.exe"
$SmokePdf = Join-Path $PSScriptRoot ".build\smoke-native.pdf"
$Runtime = Join-Path $env:RUNNER_TEMP ("law-rag-stage12f-runtime-" + [guid]::NewGuid().ToString("N"))
$LargePdf = Join-Path $env:RUNNER_TEMP ("law-rag-stage12f-large-" + [guid]::NewGuid().ToString("N") + ".pdf")
$PreviousRuntime = $env:LAW_RAG_RUNTIME_DIR

if (-not (Test-Path $Exe)) { throw "Law-Rag.exe not found at $Exe" }
if (-not (Test-Path $SmokePdf)) { throw "Synthetic native PDF smoke fixture not found at $SmokePdf" }

Copy-Item $SmokePdf $LargePdf -Force
$LargeStream = [System.IO.File]::Open($LargePdf, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Write)
try {
    # A 64 MiB synthetic PDF proves the packaged upload path exceeds the old
    # 50 MiB ceiling while remaining small enough for deterministic CI.
    $LargeStream.SetLength(64MB)
}
finally {
    $LargeStream.Dispose()
}

$env:LAW_RAG_RUNTIME_DIR = $Runtime

function Start-LawRag {
    param([int]$ListenPort)
    $Process = Start-Process -FilePath $Exe -ArgumentList @("--no-browser", "--port", "$ListenPort") -PassThru
    $BaseUrl = "http://127.0.0.1:$ListenPort"
    for ($Attempt = 1; $Attempt -le 40; $Attempt++) {
        if ($Process.HasExited) {
            throw "Law-Rag.exe exited during Stage 12F startup. Exit code: $($Process.ExitCode)"
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
    throw "Stage 12F packaged server did not become ready on $BaseUrl"
}

function Stop-LawRag {
    param($Process)
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        $Process.WaitForExit()
    }
}

$First = $null
$Second = $null
try {
    $First = Start-LawRag -ListenPort $Port
    $BaseUrl = $First.BaseUrl

    $ProviderBefore = Invoke-RestMethod -Uri "$BaseUrl/api/config/providers" -Method Get -TimeoutSec 10
    if ($ProviderBefore.setup_completed) {
        throw "Fresh Stage 12F runtime unexpectedly reports provider onboarding complete."
    }

    $SyntheticDeepSeek = "law-rag-stage12f-deepseek-secret"
    $SyntheticKimi = "law-rag-stage12f-kimi-secret"
    $SaveBody = @{
        deepseek_api_key = $SyntheticDeepSeek
        kimi_api_key = $SyntheticKimi
        complete_setup = $false
    } | ConvertTo-Json
    $Saved = Invoke-RestMethod -Uri "$BaseUrl/api/config/providers" -Method Put -ContentType "application/json" -Body $SaveBody -TimeoutSec 10
    $SavedJson = $Saved | ConvertTo-Json -Depth 8
    if ($SavedJson.Contains($SyntheticDeepSeek) -or $SavedJson.Contains($SyntheticKimi)) {
        throw "Provider configuration response leaked a synthetic API key."
    }
    if (($Saved.providers | Where-Object { $_.configured }).Count -ne 2) {
        throw "Packaged provider API did not resolve both Windows Credential Manager secrets."
    }

    Invoke-RestMethod -Uri "$BaseUrl/api/config/providers/deepseek" -Method Delete -TimeoutSec 10 | Out-Null
    Invoke-RestMethod -Uri "$BaseUrl/api/config/providers/kimi" -Method Delete -TimeoutSec 10 | Out-Null
    $Skipped = Invoke-RestMethod -Uri "$BaseUrl/api/config/providers/skip" -Method Post -TimeoutSec 10
    if (-not $Skipped.setup_completed) {
        throw "Provider onboarding skip state was not persisted."
    }

    $Batch = Invoke-RestMethod -Uri "$BaseUrl/api/batches" -Method Post -TimeoutSec 10
    if (-not $Batch.batch_id) { throw "Stage 12F batch creation did not return batch_id." }

    $UploadA = Invoke-RestMethod -Uri "$BaseUrl/api/documents" -Method Post -Form @{ file = Get-Item $SmokePdf } -TimeoutSec 20
    $UploadB = Invoke-RestMethod -Uri "$BaseUrl/api/documents" -Method Post -Form @{ file = Get-Item $LargePdf } -TimeoutSec 60
    foreach ($Upload in @($UploadA, $UploadB)) {
        if (-not $Upload.job_id) { throw "Stage 12F upload did not return job_id." }
        Invoke-RestMethod -Uri "$BaseUrl/api/batches/$($Batch.batch_id)/jobs/$($Upload.job_id)" -Method Post -TimeoutSec 10 | Out-Null
    }

    $Summary = Invoke-RestMethod -Uri "$BaseUrl/api/batches/$($Batch.batch_id)" -Method Get -TimeoutSec 10
    if ($Summary.total_jobs -ne 2) {
        throw "Batch summary did not retain both uploaded Jobs."
    }
    $ResultsRoute = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/results?batch=$($Batch.batch_id)" -TimeoutSec 10
    if ($ResultsRoute.StatusCode -ne 200 -or $ResultsRoute.Content -notmatch '<div id="root"></div>') {
        throw "Packaged /results route did not return the React shell."
    }

    Stop-LawRag -Process $First.Process
    $First = $null

    $Second = Start-LawRag -ListenPort $Port
    $BaseUrl = $Second.BaseUrl
    $ProviderAfter = Invoke-RestMethod -Uri "$BaseUrl/api/config/providers" -Method Get -TimeoutSec 10
    if (-not $ProviderAfter.setup_completed) {
        throw "Provider onboarding state did not survive application restart."
    }
    if (($ProviderAfter.providers | Where-Object { $_.configured }).Count -ne 0) {
        throw "Synthetic provider secrets were not deleted before restart."
    }

    $Recent = Invoke-RestMethod -Uri "$BaseUrl/api/batches/recent" -Method Get -TimeoutSec 10
    if ($Recent.batch_id -ne $Batch.batch_id -or $Recent.total_jobs -ne 2) {
        throw "Recent batch/job recovery did not survive application restart."
    }

    $RecoveredResults = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/results?batch=$($Batch.batch_id)" -TimeoutSec 10
    if ($RecoveredResults.StatusCode -ne 200) {
        throw "Recovered batch results route failed after restart."
    }

    Write-Host "[Law-Rag] Stage 12F onboarding, protected secrets, >50 MiB upload, batch persistence, restart recovery, and results-route smoke passed."
}
finally {
    if ($First) { Stop-LawRag -Process $First.Process }
    if ($Second) { Stop-LawRag -Process $Second.Process }
    if ($null -eq $PreviousRuntime) {
        Remove-Item Env:LAW_RAG_RUNTIME_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:LAW_RAG_RUNTIME_DIR = $PreviousRuntime
    }
    if (Test-Path $Runtime) { Remove-Item $Runtime -Recurse -Force }
    if (Test-Path $LargePdf) { Remove-Item $LargePdf -Force }
}
