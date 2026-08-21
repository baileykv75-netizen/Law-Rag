param(
    [string]$BundleDir = (Join-Path $PSScriptRoot "dist\Law-Rag"),
    [int]$Port = 8795
)

$ErrorActionPreference = "Stop"
$Exe = Join-Path $BundleDir "Law-Rag.exe"
$MetadataPath = Join-Path $BundleDir "_internal\release\public-assets-metadata.json"
$PackagedLegal = Join-Path $BundleDir "_internal\public-assets\legal\legal.db"
$PackagedRetrieval = Join-Path $BundleDir "_internal\public-assets\legal\retrieval.db"
$Runtime = Join-Path $env:RUNNER_TEMP ("law-rag-stage15-5-runtime-" + [guid]::NewGuid().ToString("N"))
$BootstrapStdout = Join-Path $env:RUNNER_TEMP ("law-rag-stage15-5-bootstrap-" + [guid]::NewGuid().ToString("N") + ".stdout.log")
$BootstrapStderr = Join-Path $env:RUNNER_TEMP ("law-rag-stage15-5-bootstrap-" + [guid]::NewGuid().ToString("N") + ".stderr.log")

if (-not (Test-Path $Exe)) { throw "Law-Rag.exe missing from Windows bundle." }
foreach ($Path in @($MetadataPath, $PackagedLegal, $PackagedRetrieval)) {
    if (-not (Test-Path $Path)) { throw "Stage 15.5 packaged corpus asset missing: $Path" }
}

$Metadata = Get-Content $MetadataPath -Raw | ConvertFrom-Json
if ($Metadata.schema_version -ne "2.0.0") { throw "Unexpected packaged corpus metadata schema." }
if ($Metadata.asset_profile -ne "stage15.5-three-domain-baseline") { throw "Unexpected packaged corpus profile." }
if ($Metadata.corpus_release.corpus_id -ne "three-domain-core") { throw "Wrong packaged corpus_id." }
if ($Metadata.corpus_release.corpus_version -ne "1.0.0") { throw "Wrong packaged corpus_version." }
if ($Metadata.corpus_release.release_digest -ne "4009c06967cd2281089e85bdfda64388dd4ac8fc3b86125d971bfa1c0f642b4f") {
    throw "Wrong packaged Corpus Release digest."
}
if ($Metadata.legal.authority_count -ne 14 -or $Metadata.legal.version_count -ne 15 -or $Metadata.legal.article_count -ne 1274) {
    throw "Packaged legal.db does not match the 14/15/1274 baseline."
}
if (-not $Metadata.retrieval.lexical_ready -or $Metadata.retrieval.article_count -ne 1274) {
    throw "Packaged lexical retrieval index does not cover all 1274 Articles."
}
if ($Metadata.retrieval.semantic_ready) {
    throw "Stage 15.5 baseline unexpectedly bundled semantic vectors/BGE weights."
}

$PackagedLegalHash = (Get-FileHash -Algorithm SHA256 $PackagedLegal).Hash.ToLowerInvariant()
$PackagedRetrievalHash = (Get-FileHash -Algorithm SHA256 $PackagedRetrieval).Hash.ToLowerInvariant()
if ($PackagedLegalHash -ne $Metadata.legal.sha256.ToLowerInvariant()) { throw "Packaged legal.db SHA mismatch." }
if ($PackagedRetrievalHash -ne $Metadata.retrieval.sha256.ToLowerInvariant()) { throw "Packaged retrieval.db SHA mismatch." }

$PreviousRuntime = $env:LAW_RAG_RUNTIME_DIR
$PreviousLegal = $env:LAW_RAG_LEGAL_DB
$PreviousRetrieval = $env:LAW_RAG_RETRIEVAL_DB
$PreviousHttpProxy = $env:HTTP_PROXY
$PreviousHttpsProxy = $env:HTTPS_PROXY
$PreviousAllProxy = $env:ALL_PROXY
$PreviousNoProxy = $env:NO_PROXY

