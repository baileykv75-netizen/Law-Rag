param(
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $RepoRoot "backend"
$Frontend = Join-Path $RepoRoot "frontend"
$BuildRoot = Join-Path $PSScriptRoot ".build"
$BuildVenv = Join-Path $PSScriptRoot ".build-venv"
$DistRoot = Join-Path $PSScriptRoot "dist"
$WorkRoot = Join-Path $PSScriptRoot "work"
$LockFile = Join-Path $Backend "requirements-release-lock-windows.txt"
$NoticeRoot = Join-Path $BuildRoot "THIRD-PARTY-NOTICES"
$ReleaseMetadata = Join-Path $BuildRoot "release-metadata.json"
$SmokePdf = Join-Path $BuildRoot "smoke-native.pdf"

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Label)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

$PythonVersion = (& python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
if ($PythonVersion -ne "3.12.10") {
    throw "Stage 11D release build requires CPython 3.12.10 exactly; found $PythonVersion"
}

$NodeVersion = (& node --version).Trim()
if ($NodeVersion -ne "v22.23.2") {
    throw "Stage 11D release build requires Node.js v22.23.2 exactly; found $NodeVersion"
}
$NpmVersion = (& npm --version).Trim()
if ($NpmVersion -ne "10.9.8") {
    throw "Stage 11D release build requires npm 10.9.8 exactly; found $NpmVersion"
}

$SourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $SourceSha -notmatch '^[0-9a-fA-F]{40}$') {
    throw "Could not resolve the full source commit SHA for release metadata."
}

if (Test-Path $BuildRoot) { Remove-Item $BuildRoot -Recurse -Force }
if (Test-Path $BuildVenv) { Remove-Item $BuildVenv -Recurse -Force }
if (Test-Path $DistRoot) { Remove-Item $DistRoot -Recurse -Force }
if (Test-Path $WorkRoot) { Remove-Item $WorkRoot -Recurse -Force }
New-Item -ItemType Directory -Path $BuildRoot | Out-Null

if ($SkipDependencyInstall) {
    throw "-SkipDependencyInstall is not supported for the reproducible Stage 11D build; use the exact isolated build environment."
}

Invoke-Checked { python -m venv $BuildVenv } "Isolated release virtualenv creation"
$ReleasePython = Join-Path $BuildVenv "Scripts\python.exe"
Invoke-Checked { & $ReleasePython -m pip install --upgrade pip==26.2.1 } "Release pip pin"
Invoke-Checked { & $ReleasePython -m pip install --no-deps -r $LockFile } "Exact Windows release lock install"
Invoke-Checked { & $ReleasePython -m pip check } "Exact Windows release dependency consistency check"

Push-Location $Frontend
try {
    Invoke-Checked { npm ci } "Locked frontend dependency install"
    Invoke-Checked { npm run build } "Frontend production build"
    $FrontendLicenses = Join-Path $Frontend "dist\third-party-frontend-licenses.json"
    if (-not (Test-Path $FrontendLicenses)) {
        throw "Vite did not emit third-party-frontend-licenses.json"
    }
}
finally {
    Pop-Location
}

Push-Location $Backend
try {
    $env:PYTHONPATH = "."
    Invoke-Checked { & $ReleasePython -m app.release_assets_cli --output-dir $BuildRoot } "Public legal/retrieval release asset build"
    Invoke-Checked { & $ReleasePython -m app.release_notices_cli --lock $LockFile --output-dir $NoticeRoot } "Exact installed Python license/NOTICE collection"
    Invoke-Checked {
        & $ReleasePython -m app.release_metadata_cli --source-sha $SourceSha --node-version $NodeVersion --npm-version $NpmVersion --output $ReleaseMetadata
    } "Release reproducibility metadata generation"
    Invoke-Checked { & $ReleasePython -m app.release_smoke_fixture_cli --output $SmokePdf } "Synthetic native PDF smoke fixture generation"
}
finally {
    Pop-Location
}

$PythonNoticeReport = Join-Path $NoticeRoot "python-third-party-notices.json"
if (-not (Test-Path $PythonNoticeReport)) {
    throw "Python third-party notice collector did not emit its review report"
}
if (-not (Test-Path $ReleaseMetadata)) {
    throw "Release reproducibility metadata was not generated"
}
if (-not (Test-Path $SmokePdf)) {
    throw "Native PDF smoke fixture was not generated"
}

& $ReleasePython -m pip freeze --all | Sort-Object | Set-Content -Encoding UTF8 (Join-Path $BuildRoot "python-resolved.txt")
& $ReleasePython -c "import json,platform,sys; print(json.dumps({'python':sys.version,'implementation':platform.python_implementation(),'platform':platform.platform()}, sort_keys=True))" | Set-Content -Encoding UTF8 (Join-Path $BuildRoot "python-runtime.json")

Push-Location $RepoRoot
try {
    Invoke-Checked {
        & $ReleasePython -m PyInstaller --noconfirm --clean --distpath $DistRoot --workpath $WorkRoot (Join-Path $PSScriptRoot "law_rag.spec")
    } "PyInstaller onedir build"
}
finally {
    Pop-Location
}

$Bundle = Join-Path $DistRoot "Law-Rag"
if (-not (Test-Path (Join-Path $Bundle "Law-Rag.exe"))) {
    throw "PyInstaller did not produce Law-Rag.exe"
}

Copy-Item (Join-Path $PSScriptRoot "README-WINDOWS.md") (Join-Path $Bundle "README-WINDOWS.md") -Force
Copy-Item (Join-Path $RepoRoot ".env.example") (Join-Path $Bundle "config.env.example") -Force
Copy-Item (Join-Path $BuildRoot "python-resolved.txt") (Join-Path $Bundle "python-resolved.txt") -Force
Copy-Item (Join-Path $BuildRoot "python-runtime.json") (Join-Path $Bundle "python-runtime.json") -Force

Write-Host ""
Write-Host "[Law-Rag] Windows onedir bundle created at: $Bundle"
Write-Host "[Law-Rag] Source commit: $SourceSha"
Write-Host "[Law-Rag] Build runtime: CPython $PythonVersion / Node $NodeVersion / npm $NpmVersion"
Write-Host "[Law-Rag] Exact Python notices and Vite bundled dependency licenses were generated for review."
Write-Host "[Law-Rag] No API keys, user runtime data, OCR weights, or BGE weights were bundled."
