param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Setup', 'Positive', 'Tamper', 'PrepareFixture', 'ManifestTamper', 'SignerMismatch', 'SameVersion', 'HttpUrl', 'Cleanup')]
    [string]$Phase,
    [string]$InstallerPath = (Join-Path $PSScriptRoot "installer-dist\Law-Rag-0.8.0-rc2-windows-x64-setup.exe"),
    [string]$OutputDir = (Join-Path $PSScriptRoot "update-dist"),
    [string]$StatePath = (Join-Path $PSScriptRoot ".stage19-3-ci-state.json")
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Stage 19.3 safe-update smoke is Windows-only.' }

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path
$PwshPath = (Get-Command pwsh.exe -ErrorAction Stop).Source

function Normalize-Thumbprint {
    param([string]$Value)
    if (-not $Value) { return '' }
    return (($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

function Add-CertificateToStore {
    param(
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [System.Security.Cryptography.X509Certificates.StoreName]$StoreName
    )
    $Store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        $StoreName,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $Store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $Store.Add($Certificate)
    }
    finally { $Store.Close() }
}

function Remove-CertificateFromStore {
    param([string]$Thumbprint, [System.Security.Cryptography.X509Certificates.StoreName]$StoreName)
    $Normalized = Normalize-Thumbprint $Thumbprint
    if (-not $Normalized) { return }
    $Store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        $StoreName,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $Store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $Matches = @($Store.Certificates | Where-Object { (Normalize-Thumbprint $_.Thumbprint) -eq $Normalized })
        foreach ($Certificate in $Matches) { $Store.Remove($Certificate) }
    }
    finally { $Store.Close() }
}

function New-DotNetCiSigner {
    param([string]$Subject)
    Write-Host "[Law-Rag][Stage19.3] START create signer $Subject"
    $Rsa = [System.Security.Cryptography.RSA]::Create(2048)
    $Transient = $null
    try {
        $Request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
            $Subject,
            $Rsa,
            [System.Security.Cryptography.HashAlgorithmName]::SHA256,
            [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
        )
        $Request.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
                [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature,
                $true
            )
        )
        $Eku = [System.Security.Cryptography.OidCollection]::new()
        [void]$Eku.Add([System.Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.3', 'Code Signing'))
        $Request.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($Eku, $true)
        )
        $Transient = $Request.CreateSelfSigned(
            [DateTimeOffset]::UtcNow.AddMinutes(-5),
            [DateTimeOffset]::UtcNow.AddDays(2)
        )
        $Password = [Guid]::NewGuid().ToString('N')
        $Pfx = $Transient.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Pfx, $Password)
        $Flags = (
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::UserKeySet -bor
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
        )
        $Persisted = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($Pfx, $Password, $Flags)
        Add-CertificateToStore -Certificate $Persisted -StoreName My
        Add-CertificateToStore -Certificate $Persisted -StoreName Root
        Add-CertificateToStore -Certificate $Persisted -StoreName TrustedPublisher
        $Stored = Get-Item "Cert:\CurrentUser\My\$($Persisted.Thumbprint)" -ErrorAction Stop
        if (-not $Stored.HasPrivateKey) { throw 'Persisted CI signer lost its private key.' }
        Write-Host "[Law-Rag][Stage19.3] PASS create signer $Subject"
        return $Stored
    }
    finally {
        if ($null -ne $Transient) { $Transient.Dispose() }
        $Rsa.Dispose()
    }
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

function Get-State {
    if (-not (Test-Path $StatePath -PathType Leaf)) { throw "Stage 19.3 CI state is missing: $StatePath" }
    return (Get-Content $StatePath -Raw | ConvertFrom-Json)
}

function Get-SignerCertificate {
    param([string]$Thumbprint)
    $Normalized = Normalize-Thumbprint $Thumbprint
    $Certificate = Get-Item "Cert:\CurrentUser\My\$Normalized" -ErrorAction Stop
    if (-not $Certificate.HasPrivateKey) { throw "CI signer $Normalized has no private key." }
    return $Certificate
}

function Sign-FileChecked {
    param([string]$Path, [string]$Thumbprint, [string]$Label)
    $SignTool = Resolve-SignTool
    Invoke-BoundedProcess -FilePath $SignTool `
        -Arguments @('sign', '/fd', 'SHA256', '/s', 'My', '/sha1', $Thumbprint, $Path) `
        -TimeoutSeconds 180 -Label "Authenticode sign: $Label"
    Invoke-BoundedProcess -FilePath $SignTool `
        -Arguments @('verify', '/pa', '/all', $Path) `
        -TimeoutSeconds 120 -Label "Authenticode verify: $Label"
}

function New-SignedManifest {
    param([string]$Artifact, [string]$Version, [string]$Url, [string]$SignerThumbprint, [string]$Directory)
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $Manifest = Join-Path $Directory 'manifest.json'
    $Cms = Join-Path $Directory 'manifest.p7s'
    $Script = Join-Path $PSScriptRoot 'new-stage19-3-update-manifest.ps1'
    Invoke-BoundedProcess -FilePath $PwshPath -TimeoutSeconds 120 -Label "manifest sign $Version" -Arguments @(
        '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $Script,
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
        [string]$CurrentVersion,
        [string]$ExpectedSigner,
        [string]$Evidence,
        [string]$Label
    )
    $Script = Join-Path $PSScriptRoot 'verify-stage19-3-update.ps1'
    Invoke-BoundedProcess -FilePath $PwshPath -TimeoutSeconds 120 -Label $Label -Arguments @(
        '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $Script,
        '-ManifestPath', $Manifest,
        '-ManifestSignaturePath', $Cms,
        '-InstallerPath', $Installer,
        '-CurrentVersion', $CurrentVersion,
        '-ExpectedSignerThumbprint', $ExpectedSigner,
        '-EvidencePath', $Evidence,
        '-RequireEligible'
    )
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
        Invoke-UpdateVerifier -Manifest $Manifest -Cms $Cms -Installer $Installer -CurrentVersion '0.8.0-rc2' `
            -ExpectedSigner $ExpectedSigner -Evidence $Evidence -Label $Label
    }
    catch {
        $Refused = $true
        Write-Host "[Law-Rag][Stage19.3] Expected $Label refusal: $($_.Exception.Message)"
    }
    if (-not $Refused) { throw "Stage 19.3 negative case unexpectedly passed: $Label" }
    if (-not (Test-Path $Evidence -PathType Leaf)) {
        throw "$Label failed before deterministic refusal evidence was written."
    }
}

function Read-Evidence {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Expected evidence was not written: $Path" }
    return (Get-Content $Path -Raw | ConvertFrom-Json)
}

function Assert-RejectionReason {
    param([string]$EvidencePath, [string]$Reason)
    $Evidence = Read-Evidence $EvidencePath
    if ($Evidence.rejection_reasons -notcontains $Reason) { throw "Expected rejection reason was missing: $Reason" }
}

function Corrupt-PeSectionByte {
    param([string]$Path)
    $Stream = $null
    $Reader = $null
    $Writer = $null
    try {
        $Stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        $Reader = [IO.BinaryReader]::new($Stream, [Text.Encoding]::ASCII, $true)
        $Writer = [IO.BinaryWriter]::new($Stream, [Text.Encoding]::ASCII, $true)
        if ($Stream.Length -lt 256) { throw 'PE candidate is unexpectedly small.' }
        $Stream.Position = 0x3C
        $PeOffset = $Reader.ReadInt32()
        if ($PeOffset -lt 0x40 -or ($PeOffset + 24) -ge $Stream.Length) { throw 'Invalid PE header offset.' }
        $Stream.Position = $PeOffset
        if ($Reader.ReadUInt32() -ne 0x00004550) { throw 'Invalid PE signature.' }
        $Stream.Position = $PeOffset + 6
        $SectionCount = $Reader.ReadUInt16()
        $Stream.Position = $PeOffset + 20
        $OptionalHeaderSize = $Reader.ReadUInt16()
        $SectionTable = [long]$PeOffset + 24 + $OptionalHeaderSize
        if ($SectionCount -lt 1 -or ($SectionTable + (40L * $SectionCount)) -gt $Stream.Length) { throw 'Invalid PE section table.' }
        for ($Index = 0; $Index -lt $SectionCount; $Index++) {
            $SectionOffset = $SectionTable + (40L * $Index)
            $Stream.Position = $SectionOffset + 16
            $RawSize = [long]$Reader.ReadUInt32()
            $Stream.Position = $SectionOffset + 20
            $RawPointer = [long]$Reader.ReadUInt32()
            if ($RawSize -le 128 -or $RawPointer -le 0 -or ($RawPointer + $RawSize) -gt $Stream.Length) { continue }
            $Delta = [Math]::Min(4096L, $RawSize - 1)
            $MutationOffset = $RawPointer + $Delta
            $Stream.Position = $MutationOffset
            $Original = $Reader.ReadByte()
            $Stream.Position = $MutationOffset
            $Writer.Write([byte]($Original -bxor 0x01))
            $Writer.Flush()
            Write-Host "[Law-Rag][Stage19.3] Mutated hashed PE section byte at offset $MutationOffset"
            return
        }
        throw 'No suitable PE section was available for tamper validation.'
    }
    finally {
        if ($null -ne $Writer) { $Writer.Dispose() }
        if ($null -ne $Reader) { $Reader.Dispose() }
        if ($null -ne $Stream) { $Stream.Dispose() }
    }
}

$Candidate = Join-Path $OutputDir 'Law-Rag-0.8.0-rc3-windows-x64-setup.exe'
$Fixture = Join-Path $OutputDir 'Law-Rag-stage19-3-fixture.exe'
$FixtureSource = Join-Path $env:SystemRoot 'System32\where.exe'

switch ($Phase) {
    'Setup' {
        Write-Host '[Law-Rag][Stage19.3] PHASE Setup'
        if (Test-Path $StatePath -PathType Leaf) { throw "Refusing to overwrite stale Stage 19.3 CI state: $StatePath" }
        $Primary = New-DotNetCiSigner -Subject 'CN=Law-Rag Stage 19.3 CI Primary ONLY'
        $Other = New-DotNetCiSigner -Subject 'CN=Law-Rag Stage 19.3 CI Mismatch ONLY'
        $PrimaryThumbprint = (Normalize-Thumbprint $Primary.Thumbprint)
        $OtherThumbprint = (Normalize-Thumbprint $Other.Thumbprint)
        if ($PrimaryThumbprint -eq $OtherThumbprint) { throw 'CI signing identities unexpectedly share a thumbprint.' }
        $State = [ordered]@{
            schema_version = '1.0.0'
            source_commit_sha = (& git -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
            primary_thumbprint = $PrimaryThumbprint
            other_thumbprint = $OtherThumbprint
            created_at = [DateTimeOffset]::UtcNow.ToString('o')
        }
        $State | ConvertTo-Json -Depth 4 | Set-Content -Path $StatePath -Encoding UTF8
        Write-Host '[Law-Rag][Stage19.3] PHASE Setup PASS'
    }
    'Positive' {
        Write-Host '[Law-Rag][Stage19.3] PHASE Positive'
        $State = Get-State
        [void](Get-SignerCertificate $State.primary_thumbprint)
        $ResolvedInstaller = (Resolve-Path $InstallerPath).Path
        if (Test-Path $Candidate) { Remove-Item $Candidate -Force }
        Move-Item -Path $ResolvedInstaller -Destination $Candidate
        Sign-FileChecked -Path $Candidate -Thumbprint $State.primary_thumbprint -Label 'real update installer'
        $ReleaseManifest = New-SignedManifest -Artifact $Candidate -Version '0.8.0-rc3' `
            -Url 'https://updates.example.invalid/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
            -SignerThumbprint $State.primary_thumbprint -Directory (Join-Path $OutputDir 'release-positive')
        $EvidencePath = Join-Path $OutputDir 'STAGE19-3-POSITIVE.json'
        Invoke-UpdateVerifier -Manifest $ReleaseManifest.Manifest -Cms $ReleaseManifest.Cms -Installer $Candidate `
            -CurrentVersion '0.8.0-rc2' -ExpectedSigner $State.primary_thumbprint -Evidence $EvidencePath -Label 'real installer positive verifier'
        $Evidence = Read-Evidence $EvidencePath
        if (-not $Evidence.eligible -or $Evidence.decision -ne 'UPDATE_ELIGIBLE') { throw 'Positive signed candidate was not eligible.' }
        if ($Evidence.manifest.cms_status -ne 'VALID') { throw 'Positive manifest CMS signature did not validate.' }
        if ($Evidence.artifact.authenticode.status -ne 'Valid') { throw 'Positive installer Authenticode signature did not validate.' }
        if ($Evidence.provider_network_uat_executed -or $Evidence.private_expert_evidence_executed) { throw 'Stage 19.3 crossed a forbidden external-evidence boundary.' }
        Write-Host '[Law-Rag][Stage19.3] PHASE Positive PASS'
    }
    'Tamper' {
        Write-Host '[Law-Rag][Stage19.3] PHASE Tamper'
        $State = Get-State
        $Manifest = Join-Path $OutputDir 'release-positive\manifest.json'
        $Cms = Join-Path $OutputDir 'release-positive\manifest.p7s'
        Corrupt-PeSectionByte -Path $Candidate
        $EvidencePath = Join-Path $OutputDir 'STAGE19-3-ARTIFACT-TAMPER.json'
        Invoke-ExpectedVerifierRefusal -Manifest $Manifest -Cms $Cms -Installer $Candidate `
            -ExpectedSigner $State.primary_thumbprint -Evidence $EvidencePath -Label 'real installer tamper verifier'
        Assert-RejectionReason -EvidencePath $EvidencePath -Reason 'ARTIFACT_SHA256_MISMATCH'
        Assert-RejectionReason -EvidencePath $EvidencePath -Reason 'INSTALLER_AUTHENTICODE_NOT_VALID'
        Write-Host '[Law-Rag][Stage19.3] PHASE Tamper PASS'
    }
    'PrepareFixture' {
        Write-Host '[Law-Rag][Stage19.3] PHASE PrepareFixture'
        $State = Get-State
        [void](Get-SignerCertificate $State.primary_thumbprint)
        if (-not (Test-Path $FixtureSource -PathType Leaf)) { throw "Windows signed-fixture source is unavailable: $FixtureSource" }
        Copy-Item $FixtureSource $Fixture -Force
        Sign-FileChecked -Path $Fixture -Thumbprint $State.primary_thumbprint -Label 'primary negative-case fixture'
        $FixtureManifest = New-SignedManifest -Artifact $Fixture -Version '0.8.0-rc3' `
            -Url 'https://updates.example.invalid/Law-Rag-stage19-3-fixture.exe' `
            -SignerThumbprint $State.primary_thumbprint -Directory (Join-Path $OutputDir 'fixture-positive')
        $EvidencePath = Join-Path $OutputDir 'STAGE19-3-FIXTURE-POSITIVE.json'
        Invoke-UpdateVerifier -Manifest $FixtureManifest.Manifest -Cms $FixtureManifest.Cms -Installer $Fixture `
            -CurrentVersion '0.8.0-rc2' -ExpectedSigner $State.primary_thumbprint -Evidence $EvidencePath -Label 'small fixture positive verifier'
        if (-not (Read-Evidence $EvidencePath).eligible) { throw 'Small signed fixture baseline was not eligible.' }
        Write-Host '[Law-Rag][Stage19.3] PHASE PrepareFixture PASS'
    }
    'ManifestTamper' {
        Write-Host '[Law-Rag][Stage19.3] PHASE ManifestTamper'
        $State = Get-State
        $SourceManifest = Join-Path $OutputDir 'fixture-positive\manifest.json'
        $Cms = Join-Path $OutputDir 'fixture-positive\manifest.p7s'
        $TamperedManifest = Join-Path $OutputDir 'UPDATE-MANIFEST-TAMPERED.json'
        Copy-Item $SourceManifest $TamperedManifest -Force
        [IO.File]::AppendAllText($TamperedManifest, ' ')
        $EvidencePath = Join-Path $OutputDir 'STAGE19-3-MANIFEST-TAMPER.json'
        Invoke-ExpectedVerifierRefusal -Manifest $TamperedManifest -Cms $Cms -Installer $Fixture `
            -ExpectedSigner $State.primary_thumbprint -Evidence $EvidencePath -Label 'manifest tamper verifier'
        Assert-RejectionReason -EvidencePath $EvidencePath -Reason 'MANIFEST_CMS_INVALID'
        Write-Host '[Law-Rag][Stage19.3] PHASE ManifestTamper PASS'
    }
    'SignerMismatch' {
        Write-Host '[Law-Rag][Stage19.3] PHASE SignerMismatch'
        $State = Get-State
        [void](Get-SignerCertificate $State.other_thumbprint)
        $MismatchFixture = Join-Path $OutputDir 'Law-Rag-stage19-3-mismatch.exe'
        Copy-Item $FixtureSource $MismatchFixture -Force
        Sign-FileChecked -Path $MismatchFixture -Thumbprint $State.other_thumbprint -Label 'mismatched-signer fixture'
        $MismatchManifest = New-SignedManifest -Artifact $MismatchFixture -Version '0.8.0-rc3' `
            -Url 'https://updates.example.invalid/Law-Rag-stage19-3-mismatch.exe' `
            -SignerThumbprint $State.primary_thumbprint -Directory (Join-Path $OutputDir 'signer-mismatch')
        $EvidencePath = Join-Path $OutputDir 'STAGE19-3-SIGNER-MISMATCH.json'
        Invoke-ExpectedVerifierRefusal -Manifest $MismatchManifest.Manifest -Cms $MismatchManifest.Cms -Installer $MismatchFixture `
            -ExpectedSigner $State.primary_thumbprint -Evidence $EvidencePath -Label 'signer mismatch verifier'
        Assert-RejectionReason -EvidencePath $EvidencePath -Reason 'INSTALLER_SIGNER_MISMATCH'
        Write-Host '[Law-Rag][Stage19.3] PHASE SignerMismatch PASS'
    }
    'SameVersion' {
        Write-Host '[Law-Rag][Stage19.3] PHASE SameVersion'
        $State = Get-State
        $Manifest = New-SignedManifest -Artifact $Fixture -Version '0.8.0-rc2' `
            -Url 'https://updates.example.invalid/Law-Rag-stage19-3-fixture.exe' `
            -SignerThumbprint $State.primary_thumbprint -Directory (Join-Path $OutputDir 'same-version')
        $EvidencePath = Join-Path $OutputDir 'STAGE19-3-SAME-VERSION.json'
        Invoke-ExpectedVerifierRefusal -Manifest $Manifest.Manifest -Cms $Manifest.Cms -Installer $Fixture `
            -ExpectedSigner $State.primary_thumbprint -Evidence $EvidencePath -Label 'same version verifier'
        Assert-RejectionReason -EvidencePath $EvidencePath -Reason 'CANDIDATE_VERSION_NOT_NEWER'
        Write-Host '[Law-Rag][Stage19.3] PHASE SameVersion PASS'
    }
    'HttpUrl' {
        Write-Host '[Law-Rag][Stage19.3] PHASE HttpUrl'
        $State = Get-State
        $Manifest = New-SignedManifest -Artifact $Fixture -Version '0.8.0-rc3' `
            -Url 'http://updates.example.invalid/Law-Rag-stage19-3-fixture.exe' `
            -SignerThumbprint $State.primary_thumbprint -Directory (Join-Path $OutputDir 'http-url')
        $EvidencePath = Join-Path $OutputDir 'STAGE19-3-HTTP-URL.json'
        Invoke-ExpectedVerifierRefusal -Manifest $Manifest.Manifest -Cms $Manifest.Cms -Installer $Fixture `
            -ExpectedSigner $State.primary_thumbprint -Evidence $EvidencePath -Label 'HTTP boundary verifier'
        Assert-RejectionReason -EvidencePath $EvidencePath -Reason 'ARTIFACT_URL_NOT_SAFE_HTTPS'
        Write-Host '[Law-Rag][Stage19.3] PHASE HttpUrl PASS'
    }
    'Cleanup' {
        Write-Host '[Law-Rag][Stage19.3] PHASE Cleanup'
        if (Test-Path $StatePath -PathType Leaf) {
            $State = Get-State
            foreach ($Thumbprint in @($State.primary_thumbprint, $State.other_thumbprint)) {
                foreach ($StoreName in @('My', 'Root', 'TrustedPublisher')) {
                    Remove-CertificateFromStore -Thumbprint $Thumbprint -StoreName $StoreName
                }
            }
            Remove-Item $StatePath -Force
        }
        Write-Host '[Law-Rag][Stage19.3] PHASE Cleanup PASS'
    }
}
