[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexgfx",
    [string] $DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string] $PythonExecutable = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $BaselineDirectory = (
        "\\VBOXSVR\codexdiag\client-baselines\wonderbane-20260831T023921516Z"
    ),
    [string] $ExpectedContentBuildId = "wb-55fbad5f-4b602995",
    [string] $ExpectedExtensionSha256 = (
        "67a10b2b414c4fb94f6d40aa916ea1610f5daa7e24e3accdfb4bf917bbb8c936"
    ),
    [string] $ExtensionVersion = "1.5.7",
    [string] $ExtensionArtifact = (
        "\\VBOXSVR\codexgfx\build\wonderbane-client-extension\Release\wonderbane-extension-1.5.7.dll"
    ),
    [string] $TexturePatchManifest = (
        "\\VBOXSVR\codexgfx\assets\wonderbane_graphics\restrained-cel-v1\texture-patches.json"
    ),
    [string] $TextureArtifactDirectory = (
        "\\VBOXSVR\codexgfx\assets\wonderbane_graphics\restrained-cel-v1"
    ),
    [string] $DestinationDirectory = (
        "S:\Wonderbane-graphics-wb-55fbad5f-4b602995-cel-1.5.7"
    ),
    [switch] $DryRunOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

foreach ($required in @(
    @{ Path = $RepositoryShare; Description = "graphics-only repository share" },
    @{ Path = $DiagnosticsShare; Description = "diagnostics share" },
    @{ Path = $PythonExecutable; Description = "guest Python environment" },
    @{ Path = $BaselineDirectory; Description = "frozen official client baseline" },
    @{ Path = $ExtensionArtifact; Description = "validated graphics extension artifact" },
    @{
        Path = $TexturePatchManifest
        Description = "reviewed restrained-cel texture manifest"
    },
    @{
        Path = $TextureArtifactDirectory
        Description = "reviewed restrained-cel texture artifacts"
    }
)) {
    if (-not (Test-Path -LiteralPath $required.Path)) {
        throw "$($required.Description) was not found: $($required.Path)"
    }
}
if (Test-Path -LiteralPath $DestinationDirectory) {
    throw "Graphics package destination already exists: $DestinationDirectory"
}
$extensionSha256 = (
    Get-FileHash -LiteralPath $ExtensionArtifact -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($ExpectedExtensionSha256 -notmatch "^[0-9a-f]{64}$") {
    throw "Expected graphics extension SHA-256 is not a lowercase SHA-256"
}
if ($extensionSha256 -cne $ExpectedExtensionSha256) {
    throw (
        "Graphics extension identity mismatch: expected $ExpectedExtensionSha256, " +
        "found $extensionSha256"
    )
}

$baselineManifest = Join-Path $BaselineDirectory "client-baseline.json"
if (-not (Test-Path -LiteralPath $baselineManifest -PathType Leaf)) {
    throw "Frozen baseline evidence was not found: $baselineManifest"
}
$baseline = Get-Content -LiteralPath $baselineManifest -Raw | ConvertFrom-Json
$executableSha256 = [string] $baseline.executable.sha256
$treeSha256 = [string] $baseline.tree_sha256
if ($executableSha256.Length -ne 64 -or $treeSha256.Length -ne 64) {
    throw "Frozen baseline evidence did not contain complete SHA-256 identities"
}
$contentBuildId = "wb-{0}-{1}" -f `
    $executableSha256.Substring(0, 8), `
    $treeSha256.Substring(0, 8)
if ($contentBuildId -ne $ExpectedContentBuildId) {
    throw (
        "Frozen baseline identity mismatch: expected $ExpectedContentBuildId, " +
        "found $contentBuildId"
    )
}

$evidenceDirectory = Join-Path `
    (Join-Path $DiagnosticsShare "graphics-packages") `
    "$contentBuildId-cel-$ExtensionVersion"
if (-not (Test-Path -LiteralPath $evidenceDirectory)) {
    New-Item -ItemType Directory -Path $evidenceDirectory | Out-Null
}
$manifestPath = Join-Path $evidenceDirectory "bootstrap.manifest.json"
$dryRunReceipt = Join-Path $evidenceDirectory "dry-run.json"
$publicationReceipt = Join-Path $evidenceDirectory "publication.json"
if (Test-Path -LiteralPath $publicationReceipt) {
    throw "Graphics package publication evidence already exists: $publicationReceipt"
}

$env:PYTHONPATH = Join-Path $RepositoryShare "src"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    & $PythonExecutable -m shadowbane_lab.client_extension `
        author-bootstrap `
        (Join-Path $BaselineDirectory "sb.exe") `
        $ExtensionArtifact `
        $manifestPath `
        --extension-version $ExtensionVersion `
        --pretty
    if ($LASTEXITCODE -ne 0) {
        throw "55fb bootstrap manifest authoring failed with exit code $LASTEXITCODE"
    }
}

