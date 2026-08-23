param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('PrepareFixture', 'SignerMismatch', 'Cleanup')]
    [string]$Phase,
    [string]$OutputDir = (Join-Path $PSScriptRoot 'update-dist'),
    [string]$StatePath = (Join-Path $PSScriptRoot '.stage19-3-ci-state.json'),
    [string]$CleanupJournalPath = (Join-Path $PSScriptRoot '.stage19-3-ci-cleanup.json')
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Stage 19.3 CI fixture/cleanup helper is Windows-only.' }

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path
$PwshPath = (Get-Command pwsh.exe -ErrorAction Stop).Source
$ManifestTool = Join-Path $PSScriptRoot 'new-stage19-3-update-manifest.ps1'
$VerifierTool = Join-Path $PSScriptRoot 'verify-stage19-3-update.ps1'
$IdentityHelper = Join-Path $PSScriptRoot 'stage19-3-ci-signing-identities.ps1'
$UnsignedFixture = Join-Path $OutputDir 'Law-Rag-stage19-3-fixture-unsigned.exe'
$Fixture = Join-Path $OutputDir 'Law-Rag-stage19-3-fixture.exe'

function Normalize-Thumbprint {
    param([string]$Value)
    if (-not $Value) { return '' }
    return (($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

function Get-SourceSha {
    $Sha = (& git -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $Sha -notmatch '^[0-9a-f]{40}$') {
        throw 'Could not resolve exact source SHA for Stage 19.3 CI fixture validation.'
    }
    return $Sha
}

function Get-State {
    if (-not (Test-Path $StatePath -PathType Leaf)) { throw "Stage 19.3 CI state is missing: $StatePath" }
    $State = Get-Content $StatePath -Raw -Encoding utf8 | ConvertFrom-Json
    if (-not $State.finalized) { throw 'Stage 19.3 CI signing state is not finalized.' }
    if ([string]$State.source_commit_sha -ne (Get-SourceSha)) { throw 'Stage 19.3 CI signing state does not match the exact checked-out source SHA.' }
    return $State
}

function Resolve-SignTool {
    $Candidates = @()
    $SdkBin = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    if (Test-Path $SdkBin -PathType Container) {
        $Candidates += Get-Item (Join-Path $SdkBin '*\x64\signtool.exe') -ErrorAction SilentlyContinue
    }
    $OnPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($null -ne $OnPath) { $Candidates += Get-Item $OnPath.Source -ErrorAction SilentlyContinue }
    $Tool = $Candidates |
        Sort-Object @{ Expression = {
            try { [version]$_.Directory.Parent.Name }
            catch { [version]'0.0' }
        }; Descending = $true } |
        Select-Object -First 1
    if ($null -eq $Tool) { throw 'Windows SDK signtool.exe was not found.' }
    return $Tool.FullName
}

function Resolve-Csc {
    $Candidates = @(
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate -PathType Leaf) { return (Resolve-Path $Candidate).Path }
    }
    $OnPath = Get-Command csc.exe -ErrorAction SilentlyContinue
    if ($null -ne $OnPath) { return $OnPath.Source }
    throw 'C# compiler csc.exe was not found on the Windows CI runner.'
}

function Invoke-BoundedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds,
        [string]$Label
    )
    Write-Host "[Law-Rag][Stage19.3] START $Label"
    $Started = [DateTimeOffset]::UtcNow
    $Psi = [System.Diagnostics.ProcessStartInfo]::new()
    $Psi.FileName = $FilePath
    $Psi.UseShellExecute = $false
    $Psi.WorkingDirectory = $RepoRoot
    foreach ($Argument in $Arguments) { [void]$Psi.ArgumentList.Add($Argument) }
    $Process = [System.Diagnostics.Process]::new()
    $Process.StartInfo = $Psi
    try {
        if (-not $Process.Start()) { throw "$Label failed to start." }
        if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $Process.Kill($true) } catch { }
            throw "$Label timed out after $TimeoutSeconds seconds."
        }
        if ($Process.ExitCode -ne 0) { throw "$Label failed with exit code $($Process.ExitCode)." }
        $Elapsed = [Math]::Round(([DateTimeOffset]::UtcNow - $Started).TotalSeconds, 1)
        Write-Host "[Law-Rag][Stage19.3] PASS $Label (${Elapsed}s)"
    }
    finally { $Process.Dispose() }
}

