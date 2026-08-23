param(
    [string]$InstallerPath = (Join-Path $PSScriptRoot "installer-dist\Law-Rag-0.8.0-rc2-windows-x64-setup.exe"),
    [string]$ExpectedSourceSha = "",
    [string]$ExpectedReleaseLabel = ""
)

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Stage 19.1 installer smoke is Windows-only." }
if ($ExpectedSourceSha -and $ExpectedSourceSha -notmatch '^[0-9a-fA-F]{40}$') {
    throw "ExpectedSourceSha must be a full 40-character Git SHA when supplied."
}
$ExpectedSourceSha = $ExpectedSourceSha.ToLowerInvariant()
$InstallerPath = (Resolve-Path $InstallerPath).Path
if ($ExpectedReleaseLabel -and -not ([IO.Path]::GetFileName($InstallerPath)).Contains($ExpectedReleaseLabel)) {
    throw "Installer filename does not contain expected release label '$ExpectedReleaseLabel'."
}
$Sandbox = Join-Path $env:RUNNER_TEMP ("law-rag-stage19-1-" + [guid]::NewGuid().ToString("N"))
$InstallDir = Join-Path $Sandbox "Programs\Law-Rag"
$FakeLocalAppData = Join-Path $Sandbox "LocalAppData"
$ExpectedRuntime = Join-Path $FakeLocalAppData "Law-Rag\runtime"
$Sentinel = Join-Path $ExpectedRuntime "installer-preserve-sentinel.txt"
$InstallLog = Join-Path $Sandbox "install.log"
$ReinstallLog = Join-Path $Sandbox "reinstall.log"
$UninstallLog = Join-Path $Sandbox "uninstall.log"

function Invoke-CheckedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Label,
        [int]$TimeoutSeconds = 300
    )

    Write-Host "[Law-Rag][Stage19.1] START $Label (timeout=${TimeoutSeconds}s)"
    $StartedAt = Get-Date
    $Process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -PassThru
    if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        throw "$Label timed out after $TimeoutSeconds seconds."
    }
    $Process.WaitForExit()
    $Elapsed = [Math]::Round(((Get-Date) - $StartedAt).TotalSeconds, 1)
    if ($Process.ExitCode -ne 0) {
        throw "$Label failed with exit code $($Process.ExitCode) after ${Elapsed}s."
    }
    Write-Host "[Law-Rag][Stage19.1] PASS  $Label (${Elapsed}s)"
}

