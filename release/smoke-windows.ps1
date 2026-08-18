param(
    [string]$BundleDir = (Join-Path $PSScriptRoot "dist\Law-Rag"),
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$Exe = Join-Path $BundleDir "Law-Rag.exe"
$SmokePdf = Join-Path $PSScriptRoot ".build\smoke-native.pdf"
$SmokeOcrImage = Join-Path $env:RUNNER_TEMP ("law-rag-stage14-ocr-smoke-" + [guid]::NewGuid().ToString("N") + ".png")
$SmokeRuntime = Join-Path $env:RUNNER_TEMP ("law-rag-stage14-smoke-runtime-" + [guid]::NewGuid().ToString("N"))
$PreviousRuntime = $env:LAW_RAG_RUNTIME_DIR

if (-not (Test-Path $Exe)) {
    throw "Law-Rag.exe not found at $Exe"
}
if (-not (Test-Path $SmokePdf)) {
    throw "Synthetic native PDF smoke fixture not found at $SmokePdf"
}

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
        "_internal\release\ocr-models-manifest.json",
        "_internal\ocr-models\PP-OCRv6_medium_det\inference.json",
        "_internal\ocr-models\PP-OCRv6_medium_det\inference.pdiparams",
        "_internal\ocr-models\PP-OCRv6_medium_det\inference.yml",
        "_internal\ocr-models\PP-OCRv6_medium_rec\inference.json",
        "_internal\ocr-models\PP-OCRv6_medium_rec\inference.pdiparams",
        "_internal\ocr-models\PP-OCRv6_medium_rec\inference.yml",
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

    $PaddleNative = Get-ChildItem -Path $BundleDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
        $_.FullName.ToLowerInvariant().Contains("paddle") -and $_.Extension.ToLowerInvariant() -in @(".dll", ".pyd")
    }
    if (-not $PaddleNative) {
        throw "Packaged OCR runtime does not contain Paddle native DLL/PYD files"
    }

    foreach ($RootPrivateName in @("runtime", "uploads", "jobs", "logs", "data_private", "benchmark_private")) {
        $PrivatePath = Join-Path $BundleDir $RootPrivateName
        if (Test-Path $PrivatePath) {
            throw "Bundle contains private application data directory: $PrivatePath"
        }
    }

    $ApprovedModelRoot = (Join-Path $BundleDir "_internal\ocr-models")
    $ApprovedModels = @(
        (Join-Path $ApprovedModelRoot "PP-OCRv6_medium_det"),
        (Join-Path $ApprovedModelRoot "PP-OCRv6_medium_rec")
    ) | ForEach-Object { [System.IO.Path]::GetFullPath($_).TrimEnd('\') }

    $BannedOcrDirectories = Get-ChildItem -Path $BundleDir -Recurse -Directory | Where-Object {
        $Full = [System.IO.Path]::GetFullPath($_.FullName).TrimEnd('\')
        $Lower = $_.Name.ToLowerInvariant()
        $IsCache = $Lower -in @("model_cache", ".paddlex", ".paddleocr", "official_models")
        $LooksLikeModel = $_.Name -like "PP-OCRv6*_det" -or $_.Name -like "PP-OCRv6*_rec"
        $IsCache -or ($LooksLikeModel -and $ApprovedModels -notcontains $Full)
    }
    if ($BannedOcrDirectories) {
        $Found = ($BannedOcrDirectories.FullName -join "; ")
        throw "Bundle contains banned OCR cache/unapproved model directories: $Found"
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
        $Name -like "source.png" -or
        $Name -like "source.docx"
    }
    if ($BannedFiles) {
        $Found = ($BannedFiles.FullName -join "; ")
        throw "Bundle contains banned private/job files: $Found"
    }

    $Resolved = Get-Content (Join-Path $BundleDir "python-resolved.txt") -Raw
    foreach ($Pinned in @("paddlepaddle==3.3.0", "paddleocr==3.7.0", "paddlex==3.7.2", "pypdfium2==5.12.1")) {
        if ($Resolved -notmatch [regex]::Escape($Pinned)) {
            throw "Packaged resolved dependency inventory is missing exact pin: $Pinned"
        }
    }
}

function New-OcrSmokeImage {
    Add-Type -AssemblyName System.Drawing
    $Bitmap = New-Object System.Drawing.Bitmap 1600, 420
    $Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
    $Font = New-Object System.Drawing.Font("Arial", 120, [System.Drawing.FontStyle]::Bold)
    $Brush = [System.Drawing.Brushes]::Black
    try {
        $Graphics.Clear([System.Drawing.Color]::White)
        $Graphics.DrawString("LAW RAG 2026", $Font, $Brush, 80, 100)
        $Bitmap.Save($SmokeOcrImage, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $Font.Dispose()
        $Graphics.Dispose()
        $Bitmap.Dispose()
    }
}

Assert-BundleContents

& $Exe --diagnose --json
if ($LASTEXITCODE -ne 0) {
    throw "Packaged runtime diagnostics failed with exit code $LASTEXITCODE"
}

$PreviousHttpProxy = $env:HTTP_PROXY
$PreviousHttpsProxy = $env:HTTPS_PROXY
$PreviousAllProxy = $env:ALL_PROXY
$PreviousNoProxy = $env:NO_PROXY
try {
    $env:HTTP_PROXY = "http://127.0.0.1:9"
    $env:HTTPS_PROXY = "http://127.0.0.1:9"
    $env:ALL_PROXY = "http://127.0.0.1:9"
    $env:NO_PROXY = "127.0.0.1,localhost"

    & $Exe --diagnose-ocr-runtime
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged OCR runtime diagnostic failed with exit code $LASTEXITCODE"
    }

    & $Exe --diagnose-ocr-models
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged OCR model integrity diagnostic failed with exit code $LASTEXITCODE"
    }

    New-OcrSmokeImage
    $InferenceOutput = (& $Exe --diagnose-ocr-inference $SmokeOcrImage 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged offline OCR inference failed with exit code $LASTEXITCODE. Output: $InferenceOutput"
    }
    if ($InferenceOutput -notmatch "LAW" -or $InferenceOutput -notmatch "2026") {
        throw "Packaged offline OCR inference did not recognize the fixed smoke text. Output: $InferenceOutput"
    }
}
finally {
    if ($null -eq $PreviousHttpProxy) { Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue } else { $env:HTTP_PROXY = $PreviousHttpProxy }
    if ($null -eq $PreviousHttpsProxy) { Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue } else { $env:HTTPS_PROXY = $PreviousHttpsProxy }
    if ($null -eq $PreviousAllProxy) { Remove-Item Env:ALL_PROXY -ErrorAction SilentlyContinue } else { $env:ALL_PROXY = $PreviousAllProxy }
    if ($null -eq $PreviousNoProxy) { Remove-Item Env:NO_PROXY -ErrorAction SilentlyContinue } else { $env:NO_PROXY = $PreviousNoProxy }
    Remove-Item $SmokeOcrImage -Force -ErrorAction SilentlyContinue
}
Assert-BundleContents

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

    $Upload = Invoke-RestMethod -Uri "$BaseUrl/api/documents" -Method Post -Form @{ file = Get-Item $SmokePdf } -TimeoutSec 15
    if (-not $Upload.job_id -or $Upload.page_count -ne 1) {
        throw "Packaged native PDF upload did not return a one-page job."
    }
    $Rendered = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/documents/$($Upload.job_id)/source/pages/1" -TimeoutSec 15
    if ($Rendered.StatusCode -ne 200 -or $Rendered.Headers["Content-Type"] -notmatch "image/png") {
        throw "Packaged PDFium source-page rendering did not return image/png."
    }

    Write-Host "[Law-Rag] Packaged OCR runtime + verified models + offline real inference, all four UI routes, API, native PDF ingestion, PDFium rendering, and privacy scan passed."
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
    Remove-Item $SmokeOcrImage -Force -ErrorAction SilentlyContinue
}
