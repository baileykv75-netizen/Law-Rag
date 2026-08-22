param(
    [string]$BundleDir = (Join-Path $PSScriptRoot "dist\Law-Rag"),
    [int]$Port = 8870
)

$ErrorActionPreference = "Stop"
$Exe = Join-Path $BundleDir "Law-Rag.exe"
$Runtime = Join-Path $env:RUNNER_TEMP ("law-rag-stage18-5-runtime-" + [guid]::NewGuid().ToString("N"))
$Stdout = Join-Path $env:RUNNER_TEMP ("law-rag-stage18-5-" + [guid]::NewGuid().ToString("N") + ".stdout.log")
$Stderr = Join-Path $env:RUNNER_TEMP ("law-rag-stage18-5-" + [guid]::NewGuid().ToString("N") + ".stderr.log")
$BaseUrl = "http://127.0.0.1:$Port"

function Start-LawRagServer {
    if (Test-Path $Stdout) { Remove-Item $Stdout -Force }
    if (Test-Path $Stderr) { Remove-Item $Stderr -Force }
    $Process = Start-Process -FilePath $Exe -ArgumentList @("--no-browser", "--no-tray", "--port", "$Port") -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr -PassThru
    $Ready = $false
    for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
        if ($Process.HasExited) {
            $Out = if (Test-Path $Stdout) { Get-Content $Stdout -Raw } else { "" }
            $Err = if (Test-Path $Stderr) { Get-Content $Stderr -Raw } else { "" }
            throw "Law-Rag.exe exited during Stage 18.5 smoke. Exit=$($Process.ExitCode)`nSTDOUT:`n$Out`nSTDERR:`n$Err"
        }
        try {
            $Health = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/health" -TimeoutSec 2
            if ($Health.StatusCode -eq 200) { $Ready = $true; break }
        }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $Ready) {
        if (-not $Process.HasExited) { Stop-Process -Id $Process.Id -Force }
        throw "Stage 18.5 packaged server did not become ready."
    }
    return $Process
}

function Stop-LawRagServer {
    param($Process)
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        $Process.WaitForExit()
    }
}

function Invoke-JsonRequest {
    param(
        [string]$Method,
        [string]$Uri,
        [object]$Body = $null
    )
    $Args = @{
        UseBasicParsing = $true
        Method = $Method
        Uri = $Uri
        TimeoutSec = 10
    }
    if ($null -ne $Body) {
        $Args.ContentType = "application/json"
        $Args.Body = ($Body | ConvertTo-Json -Depth 20)
    }
    $Response = Invoke-WebRequest @Args
    if ($Response.StatusCode -lt 200 -or $Response.StatusCode -ge 300) {
        throw "$Method $Uri returned HTTP $($Response.StatusCode)."
    }
    if ([string]::IsNullOrWhiteSpace($Response.Content)) { return $null }
    return $Response.Content | ConvertFrom-Json
}

if (-not (Test-Path $Exe)) { throw "Law-Rag.exe missing from Windows bundle." }

$PreviousRuntime = $env:LAW_RAG_RUNTIME_DIR
$PreviousLegal = $env:LAW_RAG_LEGAL_DB
$PreviousRetrieval = $env:LAW_RAG_RETRIEVAL_DB
$PreviousEncryption = $env:LAW_RAG_RUNTIME_ENCRYPTION_MODE
$PreviousDeepSeekKey = $env:DEEPSEEK_API_KEY
$PreviousKimiKey = $env:MOONSHOT_API_KEY
$Process = $null

