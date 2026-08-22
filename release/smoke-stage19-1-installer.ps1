param(
    [string]$InstallerPath = (Join-Path $PSScriptRoot "installer-dist\Law-Rag-0.8.0-rc2-windows-x64-setup.exe")
)

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Stage 19.1 installer smoke is Windows-only." }
$InstallerPath = (Resolve-Path $InstallerPath).Path
$Sandbox = Join-Path $env:RUNNER_TEMP ("law-rag-stage19-1-" + [guid]::NewGuid().ToString("N"))
$InstallDir = Join-Path $Sandbox "Programs\Law-Rag"
$FakeLocalAppData = Join-Path $Sandbox "LocalAppData"
$ExpectedRuntime = Join-Path $FakeLocalAppData "Law-Rag\runtime"
$Sentinel = Join-Path $ExpectedRuntime "installer-preserve-sentinel.txt"
$InstallLog = Join-Path $Sandbox "install.log"
$ReinstallLog = Join-Path $Sandbox "reinstall.log"
$UninstallLog = Join-Path $Sandbox "uninstall.log"

function Invoke-CheckedProcess {
    param([string]$FilePath, [string[]]$Arguments, [string]$Label)
    $Process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -PassThru -Wait
    if ($Process.ExitCode -ne 0) {
        throw "$Label failed with exit code $($Process.ExitCode)."
    }
}

function Install-LawRag {
    param([string]$LogPath)
    Invoke-CheckedProcess -FilePath $InstallerPath -Label "Law-Rag installer" -Arguments @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/DIR=`"$InstallDir`"",
        "/LOG=`"$LogPath`""
    )
}

$PreviousLocalAppData = $env:LOCALAPPDATA
$PreviousRuntime = $env:LAW_RAG_RUNTIME_DIR
$PreviousDeepSeek = $env:DEEPSEEK_API_KEY
$PreviousKimi = $env:MOONSHOT_API_KEY

New-Item -ItemType Directory -Path $Sandbox | Out-Null
try {
    $env:LOCALAPPDATA = $FakeLocalAppData
    Remove-Item Env:LAW_RAG_RUNTIME_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:MOONSHOT_API_KEY -ErrorAction SilentlyContinue

    Install-LawRag -LogPath $InstallLog

    $InstalledExe = Join-Path $InstallDir "Law-Rag.exe"
    $InstalledMarker = Join-Path $InstallDir ".law-rag-installed"
    $Uninstaller = Join-Path $InstallDir "unins000.exe"
    if (-not (Test-Path $InstalledExe)) { throw "Installed Law-Rag.exe is missing." }
    if (-not (Test-Path $InstalledMarker)) { throw "Installed-distribution marker is missing." }
    if (-not (Test-Path $Uninstaller)) { throw "Per-user uninstaller is missing." }
    if (Test-Path (Join-Path $InstallDir "runtime")) {
        throw "Installer incorrectly owns an adjacent runtime directory."
    }

    $LayoutRaw = (& $InstalledExe --diagnose-installation-layout | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Installed layout diagnostic failed with exit code $LASTEXITCODE.`n$LayoutRaw" }
    $Layout = $LayoutRaw | ConvertFrom-Json
    if (-not $Layout.installed) { throw "Installed executable did not recognize the installation marker." }
    if ($Layout.runtime_source -ne "INSTALLED_MARKER") { throw "Installed runtime source was '$($Layout.runtime_source)', expected INSTALLED_MARKER." }
    if (-not $Layout.user_data_separated_from_app) { throw "Installed runtime was not separated from application binaries." }
    if ($Layout.network_used) { throw "Installation layout diagnostic unexpectedly reported network use." }
    if ([IO.Path]::GetFullPath([string]$Layout.runtime_dir) -ne [IO.Path]::GetFullPath($ExpectedRuntime)) {
        throw "Installed runtime mismatch. Expected '$ExpectedRuntime', got '$($Layout.runtime_dir)'."
    }

    $ReportRaw = (& $InstalledExe --diagnose-report-export-runtime | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Installed Stage 18.2 report renderer diagnostic failed.`n$ReportRaw" }
    $Report = $ReportRaw | ConvertFrom-Json
    if (-not $Report.ready -or $Report.network_used) {
        throw "Installed report renderer diagnostic was not provider-free and ready."
    }

    $CorpusRaw = (& $InstalledExe --diagnose-corpus --json | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Installed packaged corpus diagnostic failed.`n$CorpusRaw" }
    $Corpus = $CorpusRaw | ConvertFrom-Json
    if (-not $Corpus.ready) { throw "Installed packaged corpus baseline is not ready." }

    New-Item -ItemType Directory -Path $ExpectedRuntime -Force | Out-Null
    "preserve-me" | Set-Content -Encoding UTF8 $Sentinel

    Install-LawRag -LogPath $ReinstallLog
    if (-not (Test-Path $Sentinel)) { throw "In-place reinstall deleted user runtime data." }
    if (-not (Test-Path $InstalledExe)) { throw "Law-Rag.exe disappeared after in-place reinstall." }

    Invoke-CheckedProcess -FilePath $Uninstaller -Label "Law-Rag uninstaller" -Arguments @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/LOG=`"$UninstallLog`""
    )

    if (Test-Path $InstalledExe) { throw "Uninstall left Law-Rag.exe installed." }
    if (Test-Path $InstalledMarker) { throw "Uninstall left the installation marker behind." }
    if (-not (Test-Path $Sentinel)) { throw "Uninstall deleted user runtime data; this is forbidden." }

    Write-Host "[Law-Rag] Stage 19.1 installer smoke PASS"
    Write-Host "[Law-Rag] per-user application install PASS"
    Write-Host "[Law-Rag] installed LocalAppData runtime separation PASS"
    Write-Host "[Law-Rag] installed Stage 18.2 renderer + corpus diagnostics PASS"
    Write-Host "[Law-Rag] in-place reinstall preserves runtime PASS"
    Write-Host "[Law-Rag] uninstall removes app but preserves runtime PASS"
    Write-Host "[Law-Rag] provider/network calls: 0"
}
finally {
    if ($null -eq $PreviousLocalAppData) { Remove-Item Env:LOCALAPPDATA -ErrorAction SilentlyContinue } else { $env:LOCALAPPDATA = $PreviousLocalAppData }
    if ($null -eq $PreviousRuntime) { Remove-Item Env:LAW_RAG_RUNTIME_DIR -ErrorAction SilentlyContinue } else { $env:LAW_RAG_RUNTIME_DIR = $PreviousRuntime }
    if ($null -eq $PreviousDeepSeek) { Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue } else { $env:DEEPSEEK_API_KEY = $PreviousDeepSeek }
    if ($null -eq $PreviousKimi) { Remove-Item Env:MOONSHOT_API_KEY -ErrorAction SilentlyContinue } else { $env:MOONSHOT_API_KEY = $PreviousKimi }
    if (Test-Path $Sandbox) { Remove-Item $Sandbox -Recurse -Force -ErrorAction SilentlyContinue }
}