& $PythonExecutable -m shadowbane_lab.client_extension `
    prepare-copy `
    $BaselineDirectory `
    $DestinationDirectory `
    $manifestPath `
    $ExtensionArtifact `
    --texture-patch-manifest $TexturePatchManifest `
    --texture-artifact-directory $TextureArtifactDirectory `
    --dry-run `
    --pretty
if ($LASTEXITCODE -ne 0) {
    throw "Graphics package dry run failed with exit code $LASTEXITCODE"
}
$texturePatch = Get-Content -LiteralPath $TexturePatchManifest -Raw | ConvertFrom-Json
$texturePatchId = [string] $texturePatch.patch_id
$texturePatchManifestSha256 = (
    Get-FileHash -LiteralPath $TexturePatchManifest -Algorithm SHA256
).Hash.ToLowerInvariant()
$expectedDryRun = [ordered]@{
    schema_version = 1
    status = "passed"
    content_build_id = $contentBuildId
    baseline_tree_sha256 = $treeSha256
    extension_version = $ExtensionVersion
    extension_sha256 = $extensionSha256
    texture_patch_id = $texturePatchId
    texture_patch_manifest_sha256 = $texturePatchManifestSha256
    destination = $DestinationDirectory
}
$utf8 = [Text.UTF8Encoding]::new($false)
if (Test-Path -LiteralPath $dryRunReceipt -PathType Leaf) {
    $existingDryRun = Get-Content -LiteralPath $dryRunReceipt -Raw | ConvertFrom-Json
    foreach ($field in $expectedDryRun.Keys) {
        $property = $existingDryRun.PSObject.Properties[$field]
        if ($null -eq $property -or [string] $property.Value -cne [string] $expectedDryRun[$field]) {
            throw "Existing graphics dry-run receipt does not match field '$field': $dryRunReceipt"
        }
    }
    Write-Output "Reused matching graphics package dry-run receipt: $dryRunReceipt"
}
else {
    $newDryRun = [ordered]@{
        schema_version = $expectedDryRun.schema_version
        status = $expectedDryRun.status
        completed_at_utc = [DateTime]::UtcNow.ToString("o")
        content_build_id = $expectedDryRun.content_build_id
        baseline_tree_sha256 = $expectedDryRun.baseline_tree_sha256
        extension_version = $expectedDryRun.extension_version
        extension_sha256 = $expectedDryRun.extension_sha256
        texture_patch_id = $expectedDryRun.texture_patch_id
        texture_patch_manifest_sha256 = $expectedDryRun.texture_patch_manifest_sha256
        destination = $expectedDryRun.destination
    } | ConvertTo-Json
    [IO.File]::WriteAllText($dryRunReceipt, "$newDryRun`n", $utf8)
}
if ($DryRunOnly) {
    Write-Output "Graphics package dry run passed: $contentBuildId"
    return
}