function Assert-UnsignedFixture {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Unsigned fixture is missing: $Path" }
    $Signature = Get-AuthenticodeSignature -FilePath $Path
    if ([string]$Signature.Status -ne 'NotSigned' -or $null -ne $Signature.SignerCertificate) {
        $Signer = if ($null -ne $Signature.SignerCertificate) { Normalize-Thumbprint $Signature.SignerCertificate.Thumbprint } else { '' }
        throw "CI fixture must begin Authenticode-unsigned; status=$($Signature.Status), signer=$Signer"
    }
}

function New-UnsignedFixture {
    $SourcePath = Join-Path $OutputDir 'stage19-3-fixture.cs'
    Remove-Item $UnsignedFixture -Force -ErrorAction SilentlyContinue
    Remove-Item $SourcePath -Force -ErrorAction SilentlyContinue
    $Code = @'
namespace LawRag.Stage193 {
    internal static class FixtureProgram {
        public static int Main() { return 0; }
    }
}
'@
    [IO.File]::WriteAllText($SourcePath, $Code, [Text.UTF8Encoding]::new($false))
    try {
        $Csc = Resolve-Csc
        Invoke-BoundedProcess -FilePath $Csc -TimeoutSeconds 60 -Label 'compile unsigned PE fixture' -Arguments @(
            '/nologo', '/target:exe', '/platform:anycpu', '/optimize+', "/out:$UnsignedFixture", $SourcePath
        )
    }
    finally {
        Remove-Item $SourcePath -Force -ErrorAction SilentlyContinue
    }
    Assert-UnsignedFixture -Path $UnsignedFixture
    Write-Host '[Law-Rag][Stage19.3] PASS unsigned PE fixture baseline is explicitly NotSigned'
}

function Sign-FileChecked {
    param([string]$Path, [string]$Thumbprint, [string]$Label)
    $Normalized = Normalize-Thumbprint $Thumbprint
    $Signer = Get-Item "Cert:\CurrentUser\My\$Normalized" -ErrorAction Stop
    if (-not $Signer.HasPrivateKey) { throw "CI signer $Normalized has no private key." }
    $SignTool = Resolve-SignTool
    Invoke-BoundedProcess -FilePath $SignTool -TimeoutSeconds 180 -Label "Authenticode sign: $Label" -Arguments @(
        'sign', '/fd', 'SHA256', '/s', 'My', '/sha1', $Normalized, $Path
    )
    Invoke-BoundedProcess -FilePath $SignTool -TimeoutSeconds 120 -Label "Authenticode verify: $Label" -Arguments @(
        'verify', '/pa', '/all', $Path
    )
    $Signature = Get-AuthenticodeSignature -FilePath $Path
    $ActualSigner = if ($null -ne $Signature.SignerCertificate) { Normalize-Thumbprint $Signature.SignerCertificate.Thumbprint } else { '' }
    if ([string]$Signature.Status -ne 'Valid' -or $ActualSigner -ne $Normalized) {
        throw "Signed fixture identity check failed for $Label; status=$($Signature.Status), expected=$Normalized, actual=$ActualSigner"
    }
}

