param(
    [string]$BundleDir = (Join-Path $PSScriptRoot "dist\Law-Rag"),
    [int]$Port = 8850
)

$ErrorActionPreference = "Stop"
$Exe = Join-Path $BundleDir "Law-Rag.exe"
$Runtime = Join-Path $env:RUNNER_TEMP ("law-rag-stage17-4-runtime-" + [guid]::NewGuid().ToString("N"))
$Stdout = Join-Path $env:RUNNER_TEMP ("law-rag-stage17-4-" + [guid]::NewGuid().ToString("N") + ".stdout.log")
$Stderr = Join-Path $env:RUNNER_TEMP ("law-rag-stage17-4-" + [guid]::NewGuid().ToString("N") + ".stderr.log")
$BaseUrl = "http://127.0.0.1:$Port"

function Write-JsonFile {
    param([string]$Path, [object]$Payload)
    $Parent = Split-Path -Parent $Path
    if ($Parent) { New-Item -ItemType Directory -Force -Path $Parent | Out-Null }
    $Payload | ConvertTo-Json -Depth 20 | Set-Content -Path $Path -Encoding UTF8
}

function Start-LawRagServer {
    if (Test-Path $Stdout) { Remove-Item $Stdout -Force }
    if (Test-Path $Stderr) { Remove-Item $Stderr -Force }
    $Process = Start-Process -FilePath $Exe -ArgumentList @("--no-browser", "--no-tray", "--port", "$Port") -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr -PassThru
    $Ready = $false
    for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
        if ($Process.HasExited) {
            $Out = if (Test-Path $Stdout) { Get-Content $Stdout -Raw } else { "" }
            $Err = if (Test-Path $Stderr) { Get-Content $Stderr -Raw } else { "" }
            throw "Law-Rag.exe exited during Stage 17.4 smoke. Exit=$($Process.ExitCode)`nSTDOUT:`n$Out`nSTDERR:`n$Err"
        }
        try {
            $Health = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/health" -TimeoutSec 2
            if ($Health.StatusCode -eq 200) { $Ready = $true; break }
        }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $Ready) {
        if (-not $Process.HasExited) { Stop-Process -Id $Process.Id -Force }
        throw "Stage 17.4 packaged server did not become ready."
    }
    return $Process
}

function Stop-LawRagServer {
    param($Process)
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        $Process.WaitForExit()
    }
}

function New-TerminalJob {
    param([guid]$JobId)
    $Job = $JobId.ToString()
    $JobDir = Join-Path $Runtime "jobs\$Job"
    $UploadDir = Join-Path $Runtime "uploads\$Job"
    $RenderedDir = Join-Path $Runtime "rendered\$Job"
    New-Item -ItemType Directory -Force -Path $JobDir, $UploadDir, $RenderedDir | Out-Null

    Write-JsonFile (Join-Path $JobDir "document.json") @{
        job_id = $Job
        filename = "stage17-smoke.pdf"
        document_kind = "pdf"
    }
    Write-JsonFile (Join-Path $JobDir "pipeline.json") @{
        schema_version = "1.3.0"
        engine_version = "stage13g-4-1.0.0"
        job_id = $Job
        status = "COMPLETE"
        current_stage = "COMPLETE"
        progress_percent = 100
        as_of = "2026-08-21"
        use_semantic = $false
        started_at = "2026-08-21T09:00:00+00:00"
        updated_at = "2026-08-21T09:05:00+00:00"
        completed_at = "2026-08-21T09:05:00+00:00"
        failure_code = $null
        failure_detail = $null
        stages = @(
            @{
                stage = "AUDIT_PLAN"
                state = "COMPLETE"
                label = "Audit plan"
                progress_percent = 40
                detail = ""
                reused_existing_artifact = $false
                started_at = "2026-08-21T09:01:00+00:00"
                finished_at = "2026-08-21T09:02:00+00:00"
            },
            @{
                stage = "ISSUE_PRIMARY_AUDIT"
                state = "COMPLETE"
                label = "Issue primary audit"
                progress_percent = 100
                detail = ""
                reused_existing_artifact = $false
                started_at = "2026-08-21T09:03:00+00:00"
                finished_at = "2026-08-21T09:05:00+00:00"
            }
        )
    }
    Set-Content -Path (Join-Path $UploadDir "source.pdf") -Value "%PDF-1.4 stage17 smoke" -Encoding ASCII
    Set-Content -Path (Join-Path $RenderedDir "page-1.png") -Value "PNG" -Encoding ASCII
}

