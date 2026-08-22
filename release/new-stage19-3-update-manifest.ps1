param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$CandidateVersion,
    [Parameter(Mandatory = $true)]
    [string]$ArtifactUrl,
    [Parameter(Mandatory = $true)]
    [string]$SignerThumbprint,
    [string]$ManifestPath = (Join-Path $PSScriptRoot "update-dist\UPDATE-MANIFEST.json"),
    [string]$SignaturePath = (Join-Path $PSScriptRoot "update-dist\UPDATE-MANIFEST.p7s"),
    [string]$ApplicationId = "law-rag",
    [string]$Target = "windows-x64",
    [string]$PublishedAt = ([DateTimeOffset]::UtcNow.ToString("o"))
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($env:OS -ne "Windows_NT") {
    throw "Stage 19.3 update manifest signing is Windows-only."
}

Add-Type -AssemblyName System.Security.Cryptography.Pkcs

function Normalize-Thumbprint {
    param([string]$Value)
    if (-not $Value) { return "" }
    return (($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant())
}

$NormalizedSigner = Normalize-Thumbprint $SignerThumbprint
if ($NormalizedSigner.Length -ne 40 -and $NormalizedSigner.Length -ne 64) {
    throw "SignerThumbprint must be a normalized SHA-1 or SHA-256 certificate thumbprint."
}

$InstallerPath = (Resolve-Path $InstallerPath).Path
if (-not (Test-Path $InstallerPath -PathType Leaf)) {
    throw "Update installer is missing: $InstallerPath"
}

$CertificatePath = "Cert:\CurrentUser\My\$NormalizedSigner"
$Certificate = Get-Item $CertificatePath -ErrorAction Stop
if (-not $Certificate.HasPrivateKey) {
    throw "Update-manifest signer certificate does not have a private key."
}
if ((Normalize-Thumbprint ([string]$Certificate.Thumbprint)) -ne $NormalizedSigner) {
    throw "Resolved signer certificate thumbprint does not match the requested signer."
}

$SourceSha = (& git -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $SourceSha -notmatch '^[0-9a-f]{40}$') {
    throw "Could not resolve exact source SHA for Stage 19.3 update manifest."
}

$Artifact = [ordered]@{
    filename = [IO.Path]::GetFileName($InstallerPath)
    url = $ArtifactUrl
    sha256 = (Get-FileHash -Algorithm SHA256 $InstallerPath).Hash.ToLowerInvariant()
    size_bytes = [int64](Get-Item $InstallerPath).Length
    authenticode_signer_thumbprint = $NormalizedSigner
}

$Manifest = [ordered]@{
    schema_version = "1.0.0"
    application_id = $ApplicationId
    target = $Target
    version = $CandidateVersion
    published_at = $PublishedAt
    source_commit_sha = $SourceSha
    artifact = $Artifact
}

$ManifestJson = $Manifest | ConvertTo-Json -Depth 8 -Compress
$ManifestBytes = [Text.UTF8Encoding]::new($false).GetBytes($ManifestJson)

$ManifestDir = Split-Path $ManifestPath -Parent
if ($ManifestDir) { New-Item -ItemType Directory -Path $ManifestDir -Force | Out-Null }
$SignatureDir = Split-Path $SignaturePath -Parent
if ($SignatureDir) { New-Item -ItemType Directory -Path $SignatureDir -Force | Out-Null }

[IO.File]::WriteAllBytes($ManifestPath, $ManifestBytes)

$ContentInfo = [System.Security.Cryptography.Pkcs.ContentInfo]::new($ManifestBytes)
$SignedCms = [System.Security.Cryptography.Pkcs.SignedCms]::new($ContentInfo, $true)
$CmsSigner = [System.Security.Cryptography.Pkcs.CmsSigner]::new(
    [System.Security.Cryptography.Pkcs.SubjectIdentifierType]::IssuerAndSerialNumber,
    $Certificate
)
$CmsSigner.IncludeOption = [System.Security.Cryptography.X509Certificates.X509IncludeOption]::EndCertOnly
$SignedCms.ComputeSignature($CmsSigner, $false)
[IO.File]::WriteAllBytes($SignaturePath, $SignedCms.Encode())

Write-Host "[Law-Rag] Stage 19.3 signed update manifest created."
Write-Host "[Law-Rag] Manifest: $ManifestPath"
Write-Host "[Law-Rag] Signature: $SignaturePath"
Write-Host "[Law-Rag] Candidate: $CandidateVersion"
Write-Host "[Law-Rag] Installer SHA-256: $($Artifact.sha256)"
Write-Host "[Law-Rag] Signer: $NormalizedSigner"