$runningGame = Get-Process -Name "sb" -ErrorAction SilentlyContinue
if ($null -ne $runningGame) {
    throw "Close every running sb.exe before replacing the managed graphics package"
}
$destinationRoot = Split-Path -Parent $DestinationDirectory
if (-not $destinationRoot -or -not (Test-Path -LiteralPath $destinationRoot -PathType Container)) {
    throw "Graphics package destination must have an existing local parent directory"
}
$resolvedDestinationRoot = (Resolve-Path -LiteralPath $destinationRoot).Path.TrimEnd("\")
$currentPackagePattern = "^Wonderbane-graphics-{0}-cel-[0-9]+\.[0-9]+\.[0-9]+$" -f `
    [regex]::Escape($contentBuildId)
$legacyPackagePattern = `
    "^Wonderbane-55fb-extension-[0-9]+\.[0-9]+\.[0-9]+-(cel|flat|hardware)-v[0-9]+$"
$obsoletePackages = Get-ChildItem -LiteralPath $resolvedDestinationRoot -Directory | Where-Object {
    $_.Name -match $currentPackagePattern -or $_.Name -match $legacyPackagePattern
}
foreach ($obsoletePackage in $obsoletePackages) {
    if ($obsoletePackage.FullName -eq $DestinationDirectory) {
        throw "Refusing to replace an existing destination package in place"
    }
    if (($obsoletePackage.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to remove a reparse-point graphics package: $($obsoletePackage.FullName)"
    }
    $resolvedPackage = (Resolve-Path -LiteralPath $obsoletePackage.FullName).Path
    $resolvedParent = (Split-Path -Parent $resolvedPackage).TrimEnd("\")
    if ($resolvedParent -cne $resolvedDestinationRoot) {
        throw "Refusing to remove a graphics package outside $resolvedDestinationRoot"
    }
    Remove-Item -LiteralPath $resolvedPackage -Recurse -Force
    Write-Output "Removed obsolete graphics package: $resolvedPackage"
}

$destinationDrive = Split-Path -Qualifier $DestinationDirectory
if (-not $destinationDrive) {
    throw "Graphics package destination must be on an explicit local drive"
}
$driveName = $destinationDrive.TrimEnd("\").TrimEnd(":")
$drive = Get-PSDrive -Name $driveName -PSProvider FileSystem -ErrorAction Stop
$requiredFreeBytes = [int64] $baseline.total_file_bytes + 512MB
if ([int64] $drive.Free -lt $requiredFreeBytes) {
    throw (
        "Insufficient free space on $destinationDrive; require $requiredFreeBytes bytes, " +
        "found $($drive.Free)"
    )
}

& $PythonExecutable -m shadowbane_lab.client_extension `
    prepare-copy `
    $BaselineDirectory `
    $DestinationDirectory `
    $manifestPath `
    $ExtensionArtifact `
    --texture-patch-manifest $TexturePatchManifest `
    --texture-artifact-directory $TextureArtifactDirectory `
    --pretty
if ($LASTEXITCODE -ne 0) {
    throw "Graphics package publication failed with exit code $LASTEXITCODE"
}
& $PythonExecutable -m shadowbane_lab.client_extension `
    verify-copy `
    $DestinationDirectory `
    --pretty
if ($LASTEXITCODE -ne 0) {
    throw "Published graphics package verification failed with exit code $LASTEXITCODE"
}

$published = [ordered]@{
    schema_version = 1
    status = "published_and_verified"
    completed_at_utc = [DateTime]::UtcNow.ToString("o")
    content_build_id = $contentBuildId
    baseline_tree_sha256 = $treeSha256
    extension_version = $ExtensionVersion
    extension_sha256 = $extensionSha256
    texture_patch_id = $texturePatchId
    texture_patch_manifest_sha256 = $texturePatchManifestSha256
    destination = $DestinationDirectory
} | ConvertTo-Json
[IO.File]::WriteAllText($publicationReceipt, "$published`n", $utf8)

Write-Output "Graphics-only client published and verified: $DestinationDirectory"
Write-Output "WonderBane content build: $contentBuildId"
Write-Output "Graphics extension SHA-256: $extensionSha256"
Write-Output "Texture overlay: $texturePatchId"
