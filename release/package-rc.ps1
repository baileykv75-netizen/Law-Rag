$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $RepoRoot "backend"
$ReleasePython = Join-Path $PSScriptRoot ".build-venv\Scripts\python.exe"
$Bundle = Join-Path $PSScriptRoot "dist\Law-Rag"
$Config = Join-Path $PSScriptRoot "rc-config.json"
$Output = Join-Path $PSScriptRoot "rc"

if (-not (Test-Path $ReleasePython)) {
    throw "Stage 11D isolated release environment is missing. Run release/build-windows.ps1 first."
}
if (-not (Test-Path (Join-Path $Bundle "Law-Rag.exe"))) {
    throw "Stage 11D onedir bundle is missing. Run release/build-windows.ps1 first."
}

Push-Location $Backend
try {
    $env:PYTHONPATH = "."
    & $ReleasePython -m app.rc_archive_cli --bundle-dir $Bundle --config $Config --output-dir $Output
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

Write-Host "[Law-Rag] Portable RC created: $Zip"
Write-Host "[Law-Rag] SHA-256: $($ManifestData.artifact.sha256)"
Write-Host "[Law-Rag] Publication state remains NOT_PUBLISHED."
