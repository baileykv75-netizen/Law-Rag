param(
    [string]$BundleDir = (Join-Path $PSScriptRoot "dist\Law-Rag"),
    [int]$Port = 8795
)

$ErrorActionPreference = "Stop"
$Exe = Join-Path $BundleDir "Law-Rag.exe"
$SmokeRuntime = Join-Path $env:RUNNER_TEMP ("law-rag-stage14-7-runtime-" + [guid]::NewGuid().ToString("N"))
$SmokeDocx = Join-Path $env:RUNNER_TEMP ("law-rag-stage14-7-" + [guid]::NewGuid().ToString("N") + ".docx")
$SmokeImage = Join-Path $env:RUNNER_TEMP ("law-rag-stage14-7-" + [guid]::NewGuid().ToString("N") + ".png")

$PreviousRuntime = $env:LAW_RAG_RUNTIME_DIR
$PreviousDeepSeekKey = $env:DEEPSEEK_API_KEY
$PreviousDeepSeekBase = $env:DEEPSEEK_BASE_URL
$PreviousHttpProxy = $env:HTTP_PROXY
$PreviousHttpsProxy = $env:HTTPS_PROXY
$PreviousAllProxy = $env:ALL_PROXY
$PreviousNoProxy = $env:NO_PROXY

function Restore-EnvironmentValue([string]$Name, [string]$Value) {
    if ($null -eq $Value) {
        Remove-Item ("Env:" + $Name) -ErrorAction SilentlyContinue
    }
    else {
        Set-Item ("Env:" + $Name) $Value
    }
}

function New-Stage14DocxFixture {
    $Root = Join-Path $env:RUNNER_TEMP ("law-rag-stage14-7-docx-src-" + [guid]::NewGuid().ToString("N"))
    $ZipPath = $SmokeDocx + ".zip"
    try {
        New-Item -ItemType Directory -Path (Join-Path $Root "word") -Force | Out-Null
        $Utf8 = New-Object System.Text.UTF8Encoding($false)
        $ContentTypes = @'
<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
'@
        $DocumentXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>设备采购合同</w:t></w:r></w:p>
    <w:p><w:r><w:t>第一条 服务范围</w:t></w:r></w:p>
    <w:p><w:r><w:t>甲方委托乙方提供设备采购与安装服务。</w:t></w:r></w:p>
    <w:ins w:id="1"><w:p><w:r><w:t>合同总价为人民币100000元，乙方应于2026年9月1日前交付。</w:t></w:r></w:p></w:ins>
    <w:sectPr/>
  </w:body>
</w:document>
'@
        [System.IO.File]::WriteAllText((Join-Path $Root "[Content_Types].xml"), $ContentTypes, $Utf8)
        [System.IO.File]::WriteAllText((Join-Path $Root "word\document.xml"), $DocumentXml, $Utf8)
        Compress-Archive -Path (Join-Path $Root "*") -DestinationPath $ZipPath -CompressionLevel Optimal -Force
        Move-Item -Path $ZipPath -Destination $SmokeDocx -Force
    }
    finally {
        if (Test-Path $Root) { Remove-Item $Root -Recurse -Force }
        if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    }
}

