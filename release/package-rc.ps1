param(
    [string]$Config = (Join-Path $PSScriptRoot "rc-config.json"),
    [string]$Output = (Join-Path $PSScriptRoot "rc"),
    [string]$BundleDir = (Join-Path $PSScriptRoot "dist\Law-Rag"),
    [string]$PythonPath = (Join-Path $PSScriptRoot ".build-venv\Scripts\python.exe")
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $RepoRoot "backend"

if (-not (Test-Path $PythonPath -PathType Leaf)) {
    throw "RC packaging Python environment is missing: $PythonPath"
}
if (-not (Test-Path (Join-Path $BundleDir "Law-Rag.exe") -PathType Leaf)) {
    throw "RC onedir bundle is missing Law-Rag.exe: $BundleDir"
}
if (-not (Test-Path $Config -PathType Leaf)) {
    throw "RC packaging config is missing: $Config"
}

$PythonPath = (Resolve-Path $PythonPath).Path
$BundleDir = (Resolve-Path $BundleDir).Path
$Config = (Resolve-Path $Config).Path
$Output = [IO.Path]::GetFullPath($Output)

Push-Location $Backend
try {
    $env:PYTHONPATH = "."
    & $PythonPath -m app.rc_archive_cli --bundle-dir $BundleDir --config $Config --output-dir $Output
    if ($LASTEXITCODE -ne 0) {
        throw "Portable RC archive generation failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$Manifest = Join-Path $Output "RC-MANIFEST.json"
$Sums = Join-Path $Output "SHA256SUMS.txt"
if (-not (Test-Path $Manifest) -or -not (Test-Path $Sums)) {
    throw "RC packaging did not produce RC-MANIFEST.json and SHA256SUMS.txt"
}

$ManifestData = Get-Content $Manifest -Raw | ConvertFrom-Json
$Zip = Join-Path $Output $ManifestData.artifact.filename
if (-not (Test-Path $Zip)) {
    throw "RC packaging did not produce the manifest-declared ZIP: $($ManifestData.artifact.filename)"
}

Write-Host "[Law-Rag] Portable RC created from bundle: $BundleDir"
Write-Host "[Law-Rag] Portable RC created: $Zip"
Write-Host "[Law-Rag] SHA-256: $($ManifestData.artifact.sha256)"
Write-Host "[Law-Rag] Publication state remains NOT_PUBLISHED."