if (-not (Test-Path $Exe)) { throw "Law-Rag.exe missing from Windows bundle." }

$PreviousRuntime = $env:LAW_RAG_RUNTIME_DIR
$PreviousLegal = $env:LAW_RAG_LEGAL_DB
$PreviousRetrieval = $env:LAW_RAG_RETRIEVAL_DB
$Process = $null

try {
    $env:LAW_RAG_RUNTIME_DIR = $Runtime
    Remove-Item Env:LAW_RAG_LEGAL_DB -ErrorAction SilentlyContinue
    Remove-Item Env:LAW_RAG_RETRIEVAL_DB -ErrorAction SilentlyContinue

    # Frozen Windows dependency/backend selection must be valid even though CI
    # starts the HTTP server with --no-tray for headless reliability.
    $TrayJson = (& $Exe --diagnose-desktop-lifecycle --json | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Frozen desktop lifecycle diagnostic failed: $TrayJson" }
    $Tray = $TrayJson | ConvertFrom-Json
    if (-not $Tray.tray_supported -or -not $Tray.pystray_available) {
        throw "Frozen Windows build does not contain a usable pystray lifecycle: $TrayJson"
    }

    $Process = Start-LawRagServer
    $RuntimeLegal = Join-Path $Runtime "legal\legal.db"
    if (-not (Test-Path $RuntimeLegal)) { throw "First-run packaged legal baseline was not installed." }
    $LegalHashBefore = (Get-FileHash -Algorithm SHA256 $RuntimeLegal).Hash.ToLowerInvariant()

    $JobId = [guid]::NewGuid()
    $BatchId = [guid]::NewGuid()
    New-TerminalJob -JobId $JobId
    $BatchPath = Join-Path $Runtime ("batches\" + $BatchId.ToString() + ".json")
    Write-JsonFile $BatchPath @{
        schema_version = "1.0.0"
        batch_id = $BatchId.ToString()
        created_at = "2026-08-21T09:00:00+00:00"
        job_ids = @($JobId.ToString())
    }
    Write-JsonFile (Join-Path $Runtime "batches\latest.json") @{ batch_id = $BatchId.ToString() }

    $History = (Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/batches/history/jobs?limit=20" -TimeoutSec 5).Content | ConvertFrom-Json
    $HistoryItem = @($History.items) | Where-Object { $_.job_id -eq $JobId.ToString() } | Select-Object -First 1
    if ($null -eq $HistoryItem -or -not $HistoryItem.can_delete -or -not $HistoryItem.terminal) {
        throw "Frozen history API did not expose the seeded terminal Job as safely deletable."
    }

    $Storage = (Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/batches/history/storage" -TimeoutSec 5).Content | ConvertFrom-Json
    if ($Storage.job_count -lt 1 -or $Storage.shared_legal_bytes -le 0 -or $Storage.jobs_bytes -le 0) {
        throw "Frozen storage summary did not report Job/shared legal storage correctly."
    }

    $WrongBody = @{ confirm_job_id = [guid]::NewGuid().ToString() } | ConvertTo-Json
    $Wrong = Invoke-WebRequest -UseBasicParsing -SkipHttpErrorCheck -Method DELETE -Uri "$BaseUrl/api/batches/history/jobs/$($JobId.ToString())" -ContentType "application/json" -Body $WrongBody -TimeoutSec 5
    if ($Wrong.StatusCode -ne 409) { throw "Wrong cleanup confirmation should return HTTP 409; got $($Wrong.StatusCode)." }
    if (-not (Test-Path (Join-Path $Runtime "jobs\$($JobId.ToString())"))) { throw "Wrong confirmation mutated Job storage." }

    $RightBody = @{ confirm_job_id = $JobId.ToString() } | ConvertTo-Json
    $Delete = Invoke-WebRequest -UseBasicParsing -Method DELETE -Uri "$BaseUrl/api/batches/history/jobs/$($JobId.ToString())" -ContentType "application/json" -Body $RightBody -TimeoutSec 10
    if ($Delete.StatusCode -ne 200) { throw "Confirmed cleanup failed with HTTP $($Delete.StatusCode)." }
    $DeleteResult = $Delete.Content | ConvertFrom-Json
    if (-not $DeleteResult.deleted -or -not $DeleteResult.shared_legal_untouched) { throw "Cleanup response did not preserve deletion/legal invariants." }
    foreach ($Category in @("jobs", "uploads", "rendered")) {
        if (Test-Path (Join-Path $Runtime "$Category\$($JobId.ToString())")) { throw "Confirmed cleanup left live $Category root." }
    }
    if ((Get-FileHash -Algorithm SHA256 $RuntimeLegal).Hash.ToLowerInvariant() -ne $LegalHashBefore) {
        throw "Job cleanup changed shared legal.db bytes."
    }
    $BatchAfter = Get-Content $BatchPath -Raw | ConvertFrom-Json
    if (@($BatchAfter.job_ids).Count -ne 0) { throw "Confirmed cleanup left a dangling batch Job reference." }
    if (Test-Path (Join-Path $Runtime "batches\latest.json")) { throw "latest.json should be removed when the last useful batch becomes empty." }

    Stop-LawRagServer $Process
    $Process = $null

    # Simulate a crash after roots were already moved to a tombstone but before
    # batch references were repaired. The next packaged server start must replay
    # the transaction before serving HTTP requests.
    $RecoveryJob = [guid]::NewGuid()
    $RecoveryBatch = [guid]::NewGuid()
    $CleanupId = [guid]::NewGuid()
    $TrashJob = Join-Path $Runtime ("cleanup\trash\" + $CleanupId.ToString() + "\jobs")
    New-Item -ItemType Directory -Force -Path $TrashJob | Out-Null
    Set-Content -Path (Join-Path $TrashJob "pipeline.json") -Value "tombstoned" -Encoding UTF8
    $RecoveryBatchPath = Join-Path $Runtime ("batches\" + $RecoveryBatch.ToString() + ".json")
    Write-JsonFile $RecoveryBatchPath @{
        schema_version = "1.0.0"
        batch_id = $RecoveryBatch.ToString()
        created_at = "2026-08-21T09:10:00+00:00"
        job_ids = @($RecoveryJob.ToString())
    }
    Write-JsonFile (Join-Path $Runtime "batches\latest.json") @{ batch_id = $RecoveryBatch.ToString() }
    $TransactionPath = Join-Path $Runtime ("cleanup\transactions\" + $CleanupId.ToString() + ".json")
    Write-JsonFile $TransactionPath @{
        schema_version = "1.0.0"
        cleanup_id = $CleanupId.ToString()
        job_id = $RecoveryJob.ToString()
        created_at = "2026-08-21T09:11:00+00:00"
        state = "ROOTS_MOVED"
        original_storage_bytes = 10
        pipeline_sha256 = ("0" * 64)
        moved_roots = @("jobs")
    }

    $Process = Start-LawRagServer
    if (Test-Path $TransactionPath) { throw "Packaged restart did not clear recovered cleanup transaction." }
    if (Test-Path (Join-Path $Runtime ("cleanup\trash\" + $CleanupId.ToString()))) { throw "Packaged restart did not purge recovered cleanup tombstone." }
    $RecoveryBatchAfter = Get-Content $RecoveryBatchPath -Raw | ConvertFrom-Json
    if (@($RecoveryBatchAfter.job_ids).Count -ne 0) { throw "Packaged cleanup recovery left a dangling batch reference." }
    if (Test-Path (Join-Path $Runtime "batches\latest.json")) { throw "Packaged cleanup recovery did not repair latest.json." }
    if ((Get-FileHash -Algorithm SHA256 $RuntimeLegal).Hash.ToLowerInvariant() -ne $LegalHashBefore) {
        throw "Packaged cleanup recovery changed shared legal.db bytes."
    }

    Write-Host "[Law-Rag] Stage 17.4 Windows validation: frozen tray dependency, history/storage API, explicit confirmation cleanup, legal protection, batch repair and restart recovery passed."
}
finally {
    Stop-LawRagServer $Process
    if ($null -eq $PreviousRuntime) { Remove-Item Env:LAW_RAG_RUNTIME_DIR -ErrorAction SilentlyContinue } else { $env:LAW_RAG_RUNTIME_DIR = $PreviousRuntime }
    if ($null -eq $PreviousLegal) { Remove-Item Env:LAW_RAG_LEGAL_DB -ErrorAction SilentlyContinue } else { $env:LAW_RAG_LEGAL_DB = $PreviousLegal }
    if ($null -eq $PreviousRetrieval) { Remove-Item Env:LAW_RAG_RETRIEVAL_DB -ErrorAction SilentlyContinue } else { $env:LAW_RAG_RETRIEVAL_DB = $PreviousRetrieval }
    foreach ($Path in @($Stdout, $Stderr)) {
        if (Test-Path $Path) { Remove-Item $Path -Force }
    }
    if (Test-Path $Runtime) { Remove-Item $Runtime -Recurse -Force }
}
