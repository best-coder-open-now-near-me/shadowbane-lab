[CmdletBinding()]
param(
    [string] $EvidenceDirectory = "\\VBOXSVR\codexdiag\client-extension-evidence\wonderbane-20260830T141558722Z",
    [string] $FrozenBaselineDirectory = "",
    [string] $DestinationDirectory = "\\VBOXSVR\codexdiag\client-extension-working\wonderbane-1.0.5-world-map-click-v1",
    [string] $ExtensionArtifact = "\\VBOXSVR\codexrepo\build\wonderbane-client-extension-final\Release\wonderbane-extension.dll",
    [string] $ManifestPath = "",
    [string] $ExtensionVersion = "1.2.0",
    [string] $TexturePatchManifest = "",
    [string] $TextureArtifactDirectory = "",
    [string] $PythonExecutable = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [switch] $DryRunOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositorySource = Join-Path (Split-Path -Parent $PSScriptRoot) "src"
$baselineDirectory = if ([string]::IsNullOrWhiteSpace($FrozenBaselineDirectory)) {
    Join-Path $EvidenceDirectory "client-baseline"
}
else {
    $FrozenBaselineDirectory
}
$sourceExecutable = Join-Path $baselineDirectory "sb.exe"
$packageId = Split-Path -Leaf $DestinationDirectory
if (-not $ManifestPath) {
    $ManifestPath = Join-Path $EvidenceDirectory "$packageId.manifest.json"
}
if ([string]::IsNullOrWhiteSpace($TexturePatchManifest) -xor [string]::IsNullOrWhiteSpace($TextureArtifactDirectory)) {
    throw "TexturePatchManifest and TextureArtifactDirectory must be supplied together."
}

$requiredFiles = @(
    @{ Path = $PythonExecutable; Description = "guest Python environment" },
    @{ Path = $sourceExecutable; Description = "frozen reviewed executable" },
    @{ Path = (Join-Path $baselineDirectory "client-baseline.json"); Description = "frozen baseline evidence" },
    @{ Path = $ExtensionArtifact; Description = "reviewed extension artifact" }
)
foreach ($required in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $required.Path -PathType Leaf)) {
        throw "$($required.Description) was not found: $($required.Path)"
    }
}
if ($TexturePatchManifest -and -not (Test-Path -LiteralPath $TexturePatchManifest -PathType Leaf)) {
    throw "Reviewed texture-patch manifest was not found: $TexturePatchManifest"
}
if ($TextureArtifactDirectory -and -not (Test-Path -LiteralPath $TextureArtifactDirectory -PathType Container)) {
    throw "Texture artifact directory was not found: $TextureArtifactDirectory"
}
if (-not (Test-Path -LiteralPath $repositorySource -PathType Container)) {
    throw "Repository Python source directory was not found: $repositorySource"
}
if (Test-Path -LiteralPath $DestinationDirectory) {
    throw "Disposable destination already exists: $DestinationDirectory"
}

$inheritedPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($inheritedPythonPath)) {
    $repositorySource
}
else {
    "$repositorySource$([IO.Path]::PathSeparator)$inheritedPythonPath"
}
$textureArguments = @()
if ($TexturePatchManifest) {
    $textureArguments = @(
        "--texture-patch-manifest", $TexturePatchManifest,
        "--texture-artifact-directory", $TextureArtifactDirectory
    )
}

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    & $PythonExecutable -m shadowbane_lab.client_extension `
        author-bootstrap `
        $sourceExecutable `
        $ExtensionArtifact `
        $ManifestPath `
        --extension-version $ExtensionVersion `
        --pretty
    if ($LASTEXITCODE -ne 0) {
        throw "Bootstrap manifest authoring failed with exit code $LASTEXITCODE"
    }
}

& $PythonExecutable -m shadowbane_lab.client_extension `
    prepare-copy `
    $baselineDirectory `
    $DestinationDirectory `
    $ManifestPath `
    $ExtensionArtifact `
    @textureArguments `
    --dry-run `
    --pretty
if ($LASTEXITCODE -ne 0) {
    throw "Disposable client dry run failed with exit code $LASTEXITCODE"
}
if ($DryRunOnly) {
    $receiptPath = Join-Path $EvidenceDirectory "$packageId.dry-run.json"
    if (Test-Path -LiteralPath $receiptPath) {
        throw "Dry-run receipt already exists: $receiptPath"
    }
    $receipt = [ordered]@{
        schema_version = 1
        status = "passed"
        completed_at_utc = [DateTime]::UtcNow.ToString("o")
        manifest = [IO.Path]::GetFileName($ManifestPath)
        destination = $DestinationDirectory
    } | ConvertTo-Json
    $encoding = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText($receiptPath, "$receipt`n", $encoding)
    Write-Output "Disposable client dry run passed; no destination was created."
    return
}

& $PythonExecutable -m shadowbane_lab.client_extension `
    prepare-copy `
    $baselineDirectory `
    $DestinationDirectory `
    $ManifestPath `
    $ExtensionArtifact `
    @textureArguments `
    --pretty
if ($LASTEXITCODE -ne 0) {
    throw "Disposable client publication failed with exit code $LASTEXITCODE"
}
Write-Output "Disposable client copy published and reread successfully: $DestinationDirectory"