try {
    $env:LAW_RAG_RUNTIME_DIR = $Runtime
    Remove-Item Env:LAW_RAG_LEGAL_DB -ErrorAction SilentlyContinue
    Remove-Item Env:LAW_RAG_RETRIEVAL_DB -ErrorAction SilentlyContinue
    $env:HTTP_PROXY = "http://127.0.0.1:9"
    $env:HTTPS_PROXY = "http://127.0.0.1:9"
    $env:ALL_PROXY = "http://127.0.0.1:9"
    $env:NO_PROXY = "127.0.0.1,localhost"

    $DiagnosticJson = (& $Exe --diagnose-corpus --json | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Frozen packaged corpus diagnostic failed: $DiagnosticJson" }
    $Diagnostic = $DiagnosticJson | ConvertFrom-Json
    if (-not $Diagnostic.ready) { throw "Frozen packaged corpus diagnostic did not report ready." }
    if ($Diagnostic.legal.authority_count -ne 14 -or $Diagnostic.legal.version_count -ne 15 -or $Diagnostic.legal.article_count -ne 1274) {
        throw "Frozen corpus diagnostic returned wrong legal counts."
    }
    if (-not $Diagnostic.smoke_query.exact_hit -or $Diagnostic.smoke_query.authority_id -ne "prc-labor-contract-law") {
        throw "Frozen offline exact-citation retrieval smoke failed."
    }
    if (Test-Path $Runtime) {
        throw "--diagnose-corpus mutated the runtime directory."
    }
    if ((Get-FileHash -Algorithm SHA256 $PackagedLegal).Hash.ToLowerInvariant() -ne $PackagedLegalHash) {
        throw "--diagnose-corpus mutated packaged legal.db bytes."
    }
    if ((Get-FileHash -Algorithm SHA256 $PackagedRetrieval).Hash.ToLowerInvariant() -ne $PackagedRetrievalHash) {
        throw "--diagnose-corpus mutated packaged retrieval.db bytes."
    }

    $Process = Start-Process -FilePath $Exe -ArgumentList @("--no-browser", "--port", "$Port") -RedirectStandardOutput $BootstrapStdout -RedirectStandardError $BootstrapStderr -PassThru
    try {
        $BaseUrl = "http://127.0.0.1:$Port"
        $Ready = $false
        for ($Attempt = 1; $Attempt -le 40; $Attempt++) {
            if ($Process.HasExited) {
                $Stdout = if (Test-Path $BootstrapStdout) { Get-Content $BootstrapStdout -Raw } else { "" }
                $Stderr = if (Test-Path $BootstrapStderr) { Get-Content $BootstrapStderr -Raw } else { "" }
                throw "Law-Rag.exe exited during Stage 15.5 bootstrap smoke. Exit=$($Process.ExitCode)`nSTDOUT:`n$Stdout`nSTDERR:`n$Stderr"
            }
            try {
                $Health = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/health" -TimeoutSec 2
                if ($Health.StatusCode -eq 200) { $Ready = $true; break }
            }
            catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $Ready) { throw "Stage 15.5 packaged server did not become ready." }

        $RuntimeLegal = Join-Path $Runtime "legal\legal.db"
        $RuntimeRetrieval = Join-Path $Runtime "legal\retrieval.db"
        $InstalledMetadataPath = Join-Path $Runtime "legal\installed-corpus.json"
        foreach ($Path in @($RuntimeLegal, $RuntimeRetrieval, $InstalledMetadataPath)) {
            if (-not (Test-Path $Path)) { throw "First-run baseline installation missing: $Path" }
        }
        if ((Get-FileHash -Algorithm SHA256 $RuntimeLegal).Hash.ToLowerInvariant() -ne $PackagedLegalHash) {
            throw "Runtime legal.db differs from verified packaged baseline after first install."
        }
        if ((Get-FileHash -Algorithm SHA256 $RuntimeRetrieval).Hash.ToLowerInvariant() -ne $PackagedRetrievalHash) {
            throw "Runtime retrieval.db differs from verified packaged baseline after first install."
        }
        $Installed = Get-Content $InstalledMetadataPath -Raw | ConvertFrom-Json
        if ($Installed.corpus_release.corpus_version -ne "1.0.0" -or $Installed.corpus_release.release_digest -ne $Metadata.corpus_release.release_digest) {
            throw "Runtime installed-corpus metadata does not pin the packaged Corpus Release."
        }
    }
    finally {
        if ($null -ne $Process -and -not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force
            $Process.WaitForExit()
        }
    }

    $env:LAW_RAG_LEGAL_DB = (Join-Path $Runtime "legal\legal.db")
    $env:LAW_RAG_RETRIEVAL_DB = (Join-Path $Runtime "legal\retrieval.db")
    $RuntimeDiagnosticJson = (& $Exe --diagnose-corpus --json | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Installed runtime corpus diagnostic failed: $RuntimeDiagnosticJson" }
    $RuntimeDiagnostic = $RuntimeDiagnosticJson | ConvertFrom-Json
    if (-not $RuntimeDiagnostic.ready -or -not $RuntimeDiagnostic.smoke_query.exact_hit) {
        throw "Installed runtime corpus is not independently retrievable offline."
    }

    Write-Host "[Law-Rag] Stage 15.5 Windows baseline: 14/15/1274 packaged, hashes verified, diagnostic non-mutating, first-run runtime install and offline retrieval passed."
}
finally {
    if ($null -eq $PreviousRuntime) { Remove-Item Env:LAW_RAG_RUNTIME_DIR -ErrorAction SilentlyContinue } else { $env:LAW_RAG_RUNTIME_DIR = $PreviousRuntime }
    if ($null -eq $PreviousLegal) { Remove-Item Env:LAW_RAG_LEGAL_DB -ErrorAction SilentlyContinue } else { $env:LAW_RAG_LEGAL_DB = $PreviousLegal }
    if ($null -eq $PreviousRetrieval) { Remove-Item Env:LAW_RAG_RETRIEVAL_DB -ErrorAction SilentlyContinue } else { $env:LAW_RAG_RETRIEVAL_DB = $PreviousRetrieval }
    if ($null -eq $PreviousHttpProxy) { Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue } else { $env:HTTP_PROXY = $PreviousHttpProxy }
    if ($null -eq $PreviousHttpsProxy) { Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue } else { $env:HTTPS_PROXY = $PreviousHttpsProxy }
    if ($null -eq $PreviousAllProxy) { Remove-Item Env:ALL_PROXY -ErrorAction SilentlyContinue } else { $env:ALL_PROXY = $PreviousAllProxy }
    if ($null -eq $PreviousNoProxy) { Remove-Item Env:NO_PROXY -ErrorAction SilentlyContinue } else { $env:NO_PROXY = $PreviousNoProxy }
    foreach ($Path in @($BootstrapStdout, $BootstrapStderr)) {
        if (Test-Path $Path) { Remove-Item $Path -Force }
    }
    if (Test-Path $Runtime) { Remove-Item $Runtime -Recurse -Force }
}
