param(
    [string]$InstallerPath = (Join-Path $PSScriptRoot "installer-dist\Law-Rag-0.8.0-rc2-windows-x64-setup.exe"),
    [string]$OutputDir = (Join-Path $PSScriptRoot "update-dist")
)

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Stage 19.3 safe-update smoke is Windows-only." }

$InstallerPath = (Resolve-Path $InstallerPath).Path
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path

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
    finally {
        $Store.Close()
    }
}

function New-DotNetCiSigner {
    param([string]$Subject)

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
        [void]$Eku.Add([System.Security.Cryptography.Oid]::new("1.3.6.1.5.5.7.3.3", "Code Signing"))
        $Request.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($Eku, $true)
        )

        $Transient = $Request.CreateSelfSigned(
            [DateTimeOffset]::UtcNow.AddMinutes(-5),
            [DateTimeOffset]::UtcNow.AddDays(2)
        )
        $Password = [Guid]::NewGuid().ToString("N")
        $Pfx = $Transient.Export(
            [System.Security.Cryptography.X509Certificates.X509ContentType]::Pfx,
            $Password
        )
        $Flags = (
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::UserKeySet -bor
            [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
        )
        $Persisted = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
            $Pfx,
            $Password,
            $Flags
        )
        Add-CertificateToStore -Certificate $Persisted -StoreName My
        Add-CertificateToStore -Certificate $Persisted -StoreName Root
        Add-CertificateToStore -Certificate $Persisted -StoreName TrustedPublisher

        $Stored = Get-Item "Cert:\CurrentUser\My\$($Persisted.Thumbprint)" -ErrorAction Stop
        if (-not $Stored.HasPrivateKey) { throw "Persisted CI signer lost its private key." }
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
    if ($null -ne $OnPath) {
        $Candidates += Get-Item $OnPath.Source -ErrorAction SilentlyContinue
    }
    $Tool = $Candidates |
        Sort-Object @{ Expression = {
            try { [version]$_.Directory.Parent.Name }
            catch { [version]'0.0' }
        }; Descending = $true } |
        Select-Object -First 1
    if ($null -eq $Tool) { throw "Windows SDK signtool.exe was not found." }
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
    $Start = [DateTimeOffset]::UtcNow
    $Psi = [System.Diagnostics.ProcessStartInfo]::new()
    $Psi.FileName = $FilePath
    $Psi.UseShellExecute = $false
    foreach ($Argument in $Arguments) {
        [void]$Psi.ArgumentList.Add($Argument)
    }
    $Process = [System.Diagnostics.Process]::new()
    $Process.StartInfo = $Psi
    try {
        if (-not $Process.Start()) { throw "$Label failed to start." }
        if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $Process.Kill($true) } catch { }
            throw "$Label timed out after $TimeoutSeconds seconds."
        }
        if ($Process.ExitCode -ne 0) {
            throw "$Label failed with exit code $($Process.ExitCode)."
        }
        $Elapsed = [Math]::Round(([DateTimeOffset]::UtcNow - $Start).TotalSeconds, 1)
        Write-Host "[Law-Rag][Stage19.3] PASS $Label (${Elapsed}s)"
    }
    finally {
        $Process.Dispose()
    }
}

