param(
    [string]$BundleDir = (Join-Path $PSScriptRoot "dist\Law-Rag"),
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$Exe = Join-Path $BundleDir "Law-Rag.exe"
if (-not (Test-Path $Exe)) {
    throw "Law-Rag.exe not found at $Exe"
}

& $Exe --diagnose --json
if ($LASTEXITCODE -ne 0) {
    throw "Packaged runtime diagnostics failed with exit code $LASTEXITCODE"
}

$Process = Start-Process -FilePath $Exe -ArgumentList @("--no-browser", "--port", "$Port") -PassThru
try {
    $BaseUrl = "http://127.0.0.1:$Port"
    $Ready = $false
    for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
        if ($Process.HasExited) {
            throw "Law-Rag.exe exited before the HTTP smoke test completed. Exit code: $($Process.ExitCode)"
        }
        try {
            $Health = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/health" -TimeoutSec 2
            if ($Health.StatusCode -eq 200) {
                $Ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $Ready) {
        throw "Law-Rag packaged server did not become ready on $BaseUrl"
    }

    $Root = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/" -TimeoutSec 5
    if ($Root.StatusCode -ne 200 -or $Root.Content -notmatch '<div id="root"></div>') {
        throw "Packaged frontend root did not return the Vite/React shell."
    }

    $MissingApi = $null
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/not-a-real-route" -TimeoutSec 5 -ErrorAction Stop | Out-Null
    }
    catch {
        $MissingApi = $_.Exception.Response.StatusCode.value__
    }
    if ($MissingApi -ne 404) {
        throw "Unknown packaged API route was not an explicit 404. Observed: $MissingApi"
    }

    Write-Host "[Law-Rag] Packaged diagnostics, API health, frontend shell, and API 404 boundary passed."
}
finally {
    if (-not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        $Process.WaitForExit()
    }
}
