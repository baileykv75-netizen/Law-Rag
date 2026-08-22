param(
    [string]$BundleDir = (Join-Path $PSScriptRoot "dist\Law-Rag"),
    [string]$OutputDir = (Join-Path $PSScriptRoot "installer-dist")
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BundleDir = (Resolve-Path $BundleDir).Path
$InstallerScript = Join-Path $PSScriptRoot "installer\Law-Rag.iss"
$MarkerFile = Join-Path $PSScriptRoot "installer\.law-rag-installed"
$Exe = Join-Path $BundleDir "Law-Rag.exe"

if ($env:OS -ne "Windows_NT") { throw "Stage 19.1 installer build is Windows-only." }
if (-not (Test-Path $Exe)) { throw "Validated onedir Law-Rag.exe is missing: $Exe" }
if (Test-Path (Join-Path $BundleDir "runtime")) {
    throw "Refusing to package a bundle that already contains runtime user data."
}
if (-not (Test-Path $InstallerScript)) { throw "Inno Setup definition missing: $InstallerScript" }
if (-not (Test-Path $MarkerFile)) { throw "Installed-distribution marker missing: $MarkerFile" }

$Candidates = @()
if ($env:INNO_SETUP_COMPILER) { $Candidates += $env:INNO_SETUP_COMPILER }
if (${env:ProgramFiles(x86)}) { $Candidates += (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe") }
if ($env:ProgramFiles) { $Candidates += (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe") }
$Iscc = $Candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $Iscc) {
    throw "Inno Setup 6 compiler was not found. Set INNO_SETUP_COMPILER to ISCC.exe."
}

if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path

# The .iss script validates PREPROCVER during the actual compile and rejects
# compiler families older than 6.x or newer than 6.x. This avoids relying on
# Windows PE version metadata or CLI options that differ between Inno families.
& $Iscc "/DBundleDir=$BundleDir" "/DOutputDir=$OutputDir" "/DMarkerFile=$MarkerFile" $InstallerScript
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed with exit code $LASTEXITCODE." }

$Installer = Join-Path $OutputDir "Law-Rag-0.8.0-rc2-windows-x64-setup.exe"
if (-not (Test-Path $Installer)) { throw "Expected installer was not produced: $Installer" }

$SourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $SourceSha -notmatch '^[0-9a-fA-F]{40}$') {
    throw "Could not resolve exact source SHA for installer evidence."
}

$Evidence = [ordered]@{
    schema_version = "1.0.0"
    stage = "19.1"
    source_sha = $SourceSha.ToLowerInvariant()
    distribution_mode = "PER_USER_INSTALLER"
    install_root = "%LOCALAPPDATA%\\Programs\\Law-Rag"
    runtime_root = "%LOCALAPPDATA%\\Law-Rag\\runtime"
    user_data_separated_from_app = $true
    uninstall_preserves_runtime = $true
    publication_state = "VALIDATION_ONLY_UNSIGNED"
    code_signing = "NOT_APPLIED"
    inno_setup_version = "6.x"
    inno_setup_version_validation = "ISPP_PREPROCVER"
    executable = [ordered]@{
        sha256 = (Get-FileHash -Algorithm SHA256 $Exe).Hash.ToLowerInvariant()
        size_bytes = (Get-Item $Exe).Length
    }
    installer = [ordered]@{
        filename = (Split-Path $Installer -Leaf)
        sha256 = (Get-FileHash -Algorithm SHA256 $Installer).Hash.ToLowerInvariant()
        size_bytes = (Get-Item $Installer).Length
    }
    provider_network_uat_executed = $false
    private_expert_evidence_executed = $false
}
$EvidencePath = Join-Path $OutputDir "STAGE19-1-INSTALLER-EVIDENCE.json"
$Evidence | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $EvidencePath

Write-Host "[Law-Rag] Stage 19.1 validation installer: $Installer"
Write-Host "[Law-Rag] Inno Setup compiler family: 6.x (validated by ISPP PREPROCVER during compilation)"
Write-Host "[Law-Rag] Installer state: VALIDATION_ONLY_UNSIGNED"
Write-Host "[Law-Rag] Runtime data is owned outside the application directory and is not an uninstall target."
Write-Host "[Law-Rag] Evidence: $EvidencePath"