function Sign-FileChecked {
    param(
        [string]$Path,
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate,
        [string]$Label
    )
    Invoke-BoundedProcess `
        -FilePath $script:SignToolPath `
        -Arguments @('sign', '/fd', 'SHA256', '/s', 'My', '/sha1', $Certificate.Thumbprint, $Path) `
        -TimeoutSeconds 300 `
        -Label "Authenticode signing: $Label"
    Write-Host "[Law-Rag][Stage19.3] Checking Authenticode status for $Label"
    $Signed = Get-AuthenticodeSignature -FilePath $Path
    if ($Signed.Status -ne 'Valid') {
        throw "$Label signature did not validate: $($Signed.Status) $($Signed.StatusMessage)"
    }
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
        if ($Stream.Length -lt 256) { throw "PE candidate is unexpectedly small." }

        $Stream.Position = 0x3C
        $PeOffset = $Reader.ReadInt32()
        if ($PeOffset -lt 0x40 -or ($PeOffset + 24) -ge $Stream.Length) { throw "Invalid PE header offset." }
        $Stream.Position = $PeOffset
        if ($Reader.ReadUInt32() -ne 0x00004550) { throw "Invalid PE signature." }

        $Stream.Position = $PeOffset + 6
        $SectionCount = $Reader.ReadUInt16()
        $Stream.Position = $PeOffset + 20
        $OptionalHeaderSize = $Reader.ReadUInt16()
        $SectionTable = [long]$PeOffset + 24 + $OptionalHeaderSize
        if ($SectionCount -lt 1 -or ($SectionTable + (40L * $SectionCount)) -gt $Stream.Length) {
            throw "Invalid PE section table."
        }

        $Mutated = $false
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
            $Mutated = $true
            break
        }
        if (-not $Mutated) { throw "No suitable PE section was available for tamper validation." }
    }
    finally {
        if ($null -ne $Writer) { $Writer.Dispose() }
        if ($null -ne $Reader) { $Reader.Dispose() }
        if ($null -ne $Stream) { $Stream.Dispose() }
    }
}

function Invoke-ExpectedRefusal {
    param([scriptblock]$Action, [string]$Label)
    $Refused = $false
    try { & $Action }
    catch {
        $Refused = $true
        Write-Host "[Law-Rag][Stage19.3] Expected $Label refusal: $($_.Exception.Message)"
    }
    if (-not $Refused) { throw "Stage 19.3 negative case unexpectedly passed: $Label" }
}

function Read-Evidence {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Expected evidence was not written: $Path" }
    return (Get-Content $Path -Raw | ConvertFrom-Json)
}

function New-SignedManifest {
    param(
        [string]$Artifact,
        [string]$Version,
        [string]$Url,
        [string]$SignerThumbprint,
        [string]$Directory
    )
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $Manifest = Join-Path $Directory 'manifest.json'
    $Cms = Join-Path $Directory 'manifest.p7s'
    ./release/new-stage19-3-update-manifest.ps1 `
        -InstallerPath $Artifact `
        -CandidateVersion $Version `
        -ArtifactUrl $Url `
        -SignerThumbprint $SignerThumbprint `
        -ManifestPath $Manifest `
        -SignaturePath $Cms
    return [pscustomobject]@{ Manifest = $Manifest; Cms = $Cms }
}