try {
    $env:LAW_RAG_RUNTIME_DIR = $Runtime
    $env:LAW_RAG_RUNTIME_ENCRYPTION_MODE = "AUTO"
    Remove-Item Env:LAW_RAG_LEGAL_DB -ErrorAction SilentlyContinue
    Remove-Item Env:LAW_RAG_RETRIEVAL_DB -ErrorAction SilentlyContinue
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:MOONSHOT_API_KEY -ErrorAction SilentlyContinue

    # Stage 18.2: the frozen executable must contain and execute the same
    # python-docx/reportlab renderers used by production export. This diagnostic
    # is synthetic and provider-free.
    $ReportJson = (& $Exe --diagnose-report-export-runtime | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Frozen report renderer diagnostic failed: $ReportJson" }
    $Report = $ReportJson | ConvertFrom-Json
    if (-not $Report.ready -or $Report.network_used -or -not $Report.synthetic_only) {
        throw "Frozen report renderer diagnostic violated its offline/ready contract: $ReportJson"
    }
    if (-not $Report.docx.ready -or $Report.docx.signature -ne "504b0304" -or $Report.docx.size_bytes -le 0) {
        throw "Frozen DOCX renderer/dependency closure is not usable: $ReportJson"
    }
    if (-not $Report.pdf.ready -or $Report.pdf.signature -ne "%PDF" -or $Report.pdf.size_bytes -le 0) {
        throw "Frozen PDF renderer/dependency closure is not usable: $ReportJson"
    }
    if ($Report.docx.sha256.Length -ne 64 -or $Report.pdf.sha256.Length -ne 64) {
        throw "Frozen report renderer diagnostic did not return SHA-256 evidence."
    }

    $Process = Start-LawRagServer

    # Stage 18.1: normal packaged startup already ran ensure_runtime_encryption_on_startup.
    # Inspect the resulting truth without assuming the hosted Windows filesystem
    # necessarily supports EFS.
    $EncryptionJson = (& $Exe --diagnose-runtime-encryption --json | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Frozen runtime-encryption diagnostic failed: $EncryptionJson" }
    $Encryption = $EncryptionJson | ConvertFrom-Json
    if ($Encryption.platform -ne "win32" -or $Encryption.mode -ne "AUTO") {
        throw "Frozen runtime-encryption diagnostic did not resolve Windows AUTO policy: $EncryptionJson"
    }
    $ExpectedManaged = @("jobs", "uploads", "rendered", "batches", "cleanup", "exports")
    foreach ($Name in $ExpectedManaged) {
        if (@($Encryption.managed_root_names) -notcontains $Name) {
            throw "Runtime encryption omitted managed root '$Name'."
        }
    }
    if (@($Encryption.managed_root_names) -contains "legal") {
        throw "Shared runtime/legal must remain outside the Job-private EFS managed-root list."
    }
    if (@("ENCRYPTED", "DEGRADED", "UNSUPPORTED") -notcontains $Encryption.state) {
        throw "AUTO runtime encryption returned an untruthful/unexpected packaged state: $EncryptionJson"
    }
    if ($Encryption.state -eq "ENCRYPTED" -and @($Encryption.protected_root_names).Count -ne $ExpectedManaged.Count) {
        throw "ENCRYPTED state must verify every managed Job-private root."
    }

    # Stage 18.3: exercise local per-Job budget persistence/API without any
    # provider execution.
    $JobId = [guid]::NewGuid()
    $JobDir = Join-Path $Runtime ("jobs\" + $JobId.ToString())
    New-Item -ItemType Directory -Force -Path $JobDir | Out-Null
    $BudgetBody = @{
        policy = @{
            max_provider_calls = 7
            max_total_tokens = 12345
            max_estimated_cost = 5.5
            currency = "CNY"
            provider_prices = @{
                deepseek = @{ prompt_per_million = 1.25; completion_per_million = 2.5 }
                kimi = @{ prompt_per_million = 1.5; completion_per_million = 3.0 }
            }
        }
    }
    $Budget = Invoke-JsonRequest -Method PUT -Uri "$BaseUrl/api/documents/$($JobId.ToString())/resource-budget" -Body $BudgetBody
    if ($Budget.state -ne "WITHIN_BUDGET" -or $Budget.provider_calls_used -ne 0) {
        throw "Packaged resource-budget API did not preserve zero-call local accounting."
    }
    if ($Budget.call_budget_remaining -ne 7 -or $Budget.token_budget_remaining -ne 12345) {
        throw "Packaged resource-budget remaining limits are incorrect."
    }
    if ([math]::Abs([double]$Budget.estimated_cost_remaining - 5.5) -gt 0.000001) {
        throw "Packaged estimated-cost budget was not preserved."
    }
    $BudgetRead = Invoke-JsonRequest -Method GET -Uri "$BaseUrl/api/documents/$($JobId.ToString())/resource-budget"
    if ($BudgetRead.policy.currency -ne "CNY" -or $BudgetRead.provider_calls_used -ne 0) {
        throw "Packaged resource-budget persistence/readback failed."
    }
    $BudgetPath = Join-Path $JobDir "resource-budget.json"
    if (-not (Test-Path $BudgetPath)) { throw "Packaged resource-budget.json was not persisted." }

    # Stage 18.4: save/read/reset only non-secret runtime options. No connection
    # probe endpoint is called anywhere in this smoke.
    $RuntimeSettingsBody = @{
        deepseek = @{
            model = "deepseek-v4-pro"
            base_url = "https://api.deepseek.com"
            request_timeout_seconds = 75
            connect_timeout_seconds = 10
            max_attempts = 2
            retry_backoff_seconds = 1.5
        }
        kimi = @{
            model = "kimi-k3"
            base_url = "https://api.moonshot.cn/v1"
            request_timeout_seconds = 95
            connect_timeout_seconds = 11
            max_attempts = 2
            retry_backoff_seconds = 1.25
        }
        confirm_custom_endpoints = $false
    }
    $RuntimeSettings = Invoke-JsonRequest -Method PUT -Uri "$BaseUrl/api/config/providers/runtime" -Body $RuntimeSettingsBody
    if (@($RuntimeSettings.providers).Count -ne 2) { throw "Packaged provider runtime settings did not expose both providers." }
    foreach ($Provider in @($RuntimeSettings.providers)) {
        if ($Provider.source -ne "SAVED") { throw "Saved packaged provider runtime source was not surfaced as SAVED." }
    }
    $DeepSeekRuntime = @($RuntimeSettings.providers) | Where-Object { $_.provider -eq "deepseek" } | Select-Object -First 1
    $KimiRuntime = @($RuntimeSettings.providers) | Where-Object { $_.provider -eq "kimi" } | Select-Object -First 1
    if ($null -eq $DeepSeekRuntime -or $DeepSeekRuntime.request_timeout_seconds -ne 75 -or $DeepSeekRuntime.base_url -ne "https://api.deepseek.com") {
        throw "Packaged DeepSeek runtime settings did not round-trip."
    }
    if ($null -eq $KimiRuntime -or $KimiRuntime.request_timeout_seconds -ne 95 -or $KimiRuntime.base_url -ne "https://api.moonshot.cn/v1") {
        throw "Packaged Kimi runtime settings did not round-trip."
    }

    $ProviderOverview = Invoke-JsonRequest -Method GET -Uri "$BaseUrl/api/config/providers"
    if (-not $ProviderOverview.secure_storage_available) {
        throw "Frozen Windows build did not expose Windows Credential Manager availability."
    }
    $OverviewSerialized = $ProviderOverview | ConvertTo-Json -Depth 20
    if ($OverviewSerialized -match "DEEPSEEK_API_KEY|MOONSHOT_API_KEY|Authorization|Bearer") {
        throw "Provider overview leaked secret-bearing fields."
    }
    foreach ($Provider in @($ProviderOverview.providers)) {
        if ($Provider.runtime_source -ne "SAVED") { throw "Provider overview did not use saved Stage 18.4 runtime source." }
    }

    $RuntimeSettingsPath = Join-Path $Runtime "config\provider-runtime.json"
    if (-not (Test-Path $RuntimeSettingsPath)) { throw "Packaged provider-runtime.json was not persisted." }
    $RuntimeSettingsText = Get-Content $RuntimeSettingsPath -Raw
    if ($RuntimeSettingsText -match "api[_-]?key|authorization|bearer") {
        throw "Non-secret provider-runtime.json contains a secret-like field."
    }

    $Reset = Invoke-JsonRequest -Method DELETE -Uri "$BaseUrl/api/config/providers/runtime"
    if (-not $Reset.reset) { throw "Packaged provider runtime reset did not report success." }
    if (Test-Path $RuntimeSettingsPath) { throw "Packaged provider runtime reset left the saved override file behind." }
    foreach ($Provider in @($Reset.overview.providers)) {
        if ($Provider.source -ne "DEFAULT") { throw "Provider reset did not return to built-in defaults in the isolated smoke environment." }
    }

    # Prove the smoke itself never created a live provider call ledger row.
    $BudgetAfter = Invoke-JsonRequest -Method GET -Uri "$BaseUrl/api/documents/$($JobId.ToString())/resource-budget"
    if ($BudgetAfter.provider_calls_used -ne 0 -or $BudgetAfter.completed_calls -ne 0 -or $BudgetAfter.in_flight_calls -ne 0) {
        throw "Stage 18.5 packaged smoke unexpectedly consumed provider budget."
    }

    Write-Host "[Law-Rag] Stage 18.5 Windows smoke passed: frozen DOCX/PDF renderers, truthful EFS state, local resource budgets, non-secret provider runtime settings, and Credential Manager boundary are usable without provider network calls."
}
finally {
    Stop-LawRagServer $Process
    if (Test-Path $Runtime) { Remove-Item -Recurse -Force $Runtime -ErrorAction SilentlyContinue }
    if (Test-Path $Stdout) { Remove-Item -Force $Stdout -ErrorAction SilentlyContinue }
    if (Test-Path $Stderr) { Remove-Item -Force $Stderr -ErrorAction SilentlyContinue }

    if ($null -eq $PreviousRuntime) { Remove-Item Env:LAW_RAG_RUNTIME_DIR -ErrorAction SilentlyContinue } else { $env:LAW_RAG_RUNTIME_DIR = $PreviousRuntime }
    if ($null -eq $PreviousLegal) { Remove-Item Env:LAW_RAG_LEGAL_DB -ErrorAction SilentlyContinue } else { $env:LAW_RAG_LEGAL_DB = $PreviousLegal }
    if ($null -eq $PreviousRetrieval) { Remove-Item Env:LAW_RAG_RETRIEVAL_DB -ErrorAction SilentlyContinue } else { $env:LAW_RAG_RETRIEVAL_DB = $PreviousRetrieval }
    if ($null -eq $PreviousEncryption) { Remove-Item Env:LAW_RAG_RUNTIME_ENCRYPTION_MODE -ErrorAction SilentlyContinue } else { $env:LAW_RAG_RUNTIME_ENCRYPTION_MODE = $PreviousEncryption }
    if ($null -eq $PreviousDeepSeekKey) { Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue } else { $env:DEEPSEEK_API_KEY = $PreviousDeepSeekKey }
    if ($null -eq $PreviousKimiKey) { Remove-Item Env:MOONSHOT_API_KEY -ErrorAction SilentlyContinue } else { $env:MOONSHOT_API_KEY = $PreviousKimiKey }
}
