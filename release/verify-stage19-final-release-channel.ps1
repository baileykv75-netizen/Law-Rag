param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$ManifestSignaturePath,
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$SigningEvidencePath,
    [Parameter(Mandatory = $true)]
    [string]$ReleaseChannel,
    [Parameter(Mandatory = $true)]
    [string]$PublicationUrl,
    [Parameter(Mandatory = $true)]
    [string]$CurrentVersion,
    [string]$ConfigPath = (Join-Path $PSScriptRoot "stage19-final-acceptance-config.json"),
    [string]$OutputPath = (Join-Path $PSScriptRoot "final-acceptance\STAGE19-FINAL-RELEASE-CHANNEL-EVIDENCE.json")
)

$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Stage 19 final release-channel verification is Windows-only." }
if ($ReleaseChannel -notmatch '^[A-Za-z0-9._-]{1,64}$') {
    throw "ReleaseChannel must be a stable 1-64 character identifier using letters, digits, dot, underscore or hyphen."
}

function Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
}

function Normalize-Thumbprint([string]$Value) {
    if (-not $Value) { return "" }
    return (($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

function Require-SafeInstallerUrl([string]$Url, [string]$ExpectedFilename) {
    $Uri = $null
    $Valid = (
        [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$Uri) -and
        $Uri.Scheme -eq 'https' -and
        [bool]$Uri.Host -and
        -not $Uri.UserInfo -and
        -not $Uri.Query -and
        -not $Uri.Fragment
    )
    if (-not $Valid) { throw "PublicationUrl must be safe absolute HTTPS with no credentials, query or fragment." }
    $UrlFilename = [Uri]::UnescapeDataString([IO.Path]::GetFileName($Uri.AbsolutePath))
    if ($UrlFilename -ne $ExpectedFilename) {
        throw "PublicationUrl filename '$UrlFilename' does not match expected installer '$ExpectedFilename'."
    }
}

foreach ($InputPath in @($ConfigPath, $ManifestPath, $ManifestSignaturePath, $InstallerPath, $SigningEvidencePath)) {
    if (-not (Test-Path $InputPath -PathType Leaf)) { throw "Required final-channel input is missing: $InputPath" }
}

$Config = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$Baseline = $Config.engineering_candidate
$ExpectedSourceSha = ([string]$Baseline.source_sha).ToLowerInvariant()
$ExpectedReleaseLabel = [string]$Baseline.release_label
$ExpectedInstallerFilename = [string]$Baseline.installer.filename
if ($ExpectedSourceSha -notmatch '^[0-9a-f]{40}$') { throw "Configured final-acceptance source SHA is invalid." }
if (-not $ExpectedInstallerFilename -or $ExpectedInstallerFilename -ne [IO.Path]::GetFileName($ExpectedInstallerFilename)) {
    throw "Configured final-acceptance installer filename is invalid."
}
Require-SafeInstallerUrl -Url $PublicationUrl -ExpectedFilename $ExpectedInstallerFilename

$InstallerPath = (Resolve-Path $InstallerPath).Path
$ManifestPath = (Resolve-Path $ManifestPath).Path
$ManifestSignaturePath = (Resolve-Path $ManifestSignaturePath).Path
$SigningEvidencePath = (Resolve-Path $SigningEvidencePath).Path
if ([IO.Path]::GetFileName($InstallerPath) -ne $ExpectedInstallerFilename) {
    throw "Final-channel installer filename does not match the frozen RC3 installer identity."
}

$Signing = Get-Content $SigningEvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
$ExpectedSigner = Normalize-Thumbprint ([string]$Signing.expected_signer_thumbprint)
$InstallerSha = Sha256 $InstallerPath
if ([string]$Signing.schema_version -ne '1.0.0') { throw "Production signing evidence schema mismatch." }
if (([string]$Signing.source_sha).ToLowerInvariant() -ne $ExpectedSourceSha) { throw "Production signing evidence source SHA mismatch." }
if (-not [bool]$Signing.publication_allowed -or [string]$Signing.publication_state -ne 'SIGNED_TRUSTED_RELEASE_CANDIDATE') {
    throw "Production signing evidence is not publishable."
}
if (-not $ExpectedSigner -or ($ExpectedSigner.Length -ne 40 -and $ExpectedSigner.Length -ne 64)) {
    throw "Production signing evidence does not contain a valid expected signer thumbprint."
}
if (([string]$Signing.installer.sha256).ToLowerInvariant() -ne $InstallerSha) {
    throw "Final-channel installer does not match production signing evidence."
}
if ([string]$Signing.installer.authenticode_status -ne 'Valid') { throw "Production signing evidence does not mark installer Authenticode Valid." }
if ((Normalize-Thumbprint ([string]$Signing.installer.signer_thumbprint)) -ne $ExpectedSigner) {
    throw "Production signing installer signer does not match expected signer."
}

$Manifest = Get-Content $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$Manifest.schema_version -ne '1.0.0') { throw "Update manifest schema mismatch." }
if ([string]$Manifest.application_id -ne 'law-rag') { throw "Update manifest application ID mismatch." }
if ([string]$Manifest.target -ne 'windows-x64') { throw "Update manifest target mismatch." }
if ([string]$Manifest.version -ne $ExpectedReleaseLabel) { throw "Update manifest version does not match frozen RC3 release label." }
if (([string]$Manifest.source_commit_sha).ToLowerInvariant() -ne $ExpectedSourceSha) { throw "Update manifest source SHA mismatch." }
if ([string]$Manifest.artifact.filename -ne $ExpectedInstallerFilename) { throw "Update manifest installer filename mismatch." }
if ([string]$Manifest.artifact.url -ne $PublicationUrl) { throw "Update manifest URL does not equal the final publication URL." }
if (([string]$Manifest.artifact.sha256).ToLowerInvariant() -ne $InstallerSha) { throw "Update manifest installer SHA mismatch." }
if ([int64]$Manifest.artifact.size_bytes -ne [int64](Get-Item $InstallerPath).Length) { throw "Update manifest installer size mismatch." }
if ((Normalize-Thumbprint ([string]$Manifest.artifact.authenticode_signer_thumbprint)) -ne $ExpectedSigner) {
    throw "Update manifest declared signer does not match production signer."
}

$Scratch = Join-Path $env:RUNNER_TEMP ("law-rag-final-channel-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Scratch -Force | Out-Null
$Stage19EvidencePath = Join-Path $Scratch 'STAGE19-3-UPDATE-EVIDENCE.json'
try {
    & (Join-Path $PSScriptRoot 'verify-stage19-3-update.ps1') `
        -ManifestPath $ManifestPath `
        -ManifestSignaturePath $ManifestSignaturePath `
        -InstallerPath $InstallerPath `
        -CurrentVersion $CurrentVersion `
        -ExpectedSignerThumbprint $ExpectedSigner `
        -EvidencePath $Stage19EvidencePath `
        -RequireEligible
    if ($LASTEXITCODE -ne 0) { throw "Inherited Stage 19.3 update verification failed with exit code $LASTEXITCODE." }

    $Stage19 = Get-Content $Stage19EvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not [bool]$Stage19.eligible -or [string]$Stage19.decision -ne 'UPDATE_ELIGIBLE') {
        throw "Inherited Stage 19.3 update evidence is not eligible."
    }
    if ([string]$Stage19.manifest.cms_status -ne 'VALID') { throw "Final update manifest detached CMS is not valid." }
    if ((Normalize-Thumbprint ([string]$Stage19.manifest.signer_thumbprint)) -ne $ExpectedSigner) {
        throw "Final update manifest CMS signer does not match production signer."
    }
    if (([string]$Stage19.artifact.sha256).ToLowerInvariant() -ne $InstallerSha) {
        throw "Inherited Stage 19.3 evidence installer SHA mismatch."
    }
    if ([string]$Stage19.artifact.url -ne $PublicationUrl) {
        throw "Inherited Stage 19.3 evidence publication URL mismatch."
    }

    $Evidence = [ordered]@{
        schema_version = '1.0.0'
        stage = '19-final-release-channel'
        source_sha = $ExpectedSourceSha
        release_label = $ExpectedReleaseLabel
        release_channel = $ReleaseChannel
        publication_url = $PublicationUrl
        current_version = $CurrentVersion
        passed = $true
        expected_signer_thumbprint = $ExpectedSigner
        distribution_candidate = [ordered]@{
            installer = [ordered]@{
                filename = $ExpectedInstallerFilename
                sha256 = $InstallerSha
                size_bytes = [int64](Get-Item $InstallerPath).Length
                authenticode_status = [string]$Signing.installer.authenticode_status
                signer_thumbprint = Normalize-Thumbprint ([string]$Signing.installer.signer_thumbprint)
            }
        }
        update_manifest = [ordered]@{
            filename = [IO.Path]::GetFileName($ManifestPath)
            sha256 = Sha256 $ManifestPath
            signature_filename = [IO.Path]::GetFileName($ManifestSignaturePath)
            signature_sha256 = Sha256 $ManifestSignaturePath
            cms_status = [string]$Stage19.manifest.cms_status
            signer_thumbprint = Normalize-Thumbprint ([string]$Stage19.manifest.signer_thumbprint)
            source_commit_sha = ([string]$Manifest.source_commit_sha).ToLowerInvariant()
            candidate_version = [string]$Stage19.candidate_version
            installer_filename = [string]$Manifest.artifact.filename
            installer_sha256 = ([string]$Manifest.artifact.sha256).ToLowerInvariant()
            artifact_url = [string]$Manifest.artifact.url
            eligible = [bool]$Stage19.eligible
        }
        external_actions = [ordered]@{
            manifest_signing_executed_by_this_script = $false
            authenticode_signing_executed_by_this_script = $false
            provider_calls_executed_by_this_script = $false
            publication_executed_by_this_script = $false
        }
    }

    $Parent = Split-Path $OutputPath -Parent
    if ($Parent) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
    $Evidence | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 $OutputPath
    Write-Host '[Law-Rag] Stage 19 final release-channel verification PASS'
    Write-Host "[Law-Rag] Source SHA: $ExpectedSourceSha"
    Write-Host "[Law-Rag] Release channel: $ReleaseChannel"
    Write-Host "[Law-Rag] Publication URL: $PublicationUrl"
    Write-Host "[Law-Rag] Installer SHA-256: $InstallerSha"
    Write-Host "[Law-Rag] Production signer: $ExpectedSigner"
    Write-Host '[Law-Rag] publication performed by verifier: false'
}
finally {
    if (Test-Path $Scratch) { Remove-Item $Scratch -Recurse -Force -ErrorAction SilentlyContinue }
}
