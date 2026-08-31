[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexgfx",
    [string] $DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string] $PythonExecutable = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $BaselineDirectory = (
        "\\VBOXSVR\codexdiag\client-baselines\wonderbane-20260831T023921516Z"
    ),
    [string] $ExpectedContentBuildId = "wb-55fbad5f-4b602995",
    [string] $ExtensionVersion = "1.4.5",
    [string] $ExtensionArtifact = (
        "\\VBOXSVR\codexgfx\build\wonderbane-graphics-baseline\Release\wonderbane-extension.dll"
    ),
    [string] $DestinationDirectory = (
        "S:\Wonderbane-graphics-wb-55fbad5f-4b602995-cel-1.4.5"
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
    @{ Path = $ExtensionArtifact; Description = "validated graphics extension artifact" }
)) {
    if (-not (Test-Path -LiteralPath $required.Path)) {
        throw "$($required.Description) was not found: $($required.Path)"
    }
}
if (Test-Path -LiteralPath $DestinationDirectory) {
    throw "Graphics package destination already exists: $DestinationDirectory"
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
foreach ($newEvidence in @($dryRunReceipt, $publicationReceipt)) {
    if (Test-Path -LiteralPath $newEvidence) {
        throw "Graphics package evidence already exists: $newEvidence"
    }
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
    --dry-run `
    --pretty
if ($LASTEXITCODE -ne 0) {
    throw "Graphics package dry run failed with exit code $LASTEXITCODE"
}
$extensionSha256 = (
    Get-FileHash -LiteralPath $ExtensionArtifact -Algorithm SHA256
).Hash.ToLowerInvariant()
$dryRun = [ordered]@{
    schema_version = 1
    status = "passed"
    completed_at_utc = [DateTime]::UtcNow.ToString("o")
    content_build_id = $contentBuildId
    baseline_tree_sha256 = $treeSha256
    extension_version = $ExtensionVersion
    extension_sha256 = $extensionSha256
    destination = $DestinationDirectory
} | ConvertTo-Json
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($dryRunReceipt, "$dryRun`n", $utf8)
if ($DryRunOnly) {
    Write-Output "Graphics package dry run passed: $contentBuildId"
    return
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
    destination = $DestinationDirectory
} | ConvertTo-Json
[IO.File]::WriteAllText($publicationReceipt, "$published`n", $utf8)

Write-Output "Graphics-only client published and verified: $DestinationDirectory"
Write-Output "WonderBane content build: $contentBuildId"
Write-Output "Graphics extension SHA-256: $extensionSha256"
