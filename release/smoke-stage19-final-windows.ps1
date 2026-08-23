param(
    [Parameter(Mandatory = $true)]
    [string]$EngineeringPortablePath,
    [Parameter(Mandatory = $true)]
    [string]$SignedRcDir,
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [string]$ConfigPath = (Join-Path $PSScriptRoot "stage19-final-acceptance-config.json"),
    [string]$ExpectedSignerThumbprint = $env:LAW_RAG_RELEASE_SIGNER_THUMBPRINT,
    [string]$OutputPath = (Join-Path $PSScriptRoot "final-acceptance\STAGE19-FINAL-WINDOWS-SMOKE-EVIDENCE.json"),
    [int]$Port = 8920
)

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Stage 19 final Windows smoke is Windows-only." }

function Normalize-Thumbprint([string]$Value) {
    if (-not $Value) { return "" }
    return (($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

function Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
}

function Signature-Record([string]$Path) {
    $Signature = Get-AuthenticodeSignature -FilePath $Path
    $Certificate = $Signature.SignerCertificate
    return [ordered]@{
        sha256 = Sha256 $Path
        size_bytes = (Get-Item $Path).Length
        authenticode_status = [string]$Signature.Status
        signer_present = ($null -ne $Certificate)
        signer_thumbprint = $(if ($null -ne $Certificate) { Normalize-Thumbprint ([string]$Certificate.Thumbprint) } else { "" })
        signer_subject = $(if ($null -ne $Certificate) { [string]$Certificate.Subject } else { "" })
    }
}

function Relative-Files([string]$Root) {
    return @(Get-ChildItem $Root -Recurse -File | ForEach-Object {
        [IO.Path]::GetRelativePath($Root, $_.FullName).Replace('\', '/')
    } | Sort-Object)
}

if (-not (Test-Path $ConfigPath -PathType Leaf)) { throw "Final acceptance config is missing." }
$Config = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$Baseline = $Config.engineering_candidate
$ExpectedSourceSha = ([string]$Baseline.source_sha).ToLowerInvariant()
$ExpectedReleaseLabel = [string]$Baseline.release_label
$ExpectedEngineeringPortableSha = ([string]$Baseline.portable.sha256).ToLowerInvariant()
$ExpectedEngineeringInstallerSha = ([string]$Baseline.installer.sha256).ToLowerInvariant()
if ($ExpectedSourceSha -notmatch '^[0-9a-f]{40}$') { throw "Configured source SHA is invalid." }
if ($ExpectedEngineeringPortableSha -notmatch '^[0-9a-f]{64}$') { throw "Configured engineering portable hash is invalid." }
if ($ExpectedEngineeringInstallerSha -notmatch '^[0-9a-f]{64}$') { throw "Configured engineering installer hash is invalid." }

$ExpectedSigner = Normalize-Thumbprint $ExpectedSignerThumbprint
if (-not $ExpectedSigner) { throw "An explicit expected production signer thumbprint is required." }
if ($ExpectedSigner.Length -ne 40 -and $ExpectedSigner.Length -ne 64) {
    throw "Expected signer thumbprint must normalize to SHA-1 or SHA-256 length."
}

$EngineeringPortablePath = (Resolve-Path $EngineeringPortablePath).Path
$SignedRcDir = (Resolve-Path $SignedRcDir).Path
$InstallerPath = (Resolve-Path $InstallerPath).Path
if ((Sha256 $EngineeringPortablePath) -ne $ExpectedEngineeringPortableSha) {
    throw "Engineering portable input does not match the frozen Stage 19.4 baseline hash."
}
if ((Sha256 $InstallerPath) -eq $ExpectedEngineeringInstallerSha) {
    throw "Final installer is byte-identical to the unsigned Stage 19.4 installer; production signing/rebuild was not applied."
}

$ManifestPath = Join-Path $SignedRcDir "RC-MANIFEST.json"
$SumsPath = Join-Path $SignedRcDir "SHA256SUMS.txt"
if (-not (Test-Path $ManifestPath -PathType Leaf)) { throw "Signed portable RC manifest is missing." }
if (-not (Test-Path $SumsPath -PathType Leaf)) { throw "Signed portable RC SHA256SUMS is missing." }
$Manifest = Get-Content $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$Manifest.rc_version -ne $ExpectedReleaseLabel) { throw "Signed portable release label mismatch." }
if (([string]$Manifest.source_commit_sha).ToLowerInvariant() -ne $ExpectedSourceSha) { throw "Signed portable source SHA mismatch." }
$ZipPath = Join-Path $SignedRcDir ([string]$Manifest.artifact.filename)
if (-not (Test-Path $ZipPath -PathType Leaf)) { throw "Manifest-declared signed portable ZIP is missing." }
$ZipSha = Sha256 $ZipPath
if ($ZipSha -eq $ExpectedEngineeringPortableSha) {
    throw "Signed portable is byte-identical to the unsigned Stage 19.4 portable; production executable signing was not applied."
}
if ($ZipSha -ne ([string]$Manifest.artifact.sha256).ToLowerInvariant()) { throw "Signed portable ZIP hash does not match manifest." }
if ((Get-Item $ZipPath).Length -ne [int64]$Manifest.artifact.size_bytes) { throw "Signed portable ZIP size does not match manifest." }
$SumsText = Get-Content $SumsPath -Raw -Encoding UTF8
if ($SumsText -notmatch [regex]::Escape("$ZipSha  $([IO.Path]::GetFileName($ZipPath))")) {
    throw "Signed portable SHA256SUMS does not bind the exact ZIP."
}

$BaselineExtractRoot = Join-Path $env:RUNNER_TEMP ("law-rag-final-baseline-" + [guid]::NewGuid().ToString("N"))
$SignedExtractRoot = Join-Path $env:RUNNER_TEMP ("law-rag-final-signed-" + [guid]::NewGuid().ToString("N"))
$PreviousDeepSeek = $env:DEEPSEEK_API_KEY
$PreviousKimi = $env:MOONSHOT_API_KEY
try {
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:MOONSHOT_API_KEY -ErrorAction SilentlyContinue

    Expand-Archive -Path $EngineeringPortablePath -DestinationPath $BaselineExtractRoot -Force
    Expand-Archive -Path $ZipPath -DestinationPath $SignedExtractRoot -Force
    $BaselineBundle = Join-Path $BaselineExtractRoot "Law-Rag"
    $Bundle = Join-Path $SignedExtractRoot "Law-Rag"
    $BaselineExe = Join-Path $BaselineBundle "Law-Rag.exe"
    $ExePath = Join-Path $Bundle "Law-Rag.exe"
    if (-not (Test-Path $BaselineExe -PathType Leaf) -or -not (Test-Path $ExePath -PathType Leaf)) {
        throw "Baseline or signed portable ZIP does not contain Law-Rag.exe."
    }

    $BaselineFiles = Relative-Files $BaselineBundle
    $SignedFiles = Relative-Files $Bundle
    $FileListDifference = @(Compare-Object $BaselineFiles $SignedFiles)
    if ($FileListDifference.Count -ne 0) {
        throw "Signed portable file list differs from the exact Stage 19.4 baseline."
    }

    $ChangedPaths = @()
    foreach ($RelativePath in $BaselineFiles) {
        $BaselineFile = Join-Path $BaselineBundle ($RelativePath.Replace('/', '\'))
        $SignedFile = Join-Path $Bundle ($RelativePath.Replace('/', '\'))
        $BaselineHash = Sha256 $BaselineFile
        $SignedHash = Sha256 $SignedFile
        if ($BaselineHash -ne $SignedHash) { $ChangedPaths += $RelativePath }
    }
    if ($ChangedPaths.Count -ne 1 -or $ChangedPaths[0] -ne "Law-Rag.exe") {
        throw "Signed portable may differ from the exact Stage 19.4 baseline only at Law-Rag.exe; changed paths: $($ChangedPaths -join ', ')."
    }

    $MetadataPath = Join-Path $Bundle "_internal\release\release-metadata.json"
    if (-not (Test-Path $MetadataPath -PathType Leaf)) { throw "Signed portable release metadata is missing." }
    $Metadata = Get-Content $MetadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (([string]$Metadata.source_commit_sha).ToLowerInvariant() -ne $ExpectedSourceSha) {
        throw "Signed portable embedded source SHA mismatch."
    }

    $GuidePath = Join-Path $Bundle "README-WINDOWS.md"
    if (-not (Test-Path $GuidePath -PathType Leaf)) { throw "Signed portable Windows guide is missing." }
    $Guide = Get-Content $GuidePath -Raw -Encoding UTF8
    foreach ($RequiredText in @($ExpectedReleaseLabel, "release-specific signing evidence", "FINAL_ACCEPTANCE_PENDING")) {
        if (-not $Guide.Contains($RequiredText)) { throw "Signed portable guide is stale; missing: $RequiredText" }
    }

    $ExeSignature = Signature-Record $ExePath
    $InstallerSignature = Signature-Record $InstallerPath
    if ($ExeSignature.authenticode_status -ne "Valid") { throw "Signed portable Law-Rag.exe Authenticode status is not Valid." }
    if ($InstallerSignature.authenticode_status -ne "Valid") { throw "Signed installer Authenticode status is not Valid." }
    if (-not $ExeSignature.signer_present -or -not $InstallerSignature.signer_present) { throw "Production signer certificate is missing." }
    if ($ExeSignature.signer_thumbprint -ne $ExpectedSigner) { throw "Signed portable executable signer mismatch." }
    if ($InstallerSignature.signer_thumbprint -ne $ExpectedSigner) { throw "Signed installer signer mismatch." }

    & (Join-Path $PSScriptRoot "smoke-windows.ps1") -BundleDir $Bundle -Port $Port
    if ($LASTEXITCODE -ne 0) { throw "Final signed portable runtime smoke failed." }
    & (Join-Path $PSScriptRoot "smoke-stage14-7-windows.ps1") -BundleDir $Bundle -Port ($Port + 5)
    if ($LASTEXITCODE -ne 0) { throw "Final signed portable DOCX/OCR/provider-boundary smoke failed." }
    & (Join-Path $PSScriptRoot "smoke-stage12f-windows.ps1") -BundleDir $Bundle -Port ($Port + 10)
    if ($LASTEXITCODE -ne 0) { throw "Final signed portable user-flow smoke failed." }
    & (Join-Path $PSScriptRoot "smoke-stage13a-windows.ps1") -BundleDir $Bundle -Port ($Port + 20)
    if ($LASTEXITCODE -ne 0) { throw "Final signed portable provider-boundary smoke failed." }

    & (Join-Path $PSScriptRoot "smoke-stage19-1-installer.ps1") `
        -InstallerPath $InstallerPath `
        -ExpectedSourceSha $ExpectedSourceSha `
        -ExpectedReleaseLabel $ExpectedReleaseLabel `
        -ExpectedExecutableSha256 $ExeSignature.sha256
    if ($LASTEXITCODE -ne 0) { throw "Final signed installer lifecycle smoke failed." }

    $Evidence = [ordered]@{
        schema_version = "1.0.0"
        stage = "19-final-windows-smoke"
        source_sha = $ExpectedSourceSha
        release_label = $ExpectedReleaseLabel
        passed = $true
        production_signed = $true
        provider_network_calls = 0
        expected_signer_thumbprint = $ExpectedSigner
        engineering_baseline = [ordered]@{
            portable_sha256 = $ExpectedEngineeringPortableSha
            installer_sha256 = $ExpectedEngineeringInstallerSha
        }
        transformation = [ordered]@{
            exact_baseline_portable_verified = $true
            file_list_identical = $true
            changed_paths = @($ChangedPaths)
            only_authenticode_target_changed = $true
            installer_built_from_same_signed_executable = $true
        }
        distribution_candidate = [ordered]@{
            portable = [ordered]@{
                filename = [IO.Path]::GetFileName($ZipPath)
                sha256 = $ZipSha
                size_bytes = (Get-Item $ZipPath).Length
            }
            executable = [ordered]@{
                filename = "Law-Rag.exe"
                sha256 = $ExeSignature.sha256
                size_bytes = $ExeSignature.size_bytes
                authenticode_status = $ExeSignature.authenticode_status
                signer_thumbprint = $ExeSignature.signer_thumbprint
                signer_subject = $ExeSignature.signer_subject
            }
            installer = [ordered]@{
                filename = [IO.Path]::GetFileName($InstallerPath)
                sha256 = $InstallerSignature.sha256
                size_bytes = $InstallerSignature.size_bytes
                authenticode_status = $InstallerSignature.authenticode_status
                signer_thumbprint = $InstallerSignature.signer_thumbprint
                signer_subject = $InstallerSignature.signer_subject
            }
        }
        checks = [ordered]@{
            baseline_to_signed_transformation = $true
            portable_manifest_hash = $true
            embedded_source_identity = $true
            portable_executable_signature = $true
            installer_signature = $true
            signer_identity_match = $true
            packaged_runtime_smoke = $true
            installer_contains_same_signed_executable = $true
            reinstall_preserves_runtime = $true
            uninstall_preserves_runtime = $true
        }
        external_actions = [ordered]@{
            signing_executed_by_this_script = $false
            provider_calls_executed_by_this_script = $false
            publication_executed_by_this_script = $false
        }
    }

    $Parent = Split-Path $OutputPath -Parent
    if ($Parent) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
    $Evidence | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 $OutputPath
    Write-Host "[Law-Rag] Stage 19 final signed Windows smoke PASS"
    Write-Host "[Law-Rag] Exact engineering baseline -> signed candidate transformation PASS"
    Write-Host "[Law-Rag] Changed portable path: Law-Rag.exe only"
    Write-Host "[Law-Rag] Source SHA: $ExpectedSourceSha"
    Write-Host "[Law-Rag] Signed portable SHA-256: $ZipSha"
    Write-Host "[Law-Rag] Signed executable SHA-256: $($ExeSignature.sha256)"
    Write-Host "[Law-Rag] Signed installer SHA-256: $($InstallerSignature.sha256)"
    Write-Host "[Law-Rag] Provider/network calls: 0"
}
finally {
    if ($null -eq $PreviousDeepSeek) { Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue } else { $env:DEEPSEEK_API_KEY = $PreviousDeepSeek }
    if ($null -eq $PreviousKimi) { Remove-Item Env:MOONSHOT_API_KEY -ErrorAction SilentlyContinue } else { $env:MOONSHOT_API_KEY = $PreviousKimi }
    if (Test-Path $BaselineExtractRoot) { Remove-Item $BaselineExtractRoot -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path $SignedExtractRoot) { Remove-Item $SignedExtractRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