function New-SignedManifest {
    param([string]$Artifact, [string]$Version, [string]$Url, [string]$SignerThumbprint, [string]$Directory)
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $Manifest = Join-Path $Directory 'manifest.json'
    $Cms = Join-Path $Directory 'manifest.p7s'
    Invoke-BoundedProcess -FilePath $PwshPath -TimeoutSeconds 120 -Label "manifest sign $Version" -Arguments @(
        '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $ManifestTool,
        '-InstallerPath', $Artifact,
        '-CandidateVersion', $Version,
        '-ArtifactUrl', $Url,
        '-SignerThumbprint', $SignerThumbprint,
        '-ManifestPath', $Manifest,
        '-SignaturePath', $Cms
    )
    if (-not (Test-Path $Manifest -PathType Leaf) -or -not (Test-Path $Cms -PathType Leaf)) {
        throw "Manifest generation did not produce both outputs in $Directory."
    }
    return [pscustomobject]@{ Manifest = $Manifest; Cms = $Cms }
}

function Invoke-UpdateVerifier {
    param(
        [string]$Manifest,
        [string]$Cms,
        [string]$Installer,
        [string]$ExpectedSigner,
        [string]$Evidence,
        [string]$Label
    )
    Invoke-BoundedProcess -FilePath $PwshPath -TimeoutSeconds 120 -Label $Label -Arguments @(
        '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $VerifierTool,
        '-ManifestPath', $Manifest,
        '-ManifestSignaturePath', $Cms,
        '-InstallerPath', $Installer,
        '-CurrentVersion', '0.8.0-rc2',
        '-ExpectedSignerThumbprint', $ExpectedSigner,
        '-EvidencePath', $Evidence,
        '-RequireEligible'
    )
}

function Read-Evidence {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Expected evidence was not written: $Path" }
    return (Get-Content $Path -Raw -Encoding utf8 | ConvertFrom-Json)
}

function Invoke-ExpectedVerifierRefusal {
    param(
        [string]$Manifest,
        [string]$Cms,
        [string]$Installer,
        [string]$ExpectedSigner,
        [string]$Evidence,
        [string]$Label
    )
    $Refused = $false
    try {
        Invoke-UpdateVerifier -Manifest $Manifest -Cms $Cms -Installer $Installer -ExpectedSigner $ExpectedSigner -Evidence $Evidence -Label $Label
    }
    catch {
        $Refused = $true
        Write-Host "[Law-Rag][Stage19.3] Expected $Label refusal: $($_.Exception.Message)"
    }
    if (-not $Refused) { throw "Stage 19.3 negative case unexpectedly passed: $Label" }
    if (-not (Test-Path $Evidence -PathType Leaf)) { throw "$Label failed before deterministic refusal evidence was written." }
}