$Primary = $null
$Other = $null
try {
    Write-Host "[Law-Rag][Stage19.3] Creating .NET CI-only signing identities"
    $Primary = New-DotNetCiSigner -Subject 'CN=Law-Rag Stage 19.3 CI Primary ONLY'
    $Other = New-DotNetCiSigner -Subject 'CN=Law-Rag Stage 19.3 CI Mismatch ONLY'
    $PrimaryThumbprint = $Primary.Thumbprint.ToUpperInvariant()
    $OtherThumbprint = $Other.Thumbprint.ToUpperInvariant()
    if ($PrimaryThumbprint -eq $OtherThumbprint) { throw "CI signing identities unexpectedly share a thumbprint." }
    $env:LAW_RAG_RELEASE_SIGNER_THUMBPRINT = $PrimaryThumbprint
    $script:SignToolPath = Resolve-SignTool
    Write-Host "[Law-Rag][Stage19.3] Using bounded Windows SDK signer: $script:SignToolPath"

    # Strong release-artifact path. The inherited Stage 19.1 installer has already
    # passed the unsigned-publication gate in the preceding workflow step. Move it
    # within the same workspace instead of copying hundreds of megabytes, then
    # sign and verify the exact bytes. After the positive decision is recorded,
    # mutate a hashed PE section byte in that same candidate so the file remains a
    # structurally parseable PE while both content hash and Authenticode must fail.
    Write-Host "[Law-Rag][Stage19.3] Validating real installer positive path"
    $Candidate = Join-Path $OutputDir 'Law-Rag-0.8.0-rc3-windows-x64-setup.exe'
    if (Test-Path $Candidate) { Remove-Item $Candidate -Force }
    Move-Item -Path $InstallerPath -Destination $Candidate
    Sign-FileChecked -Path $Candidate -Certificate $Primary -Label 'real update installer'

    $ReleaseManifest = New-SignedManifest `
        -Artifact $Candidate `
        -Version '0.8.0-rc3' `
        -Url 'https://updates.example.invalid/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -Directory (Join-Path $OutputDir 'release-positive')
    $PositiveEvidence = Join-Path $OutputDir 'STAGE19-3-POSITIVE.json'
    ./release/verify-stage19-3-update.ps1 `
        -ManifestPath $ReleaseManifest.Manifest `
        -ManifestSignaturePath $ReleaseManifest.Cms `
        -InstallerPath $Candidate `
        -CurrentVersion '0.8.0-rc2' `
        -ExpectedSignerThumbprint $PrimaryThumbprint `
        -EvidencePath $PositiveEvidence `
        -RequireEligible
    $Positive = Read-Evidence $PositiveEvidence
    if (-not $Positive.eligible -or $Positive.decision -ne 'UPDATE_ELIGIBLE') { throw "Positive signed candidate was not eligible." }
    if ($Positive.manifest.cms_status -ne 'VALID') { throw "Positive manifest CMS signature did not validate." }
    if ($Positive.artifact.authenticode.status -ne 'Valid') { throw "Positive installer Authenticode signature did not validate." }
    if ($Positive.provider_network_uat_executed -or $Positive.private_expert_evidence_executed) { throw "Stage 19.3 crossed a forbidden external-evidence boundary." }

    Write-Host "[Law-Rag][Stage19.3] Validating real installer tamper rejection"
    Corrupt-PeSectionByte -Path $Candidate
    $TamperedEvidence = Join-Path $OutputDir 'STAGE19-3-ARTIFACT-TAMPER.json'
    Invoke-ExpectedRefusal -Label 'installer-tamper' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $ReleaseManifest.Manifest -ManifestSignaturePath $ReleaseManifest.Cms -InstallerPath $Candidate -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $TamperedEvidence -RequireEligible
    }
    $Tampered = Read-Evidence $TamperedEvidence
    if ($Tampered.rejection_reasons -notcontains 'ARTIFACT_SHA256_MISMATCH') { throw "Installer tamper did not report SHA-256 mismatch." }
    if ($Tampered.rejection_reasons -notcontains 'INSTALLER_AUTHENTICODE_NOT_VALID') { throw "Installer tamper did not invalidate Authenticode." }

    # Logic-only negative cases use a small signed Windows PE fixture. They still
    # execute the exact production manifest generator and verifier, but avoid
    # repeatedly hashing the large OCR-bearing release installer for conditions
    # unrelated to artifact size.
    Write-Host "[Law-Rag][Stage19.3] Preparing small signed fixture for logic-only negative cases"
    $FixtureSource = Join-Path $env:SystemRoot 'System32\where.exe'
    if (-not (Test-Path $FixtureSource -PathType Leaf)) { throw "Windows signed-fixture source is unavailable: $FixtureSource" }
    $Fixture = Join-Path $OutputDir 'Law-Rag-stage19-3-fixture.exe'
    Copy-Item $FixtureSource $Fixture -Force
    Sign-FileChecked -Path $Fixture -Certificate $Primary -Label 'primary negative-case fixture'
    $FixtureManifest = New-SignedManifest `
        -Artifact $Fixture `
        -Version '0.8.0-rc3' `
        -Url 'https://updates.example.invalid/Law-Rag-stage19-3-fixture.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -Directory (Join-Path $OutputDir 'fixture-positive')

    Write-Host "[Law-Rag][Stage19.3] Validating manifest tamper rejection"
    $TamperedManifest = Join-Path $OutputDir 'UPDATE-MANIFEST-TAMPERED.json'
    Copy-Item $FixtureManifest.Manifest $TamperedManifest -Force
    [IO.File]::AppendAllText($TamperedManifest, ' ')
    $ManifestTamperEvidence = Join-Path $OutputDir 'STAGE19-3-MANIFEST-TAMPER.json'
    Invoke-ExpectedRefusal -Label 'manifest-tamper' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $TamperedManifest -ManifestSignaturePath $FixtureManifest.Cms -InstallerPath $Fixture -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $ManifestTamperEvidence -RequireEligible
    }
    if ((Read-Evidence $ManifestTamperEvidence).rejection_reasons -notcontains 'MANIFEST_CMS_INVALID') { throw "Manifest tamper did not fail at the CMS boundary." }

    Write-Host "[Law-Rag][Stage19.3] Validating signer mismatch rejection"
    $MismatchFixture = Join-Path $OutputDir 'Law-Rag-stage19-3-mismatch.exe'
    Copy-Item $FixtureSource $MismatchFixture -Force
    Sign-FileChecked -Path $MismatchFixture -Certificate $Other -Label 'mismatched-signer fixture'
    $MismatchManifest = New-SignedManifest `
        -Artifact $MismatchFixture `
        -Version '0.8.0-rc3' `
        -Url 'https://updates.example.invalid/Law-Rag-stage19-3-mismatch.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -Directory (Join-Path $OutputDir 'signer-mismatch')
    $MismatchEvidence = Join-Path $OutputDir 'STAGE19-3-SIGNER-MISMATCH.json'
    Invoke-ExpectedRefusal -Label 'signer-mismatch' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $MismatchManifest.Manifest -ManifestSignaturePath $MismatchManifest.Cms -InstallerPath $MismatchFixture -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $MismatchEvidence -RequireEligible
    }
    if ((Read-Evidence $MismatchEvidence).rejection_reasons -notcontains 'INSTALLER_SIGNER_MISMATCH') { throw "Signer mismatch was not detected." }

    Write-Host "[Law-Rag][Stage19.3] Validating version monotonicity rejection"
    $SameManifest = New-SignedManifest `
        -Artifact $Fixture `
        -Version '0.8.0-rc2' `
        -Url 'https://updates.example.invalid/Law-Rag-stage19-3-fixture.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -Directory (Join-Path $OutputDir 'same-version')
    $SameEvidence = Join-Path $OutputDir 'STAGE19-3-SAME-VERSION.json'
    Invoke-ExpectedRefusal -Label 'same-version' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $SameManifest.Manifest -ManifestSignaturePath $SameManifest.Cms -InstallerPath $Fixture -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $SameEvidence -RequireEligible
    }
    if ((Read-Evidence $SameEvidence).rejection_reasons -notcontains 'CANDIDATE_VERSION_NOT_NEWER') { throw "Same-version candidate was not rejected." }

    Write-Host "[Law-Rag][Stage19.3] Validating HTTPS boundary rejection"
    $HttpManifest = New-SignedManifest `
        -Artifact $Fixture `
        -Version '0.8.0-rc3' `
        -Url 'http://updates.example.invalid/Law-Rag-stage19-3-fixture.exe' `
        -SignerThumbprint $PrimaryThumbprint `
        -Directory (Join-Path $OutputDir 'http-url')
    $HttpEvidence = Join-Path $OutputDir 'STAGE19-3-HTTP-URL.json'
    Invoke-ExpectedRefusal -Label 'http-url' -Action {
        ./release/verify-stage19-3-update.ps1 -ManifestPath $HttpManifest.Manifest -ManifestSignaturePath $HttpManifest.Cms -InstallerPath $Fixture -CurrentVersion '0.8.0-rc2' -ExpectedSignerThumbprint $PrimaryThumbprint -EvidencePath $HttpEvidence -RequireEligible
    }
    if ((Read-Evidence $HttpEvidence).rejection_reasons -notcontains 'ARTIFACT_URL_NOT_SAFE_HTTPS') { throw "HTTP candidate was not rejected." }

    Write-Host "[Law-Rag] Stage 19.3 safe-update trust chain PASS"
    Write-Host "[Law-Rag] real installer positive + PE-section-tamper paths PASS"
    Write-Host "[Law-Rag] manifest/signer/version/HTTPS negative paths PASS"
    Write-Host "[Law-Rag] provider/network calls: 0"
}
finally {
    Remove-Item Env:LAW_RAG_RELEASE_SIGNER_THUMBPRINT -ErrorAction SilentlyContinue
    foreach ($Certificate in @($Primary, $Other)) {
        if ($null -eq $Certificate) { continue }
        $Thumbprint = $Certificate.Thumbprint
        foreach ($StoreName in @('My', 'Root', 'TrustedPublisher')) {
            Remove-Item "Cert:\CurrentUser\$StoreName\$Thumbprint" -Force -ErrorAction SilentlyContinue
        }
    }
}