function Invoke-CapturedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Label,
        [int]$TimeoutSeconds = 180
    )

    $Token = [guid]::NewGuid().ToString("N")
    $StdoutPath = Join-Path $Sandbox ("diagnostic-$Token.stdout.txt")
    $StderrPath = Join-Path $Sandbox ("diagnostic-$Token.stderr.txt")
    Write-Host "[Law-Rag][Stage19.1] START $Label (timeout=${TimeoutSeconds}s)"
    $StartedAt = Get-Date
    try {
        $Process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -PassThru
        if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            throw "$Label timed out after $TimeoutSeconds seconds."
        }
        $Process.WaitForExit()
        $Stdout = if (Test-Path $StdoutPath) { Get-Content $StdoutPath -Raw } else { "" }
        $Stderr = if (Test-Path $StderrPath) { Get-Content $StderrPath -Raw } else { "" }
        $Elapsed = [Math]::Round(((Get-Date) - $StartedAt).TotalSeconds, 1)
        if ($Process.ExitCode -ne 0) {
            throw "$Label failed with exit code $($Process.ExitCode) after ${Elapsed}s.`nSTDOUT:`n$Stdout`nSTDERR:`n$Stderr"
        }
        Write-Host "[Law-Rag][Stage19.1] PASS  $Label (${Elapsed}s)"
        return $Stdout
    }
    finally {
        Remove-Item $StdoutPath -Force -ErrorAction SilentlyContinue
        Remove-Item $StderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Install-LawRag {
    param([string]$LogPath, [string]$Label)
    Invoke-CheckedProcess -FilePath $InstallerPath -Label $Label -TimeoutSeconds 420 -Arguments @(
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

    Install-LawRag -LogPath $InstallLog -Label "initial per-user install"

    $InstalledExe = Join-Path $InstallDir "Law-Rag.exe"
    $InstalledMarker = Join-Path $InstallDir ".law-rag-installed"
    $Uninstaller = Join-Path $InstallDir "unins000.exe"
    if (-not (Test-Path $InstalledExe)) { throw "Installed Law-Rag.exe is missing." }
    if (-not (Test-Path $InstalledMarker)) { throw "Installed-distribution marker is missing." }
    if (-not (Test-Path $Uninstaller)) { throw "Per-user uninstaller is missing." }
    if (Test-Path (Join-Path $InstallDir "runtime")) {
        throw "Installer incorrectly owns an adjacent runtime directory."
    }

    if ($ExpectedSourceSha) {
        $InstalledMetadataPath = Join-Path $InstallDir "_internal\release\release-metadata.json"
        if (-not (Test-Path $InstalledMetadataPath -PathType Leaf)) {
            throw "Installed release metadata is missing."
        }
        $InstalledMetadata = Get-Content $InstalledMetadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (([string]$InstalledMetadata.source_commit_sha).ToLowerInvariant() -ne $ExpectedSourceSha) {
            throw "Installed source SHA does not match ExpectedSourceSha."
        }
    }
    if ($ExpectedReleaseLabel) {
        $InstalledGuidePath = Join-Path $InstallDir "README-WINDOWS.md"
        if (-not (Test-Path $InstalledGuidePath -PathType Leaf)) {
            throw "Installed README-WINDOWS.md is missing."
        }
        $InstalledGuide = Get-Content $InstalledGuidePath -Raw -Encoding UTF8
        if (-not $InstalledGuide.Contains($ExpectedReleaseLabel)) {
            throw "Installed README-WINDOWS.md does not contain expected release label '$ExpectedReleaseLabel'."
        }
    }

    $LayoutRaw = Invoke-CapturedProcess -FilePath $InstalledExe -Arguments @("--diagnose-installation-layout") -Label "installed layout diagnostic"
    $Layout = $LayoutRaw | ConvertFrom-Json
    if (-not $Layout.installed) { throw "Installed executable did not recognize the installation marker." }
    if ($Layout.runtime_source -ne "INSTALLED_MARKER") { throw "Installed runtime source was '$($Layout.runtime_source)', expected INSTALLED_MARKER." }
    if (-not $Layout.user_data_separated_from_app) { throw "Installed runtime was not separated from application binaries." }
    if ($Layout.network_used) { throw "Installation layout diagnostic unexpectedly reported network use." }
    if ([IO.Path]::GetFullPath([string]$Layout.runtime_dir) -ne [IO.Path]::GetFullPath($ExpectedRuntime)) {
        throw "Installed runtime mismatch. Expected '$ExpectedRuntime', got '$($Layout.runtime_dir)'."
    }

    $ReportRaw = Invoke-CapturedProcess -FilePath $InstalledExe -Arguments @("--diagnose-report-export-runtime") -Label "installed report-export diagnostic"
    $Report = $ReportRaw | ConvertFrom-Json
    if (-not $Report.ready -or $Report.network_used) {
        throw "Installed report renderer diagnostic was not provider-free and ready."
    }

    $CorpusRaw = Invoke-CapturedProcess -FilePath $InstalledExe -Arguments @("--diagnose-corpus", "--json") -Label "installed corpus diagnostic" -TimeoutSeconds 240
    $Corpus = $CorpusRaw | ConvertFrom-Json
    if (-not $Corpus.ready) { throw "Installed packaged corpus baseline is not ready." }

    New-Item -ItemType Directory -Path $ExpectedRuntime -Force | Out-Null
    "preserve-me" | Set-Content -Encoding UTF8 $Sentinel

    Install-LawRag -LogPath $ReinstallLog -Label "in-place reinstall"
    if (-not (Test-Path $Sentinel)) { throw "In-place reinstall deleted user runtime data." }
    if (-not (Test-Path $InstalledExe)) { throw "Law-Rag.exe disappeared after in-place reinstall." }

    Invoke-CheckedProcess -FilePath $Uninstaller -Label "per-user uninstall" -TimeoutSeconds 420 -Arguments @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/LOG=`"$UninstallLog`""
    )

    if (Test-Path $InstalledExe) { throw "Uninstall left Law-Rag.exe installed." }
    if (Test-Path $InstalledMarker) { throw "Uninstall left the installation marker behind." }
    if (-not (Test-Path $Sentinel)) { throw "Uninstall deleted user runtime data; this is forbidden." }

    Write-Host "[Law-Rag] Stage 19.1 installer smoke PASS"
    if ($ExpectedSourceSha) { Write-Host "[Law-Rag] installed source identity PASS: $ExpectedSourceSha" }
    if ($ExpectedReleaseLabel) { Write-Host "[Law-Rag] installed release label PASS: $ExpectedReleaseLabel" }
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