function Invoke-PrepareFixture {
    Write-Host '[Law-Rag][Stage19.3] PHASE PrepareFixture deterministic unsigned source'
    $State = Get-State
    $Primary = Normalize-Thumbprint ([string]$State.primary_thumbprint)
    New-UnsignedFixture
    Copy-Item -LiteralPath $UnsignedFixture -Destination $Fixture -Force
    Sign-FileChecked -Path $Fixture -Thumbprint $Primary -Label 'primary negative-case fixture'

    $Manifest = New-SignedManifest -Artifact $Fixture -Version '0.8.0-rc3' `
        -Url 'https://updates.example.invalid/Law-Rag-stage19-3-fixture.exe' `
        -SignerThumbprint $Primary -Directory (Join-Path $OutputDir 'fixture-positive')
    $EvidencePath = Join-Path $OutputDir 'STAGE19-3-FIXTURE-POSITIVE.json'
    Invoke-UpdateVerifier -Manifest $Manifest.Manifest -Cms $Manifest.Cms -Installer $Fixture `
        -ExpectedSigner $Primary -Evidence $EvidencePath -Label 'small fixture positive verifier'
    $Evidence = Read-Evidence $EvidencePath
    if (-not $Evidence.eligible -or $Evidence.decision -ne 'UPDATE_ELIGIBLE') { throw 'Small signed fixture baseline was not eligible.' }
    if ($Evidence.manifest.cms_status -ne 'VALID') { throw 'Small fixture manifest CMS signature did not validate.' }
    if ($Evidence.artifact.authenticode.status -ne 'Valid') { throw 'Small fixture Authenticode signature did not validate.' }
    Write-Host '[Law-Rag][Stage19.3] PHASE PrepareFixture PASS'
}

function Invoke-SignerMismatch {
    Write-Host '[Law-Rag][Stage19.3] PHASE SignerMismatch deterministic unsigned source'
    $State = Get-State
    $Primary = Normalize-Thumbprint ([string]$State.primary_thumbprint)
    $Other = Normalize-Thumbprint ([string]$State.other_thumbprint)
    Assert-UnsignedFixture -Path $UnsignedFixture

    $MismatchFixture = Join-Path $OutputDir 'Law-Rag-stage19-3-mismatch.exe'
    Copy-Item -LiteralPath $UnsignedFixture -Destination $MismatchFixture -Force
    Sign-FileChecked -Path $MismatchFixture -Thumbprint $Other -Label 'mismatched-signer fixture'
    $Manifest = New-SignedManifest -Artifact $MismatchFixture -Version '0.8.0-rc3' `
        -Url 'https://updates.example.invalid/Law-Rag-stage19-3-mismatch.exe' `
        -SignerThumbprint $Primary -Directory (Join-Path $OutputDir 'signer-mismatch')
    $EvidencePath = Join-Path $OutputDir 'STAGE19-3-SIGNER-MISMATCH.json'
    Invoke-ExpectedVerifierRefusal -Manifest $Manifest.Manifest -Cms $Manifest.Cms -Installer $MismatchFixture `
        -ExpectedSigner $Primary -Evidence $EvidencePath -Label 'signer mismatch verifier'
    $Evidence = Read-Evidence $EvidencePath
    if ($Evidence.rejection_reasons -notcontains 'INSTALLER_SIGNER_MISMATCH') {
        throw 'Signer mismatch evidence did not contain INSTALLER_SIGNER_MISMATCH.'
    }
    Write-Host '[Law-Rag][Stage19.3] PHASE SignerMismatch PASS'
}

function Read-CleanupThumbprintsLoose {
    $Values = [System.Collections.Generic.List[string]]::new()
    foreach ($Path in @($CleanupJournalPath, $StatePath)) {
        if (-not (Test-Path $Path -PathType Leaf)) { continue }
        try {
            $Data = Get-Content $Path -Raw -Encoding utf8 | ConvertFrom-Json
            $RawValues = if ($Path -eq $CleanupJournalPath) {
                @($Data.thumbprints)
            } else {
                @($Data.primary_thumbprint, $Data.other_thumbprint)
            }
            foreach ($Raw in $RawValues) {
                $Thumbprint = Normalize-Thumbprint ([string]$Raw)
                if ($Thumbprint -and -not $Values.Contains($Thumbprint)) { $Values.Add($Thumbprint) }
            }
        }
        catch {
            Write-Warning "Could not snapshot cleanup identifiers from ${Path}: $($_.Exception.Message)"
        }
    }
    return @($Values)
}

