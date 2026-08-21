param(
    [string]$BundleDir = (Join-Path $PSScriptRoot "dist\Law-Rag"),
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$Exe = Join-Path $BundleDir "Law-Rag.exe"
$SmokePdf = Join-Path $PSScriptRoot ".build\smoke-native.pdf"
$SmokeRuntime = Join-Path $env:RUNNER_TEMP ("law-rag-stage11d-smoke-runtime-" + [guid]::NewGuid().ToString("N"))
$PreviousRuntime = $env:LAW_RAG_RUNTIME_DIR

if (-not (Test-Path $Exe)) {
    throw "Law-Rag.exe not found at $Exe"
}
if (-not (Test-Path $SmokePdf)) {
    throw "Synthetic native PDF smoke fixture not found at $SmokePdf"
}

# Never let CI smoke jobs create private/runtime artifacts inside the bundle
# that is subsequently uploaded as the release artifact.
$env:LAW_RAG_RUNTIME_DIR = $SmokeRuntime

function Assert-BundleContents {
    $Required = @(
        "Law-Rag.exe",
        "README-WINDOWS.md",
        "python-runtime.json",
        "python-resolved.txt",
        "_internal\public-assets\legal\legal.db",
        "_internal\public-assets\legal\retrieval.db",
        "_internal\release\public-assets-metadata.json",
        "_internal\release\release-metadata.json",
        "_internal\release\dependency-inventory.json",
        "_internal\frontend-dist\third-party-frontend-licenses.json",
        "_internal\THIRD-PARTY-NOTICES\python-third-party-notices.json"
    )
    foreach ($Relative in $Required) {
        if (-not (Test-Path (Join-Path $BundleDir $Relative))) {
            throw "Required release file is missing: $Relative"
        }
    }

    $Pdfium = Get-ChildItem -Path $BundleDir -Recurse -File -Filter "pdfium.dll" -ErrorAction SilentlyContinue
    if (-not $Pdfium) {
        throw "Packaged native PDF runtime does not contain pdfium.dll"
    }

    $BannedDirectoryNames = @("runtime", "uploads", "jobs", "logs", "data_private", "benchmark_private", "model_cache")
    $BannedDirectories = Get-ChildItem -Path $BundleDir -Recurse -Directory | Where-Object {
        $BannedDirectoryNames -contains $_.Name.ToLowerInvariant()
    }
    if ($BannedDirectories) {
        $Found = ($BannedDirectories.FullName -join "; ")
        throw "Bundle contains banned private/runtime directories: $Found"
    }

    $BannedJobArtifactNames = @(
        "human-review.json",
        "pipeline.json",
        "pipeline-control.json",
        "job-architecture.json",
        "audit-plan.json",
        "issue-legal-context.json",
        "issue-primary-audit.json",
        "issue-secondary-review.json",
        "issue-review-report.json",
        "ai-audit.json",
        "secondary-review.json",
        "review-report.json"
    )
    $BannedFiles = Get-ChildItem -Path $BundleDir -Recurse -File | Where-Object {
        $Name = $_.Name.ToLowerInvariant()
        $BannedJobArtifactNames -contains $Name -or
        $Name -eq ".env" -or
        $Name -like "source.pdf" -or
        $Name -like "source.jpg" -or
        $Name -like "source.jpeg" -or
        $Name -like "source.png"
    }
    if ($BannedFiles) {
        $Found = ($BannedFiles.FullName -join "; ")
        throw "Bundle contains banned private/job files: $Found"
    }
}

Assert-BundleContents

& $Exe --diagnose --json
if ($LASTEXITCODE -ne 0) {
    throw "Packaged runtime diagnostics failed with exit code $LASTEXITCODE"
}

$Process = Start-Process -FilePath $Exe -ArgumentList @("--no-browser", "--port", "$Port") -PassThru
try {
    $BaseUrl = "http://127.0.0.1:$Port"
    $Ready = $false
    for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
        if ($Process.HasExited) {
            throw "Law-Rag.exe exited before the HTTP smoke test completed. Exit code: $($Process.ExitCode)"
        }
        try {
            $Health = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/health" -TimeoutSec 2
            if ($Health.StatusCode -eq 200) {
                $Ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $Ready) {
        throw "Law-Rag packaged server did not become ready on $BaseUrl"
    }

    foreach ($Route in @("/", "/results", "/workspace", "/developer")) {
        $Page = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl$Route" -TimeoutSec 5
        if ($Page.StatusCode -ne 200 -or $Page.Content -notmatch '<div id="root"></div>') {
            throw "Packaged frontend route $Route did not return the Vite/React shell."
        }
    }

    $MissingApi = $null
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/not-a-real-route" -TimeoutSec 5 -ErrorAction Stop | Out-Null
    }
    catch {
        $MissingApi = $_.Exception.Response.StatusCode.value__
    }
    if ($MissingApi -ne 404) {
        throw "Unknown packaged API route was not an explicit 404. Observed: $MissingApi"
    }

    # Exercise the packaged native PDF ingestion path, then render the uploaded
    # page through the source-page API. This proves the collected PDFium DLL
    # works from the actual onedir executable, without OCR/provider calls.
    $Upload = Invoke-RestMethod -Uri "$BaseUrl/api/documents" -Method Post -Form @{ file = Get-Item $SmokePdf } -TimeoutSec 15
    if (-not $Upload.job_id -or $Upload.page_count -ne 1) {
        throw "Packaged native PDF upload did not return a one-page job."
    }
    $Rendered = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/documents/$($Upload.job_id)/source/pages/1" -TimeoutSec 15
    if ($Rendered.StatusCode -ne 200 -or $Rendered.Headers["Content-Type"] -notmatch "image/png") {
        throw "Packaged PDFium source-page rendering did not return image/png."
    }

    Write-Host "[Law-Rag] Packaged diagnostics, all four UI routes, API, native PDF ingestion, PDFium rendering, and private-data scan passed."
}
finally {
    if (-not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        $Process.WaitForExit()
    }
    if ($null -eq $PreviousRuntime) {
        Remove-Item Env:LAW_RAG_RUNTIME_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:LAW_RAG_RUNTIME_DIR = $PreviousRuntime
    }
    if (Test-Path $SmokeRuntime) {
        Remove-Item $SmokeRuntime -Recurse -Force
    }
}