function New-Stage14OcrImage {
    Add-Type -AssemblyName System.Drawing
    $Bitmap = New-Object System.Drawing.Bitmap 1600, 420
    $Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
    $Font = New-Object System.Drawing.Font("Arial", 120, [System.Drawing.FontStyle]::Bold)
    try {
        $Graphics.Clear([System.Drawing.Color]::White)
        $Graphics.DrawString("LAW RAG 2026", $Font, [System.Drawing.Brushes]::Black, 80, 100)
        $Bitmap.Save($SmokeImage, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $Font.Dispose()
        $Graphics.Dispose()
        $Bitmap.Dispose()
    }
}

function Assert-PackagedHomeDocxPicker {
    $Assets = Join-Path $BundleDir "_internal\frontend-dist\assets"
    $Scripts = Get-ChildItem -Path $Assets -Recurse -File -Filter "*.js" -ErrorAction Stop
    if (-not $Scripts) { throw "Packaged frontend contains no JavaScript assets." }
    $Joined = ($Scripts | ForEach-Object { Get-Content $_.FullName -Raw }) -join "`n"
    foreach ($Expected in @(
        ".docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )) {
        if (-not $Joined.Contains($Expected)) {
            throw "Packaged Home asset does not expose the Stage 14 DOCX picker contract: $Expected"
        }
    }
    Write-Host "[Law-Rag] Packaged Home DOCX picker assets: OK"
}

function Wait-ForServer([System.Diagnostics.Process]$Process, [string]$BaseUrl) {
    for ($Attempt = 1; $Attempt -le 40; $Attempt++) {
        if ($Process.HasExited) {
            throw "Law-Rag.exe exited before Stage 14.7 smoke became ready. Exit code: $($Process.ExitCode)"
        }
        try {
            $Health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -TimeoutSec 2
            if ($Health.status -eq "ok") { return }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Law-Rag packaged server did not become ready on $BaseUrl"
}

function Wait-ForPipeline([string]$BaseUrl, [string]$JobId) {
    for ($Attempt = 1; $Attempt -le 80; $Attempt++) {
        $Pipeline = Invoke-RestMethod -Uri "$BaseUrl/api/documents/$JobId/pipeline" -TimeoutSec 5
        if ($Pipeline.status -in @("PAUSED_BEFORE_PROVIDER", "FAILED", "WAITING_CONFIGURATION", "CANCELLED", "COMPLETE")) {
            return $Pipeline
        }
        Start-Sleep -Milliseconds 250
    }
    throw "DOCX Pipeline did not reach the expected provider boundary."
}

if (-not (Test-Path $Exe)) {
    throw "Law-Rag.exe not found at $Exe"
}

New-Stage14DocxFixture
New-Stage14OcrImage
Assert-PackagedHomeDocxPicker

$env:LAW_RAG_RUNTIME_DIR = $SmokeRuntime
$env:DEEPSEEK_API_KEY = "law-rag-stage14-7-synthetic-configured-key"
$env:DEEPSEEK_BASE_URL = "http://127.0.0.1:9"
$env:HTTP_PROXY = "http://127.0.0.1:9"
$env:HTTPS_PROXY = "http://127.0.0.1:9"
$env:ALL_PROXY = "http://127.0.0.1:9"
$env:NO_PROXY = "127.0.0.1,localhost"

$Process = Start-Process -FilePath $Exe -ArgumentList @("--no-browser", "--port", "$Port") -PassThru
try {
    $BaseUrl = "http://127.0.0.1:$Port"
    Wait-ForServer $Process $BaseUrl

    $DocxUpload = Invoke-RestMethod -Uri "$BaseUrl/api/documents" -Method Post -Form @{ file = Get-Item $SmokeDocx } -TimeoutSec 30
    if (-not $DocxUpload.job_id) { throw "Packaged DOCX upload did not return a job id." }
    if ($DocxUpload.document_kind -ne "docx" -or $DocxUpload.page_count -ne 0) {
        throw "Packaged DOCX upload did not preserve structural/non-paginated identity."
    }
    if ($DocxUpload.evidence_count -lt 4) {
        throw "Packaged DOCX upload did not preserve expected structural Evidence."
    }
    if (-not $DocxUpload.warnings -or $DocxUpload.warnings.Count -lt 1) {
        throw "Tracked-change DOCX smoke fixture did not surface a source warning."
    }

    $EvidencePath = Join-Path $SmokeRuntime ("jobs\" + $DocxUpload.job_id + "\evidence.json")
    if (-not (Test-Path $EvidencePath)) { throw "Packaged DOCX SourceEvidenceArtifact was not persisted." }
    $Evidence = Get-Content $EvidencePath -Raw | ConvertFrom-Json
    if ($Evidence.source_document.document_kind -ne "docx") {
        throw "Persisted DOCX Source Evidence lost source-document identity."
    }
    if (-not $Evidence.evidence -or $Evidence.evidence[0].source_anchor.kind -notlike "DOCX_*") {
        throw "Persisted DOCX Source Evidence lost typed structural anchors."
    }
    if (-not $Evidence.warnings -or $Evidence.warnings.Count -lt 1) {
        throw "Persisted DOCX Source Evidence lost source warnings."
    }

    $PipelineBody = @{
        as_of = "2026-08-19"
        use_semantic = $false
        provider_mode = "REQUIRE_APPROVAL"
    } | ConvertTo-Json
    Invoke-RestMethod -Uri "$BaseUrl/api/documents/$($DocxUpload.job_id)/pipeline" -Method Post -ContentType "application/json" -Body $PipelineBody -TimeoutSec 15 | Out-Null
    $Pipeline = Wait-ForPipeline $BaseUrl $DocxUpload.job_id
    if ($Pipeline.status -ne "PAUSED_BEFORE_PROVIDER" -or $Pipeline.current_stage -ne "AUDIT_PLAN" -or $Pipeline.progress_percent -ne 48 -or $Pipeline.failure_code -ne "PROVIDER_APPROVAL_REQUIRED") {
        throw ("Packaged DOCX Pipeline did not stop at the Stage 13 provider boundary. Observed: " + ($Pipeline | ConvertTo-Json -Depth 8 -Compress))
    }
    $OcrStage = $Pipeline.stages | Where-Object { $_.stage -eq "OCR" }
    $StructureStage = $Pipeline.stages | Where-Object { $_.stage -eq "STRUCTURE" }
    $RulesStage = $Pipeline.stages | Where-Object { $_.stage -eq "RULES" }
    if ($OcrStage.state -ne "SKIPPED" -or $StructureStage.state -ne "COMPLETE" -or $RulesStage.state -ne "COMPLETE") {
        throw "Packaged DOCX Pipeline did not preserve native-DOCX OCR skip + real local STRUCTURE/RULES semantics."
    }
    foreach ($Artifact in @("contract.json", "audit-rules.json")) {
        $ArtifactPath = Join-Path $SmokeRuntime ("jobs\" + $DocxUpload.job_id + "\" + $Artifact)
        if (-not (Test-Path $ArtifactPath)) { throw "Packaged DOCX Pipeline did not create $Artifact" }
    }

    $ImageUpload = Invoke-RestMethod -Uri "$BaseUrl/api/documents" -Method Post -Form @{ file = Get-Item $SmokeImage } -TimeoutSec 30
    if (-not $ImageUpload.job_id -or $ImageUpload.document_kind -ne "image" -or $ImageUpload.ocr_required_pages -ne 1) {
        throw "Packaged image upload did not route to OCR."
    }
    $Ocr = Invoke-RestMethod -Uri "$BaseUrl/api/documents/$($ImageUpload.job_id)/ocr" -Method Post -TimeoutSec 120
    if ($Ocr.status -ne "complete" -or $Ocr.ocr_pages_complete -ne 1) {
        throw ("Packaged image OCR did not complete: " + ($Ocr | ConvertTo-Json -Depth 8 -Compress))
    }
    $Recognized = (($Ocr.pages | ForEach-Object { $_.text }) -join " ")
    if ($Recognized -notmatch "LAW" -or $Recognized -notmatch "2026") {
        throw "Packaged image /ocr path did not recognize fixed smoke text. Observed: $Recognized"
    }

    Write-Host "[Law-Rag] Stage 14.7 packaged DOCX Home/Pipeline/provider-boundary and image OCR API smoke passed with outbound network blocked."
}
finally {
    if (-not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        $Process.WaitForExit()
    }
    Restore-EnvironmentValue "LAW_RAG_RUNTIME_DIR" $PreviousRuntime
    Restore-EnvironmentValue "DEEPSEEK_API_KEY" $PreviousDeepSeekKey
    Restore-EnvironmentValue "DEEPSEEK_BASE_URL" $PreviousDeepSeekBase
    Restore-EnvironmentValue "HTTP_PROXY" $PreviousHttpProxy
    Restore-EnvironmentValue "HTTPS_PROXY" $PreviousHttpsProxy
    Restore-EnvironmentValue "ALL_PROXY" $PreviousAllProxy
    Restore-EnvironmentValue "NO_PROXY" $PreviousNoProxy
    foreach ($Path in @($SmokeRuntime, $SmokeDocx, $SmokeImage)) {
        if (Test-Path $Path) {
            Remove-Item $Path -Recurse -Force
        }
    }
}