function Test-CleanupResiduals {
    param([string[]]$Thumbprints)
    $Residuals = [System.Collections.Generic.List[object]]::new()
    $InspectionErrors = [System.Collections.Generic.List[string]]::new()
    $Targets = @(
        [pscustomobject]@{ StoreName = [System.Security.Cryptography.X509Certificates.StoreName]::My; StoreLocation = [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser },
        [pscustomobject]@{ StoreName = [System.Security.Cryptography.X509Certificates.StoreName]::Root; StoreLocation = [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser },
        [pscustomobject]@{ StoreName = [System.Security.Cryptography.X509Certificates.StoreName]::TrustedPublisher; StoreLocation = [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser },
        [pscustomobject]@{ StoreName = [System.Security.Cryptography.X509Certificates.StoreName]::Root; StoreLocation = [System.Security.Cryptography.X509Certificates.StoreLocation]::LocalMachine },
        [pscustomobject]@{ StoreName = [System.Security.Cryptography.X509Certificates.StoreName]::TrustedPublisher; StoreLocation = [System.Security.Cryptography.X509Certificates.StoreLocation]::LocalMachine }
    )
    foreach ($Thumbprint in $Thumbprints) {
        foreach ($Target in $Targets) {
            $Store = $null
            try {
                $Store = [System.Security.Cryptography.X509Certificates.X509Store]::new($Target.StoreName, $Target.StoreLocation)
                $Store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
                $Count = @($Store.Certificates | Where-Object { (Normalize-Thumbprint $_.Thumbprint) -eq $Thumbprint }).Count
                if ($Count -gt 0) {
                    $Residuals.Add([pscustomobject]@{
                        thumbprint = $Thumbprint
                        store_location = [string]$Target.StoreLocation
                        store_name = [string]$Target.StoreName
                        count = $Count
                    })
                }
            }
            catch {
                $InspectionErrors.Add("${Thumbprint}@$($Target.StoreLocation)/$($Target.StoreName): $($_.Exception.Message)")
            }
            finally {
                if ($null -ne $Store) { $Store.Close() }
            }
        }
    }
    return [pscustomobject]@{ residuals = @($Residuals); inspection_errors = @($InspectionErrors) }
}

function Invoke-CleanupWithEvidence {
    Write-Host '[Law-Rag][Stage19.3] PHASE Cleanup with residual evidence'
    $Thumbprints = @(Read-CleanupThumbprintsLoose)
    $HelperSucceeded = $false
    $HelperError = $null
    try {
        & $IdentityHelper -Phase Cleanup -StatePath $StatePath -CleanupJournalPath $CleanupJournalPath
        $HelperSucceeded = $true
    }
    catch {
        $HelperError = $_.Exception.Message
        Write-Warning "Stage 19.3 identity helper cleanup failed: $HelperError"
    }

    $Inspection = Test-CleanupResiduals -Thumbprints $Thumbprints
    $CleanupComplete = $HelperSucceeded -and $Inspection.residuals.Count -eq 0 -and $Inspection.inspection_errors.Count -eq 0
    $EvidenceDir = Join-Path $OutputDir 'cleanup'
    New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
    $EvidencePath = Join-Path $EvidenceDir 'STAGE19-3-CI-CLEANUP.json'
    $Evidence = [ordered]@{
        schema_version = '1.0.0'
        source_commit_sha = (Get-SourceSha)
        checked_at = [DateTimeOffset]::UtcNow.ToString('o')
        cleanup_complete = $CleanupComplete
        identity_helper_succeeded = $HelperSucceeded
        identity_helper_error = $HelperError
        tracked_thumbprints = $Thumbprints
        residual_certificates = @($Inspection.residuals)
        inspection_errors = @($Inspection.inspection_errors)
    }
    [IO.File]::WriteAllText($EvidencePath, ($Evidence | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))

    if (-not $CleanupComplete) {
        $ResidualSummary = if ($Inspection.residuals.Count -gt 0) {
            ($Inspection.residuals | ForEach-Object { "$($_.thumbprint)@$($_.store_location)/$($_.store_name)x$($_.count)" }) -join '; '
        } else { 'none observed' }
        $InspectionSummary = if ($Inspection.inspection_errors.Count -gt 0) { $Inspection.inspection_errors -join '; ' } else { 'none' }
        throw "Stage 19.3 cleanup did not prove complete. helper_error=$HelperError; residuals=$ResidualSummary; inspection_errors=$InspectionSummary"
    }
    Write-Host '[Law-Rag][Stage19.3] PHASE Cleanup PASS with zero tracked residual certificates'
}

switch ($Phase) {
    'PrepareFixture' { Invoke-PrepareFixture }
    'SignerMismatch' { Invoke-SignerMismatch }
    'Cleanup' { Invoke-CleanupWithEvidence }
}
