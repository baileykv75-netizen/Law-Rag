param(
    [string]$RcDir = (Join-Path $PSScriptRoot "rc"),
    [int]$Port = 8766
)

$ErrorActionPreference = "Stop"
$ManifestPath = Join-Path $RcDir "RC-MANIFEST.json"
$SumsPath = Join-Path $RcDir "SHA256SUMS.txt"
if (-not (Test-Path $ManifestPath) -or -not (Test-Path $SumsPath)) {
    throw "RC-MANIFEST.json or SHA256SUMS.txt is missing."
}

$Manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$ZipPath = Join-Path $RcDir $Manifest.artifact.filename
if (-not (Test-Path $ZipPath)) {
    throw "Manifest-declared RC ZIP is missing: $($Manifest.artifact.filename)"
}

$ActualZipHash = (Get-FileHash -Algorithm SHA256 $ZipPath).Hash.ToLowerInvariant()
if ($ActualZipHash -ne $Manifest.artifact.sha256.ToLowerInvariant()) {
    throw "RC ZIP SHA-256 does not match RC-MANIFEST.json."
}
$Sums = Get-Content $SumsPath -Raw
if ($Sums -notmatch [regex]::Escape($ActualZipHash)) {
    throw "SHA256SUMS.txt does not contain the RC ZIP hash."
}

$ExtractRoot = Join-Path $env:RUNNER_TEMP ("law-rag-rc-extract-" + [guid]::NewGuid().ToString("N"))
try {
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractRoot -Force
    $ExtractedBundle = Join-Path $ExtractRoot "Law-Rag"
    if (-not (Test-Path (Join-Path $ExtractedBundle "Law-Rag.exe"))) {
        throw "Extracted RC does not contain Law-Rag/Law-Rag.exe."
    }

    $BundledMetadataPath = Join-Path $ExtractedBundle "_internal\release\release-metadata.json"
    $BundledMetadata = Get-Content $BundledMetadataPath -Raw | ConvertFrom-Json
    if ($BundledMetadata.source_commit_sha -ne $Manifest.source_commit_sha) {
        throw "Extracted release metadata source SHA does not match RC-MANIFEST.json."
    }
    if ($BundledMetadata.application_version -ne $Manifest.application_version) {
        throw "Extracted application version does not match RC-MANIFEST.json."
    }

    & (Join-Path $PSScriptRoot "smoke-windows.ps1") -BundleDir $ExtractedBundle -Port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Extracted portable RC smoke failed with exit code $LASTEXITCODE"
    }

    Write-Host "[Law-Rag] Extracted RC hash/metadata/runtime/PDFium smoke passed."
}
finally {
    if (Test-Path $ExtractRoot) {
        Remove-Item $ExtractRoot -Recurse -Force
    }
}
