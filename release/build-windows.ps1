param(
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $RepoRoot "backend"
$Frontend = Join-Path $RepoRoot "frontend"
$BuildRoot = Join-Path $PSScriptRoot ".build"
$DistRoot = Join-Path $PSScriptRoot "dist"
$WorkRoot = Join-Path $PSScriptRoot "work"

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Label)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

$PythonVersion = (& python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
if (-not $PythonVersion.StartsWith("3.12.")) {
    throw "Stage 11D requires CPython 3.12.x; found $PythonVersion"
}

Invoke-Checked { node --version } "Node.js check"
Invoke-Checked { npm --version } "npm check"

if (-not $SkipDependencyInstall) {
    Invoke-Checked { python -m pip install -r (Join-Path $Backend "requirements-release-base.txt") } "Base release dependency install"
    Invoke-Checked { python -m pip install -r (Join-Path $Backend "requirements-release-build.txt") } "PyInstaller build dependency install"
}

if (Test-Path $BuildRoot) { Remove-Item $BuildRoot -Recurse -Force }
if (Test-Path $DistRoot) { Remove-Item $DistRoot -Recurse -Force }
if (Test-Path $WorkRoot) { Remove-Item $WorkRoot -Recurse -Force }
New-Item -ItemType Directory -Path $BuildRoot | Out-Null

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
    Invoke-Checked { python -m app.release_assets_cli --output-dir $BuildRoot } "Public legal/retrieval release asset build"
}
finally {
    Pop-Location
}

python -m pip freeze --all | Sort-Object | Set-Content -Encoding UTF8 (Join-Path $BuildRoot "python-resolved.txt")
python -c "import json,platform,sys; print(json.dumps({'python':sys.version,'implementation':platform.python_implementation(),'platform':platform.platform()}, sort_keys=True))" | Set-Content -Encoding UTF8 (Join-Path $BuildRoot "python-runtime.json")

Push-Location $RepoRoot
try {
    Invoke-Checked {
        pyinstaller --noconfirm --clean --distpath $DistRoot --workpath $WorkRoot (Join-Path $PSScriptRoot "law_rag.spec")
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
Write-Host "[Law-Rag] No API keys, user runtime data, OCR weights, or BGE weights were bundled."
