[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexdiagtools",
    [string] $DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string] $PythonExecutable = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $ClientDirectory = "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane",
    [string] $ExpectedVanillaExecutableSha256 = "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc",
    [string] $ExtensionVersion = "1.6.13",
    [string] $ExpectedExtensionSha256 = "f51119f8584d482fe40d73c183f6ebacdeb75f962688e2d6200483a7e16e740c",
    [string] $ExtensionArtifact = "\\VBOXSVR\codexdiagtools\build\wonderbane-diagnostics-extension\Release\wonderbane-extension.dll",
    [ValidatePattern("(?-i)^[a-z0-9][a-z0-9-]{0,31}$")]
    [string] $InstanceId = "primary",
    [string] $DestinationDirectory = "",
    [string] $CurrentReceipt = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DestinationDirectory)) {
    $DestinationDirectory = Join-Path $env:USERPROFILE (
        "Wonderbane-diagnostics-wb-55fbad5f-present-$ExtensionVersion-$InstanceId"
    )
}
if ([string]::IsNullOrWhiteSpace($CurrentReceipt)) {
    $CurrentReceipt = Join-Path $env:LOCALAPPDATA (
        "ShadowbaneLab\diagnostics-client\current-$InstanceId.json"
    )
}

function Remove-ExactTransientBaseline {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Root,
        [Parameter(Mandatory = $true)]
        [string] $Directory
    )
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
        return
    }
    $resolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd("\")
    $resolvedDirectory = [IO.Path]::GetFullPath($Directory).TrimEnd("\")
    if ((Split-Path -Parent $resolvedDirectory).TrimEnd("\") -cne $resolvedRoot) {
        throw "Refusing to remove a transient baseline outside $resolvedRoot"
    }
    $leaf = Split-Path -Leaf $resolvedDirectory
    if ($leaf -notmatch "^wbdiag-[0-9a-f]{32}$") {
        throw "Refusing to remove a non-canonical transient baseline: $resolvedDirectory"
    }
    $item = Get-Item -LiteralPath $resolvedDirectory -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to remove a reparse-point transient baseline: $resolvedDirectory"
    }
    Remove-Item -LiteralPath $resolvedDirectory -Recurse -Force
}

foreach ($required in @(
    @{ Path = $RepositoryShare; Kind = "Container"; Description = "diagnostics repository share" },
    @{ Path = $DiagnosticsShare; Kind = "Container"; Description = "diagnostics evidence share" },
    @{ Path = $PythonExecutable; Kind = "Leaf"; Description = "guest Python environment" },
    @{ Path = $ClientDirectory; Kind = "Container"; Description = "source client directory" },
    @{ Path = $ExtensionArtifact; Kind = "Leaf"; Description = "diagnostics-only extension" }
)) {
    if (-not (Test-Path -LiteralPath $required.Path -PathType $required.Kind)) {
        throw "$($required.Description) was not found: $($required.Path)"
    }
}
$sourceExecutable = Join-Path $ClientDirectory "sb.exe"
if (-not (Test-Path -LiteralPath $sourceExecutable -PathType Leaf)) {
    throw "Source client executable was not found: $sourceExecutable"
}
$resolvedSourceExecutable = [IO.Path]::GetFullPath(
    (Resolve-Path -LiteralPath $sourceExecutable).Path
)
$runningSourceClients = @()
foreach ($runningClient in @(Get-Process -Name "sb" -ErrorAction SilentlyContinue)) {
    try {
        $candidatePath = $runningClient.Path
    }
    catch {
        throw "Could not inspect existing sb.exe PID $($runningClient.Id); refusing publication from an ambiguous source state"
    }
    if (-not $candidatePath) {
        throw "Existing sb.exe PID $($runningClient.Id) has no inspectable executable path; refusing publication from an ambiguous source state"
    }
    if ([string]::Equals(
        [IO.Path]::GetFullPath($candidatePath),
        $resolvedSourceExecutable,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        $runningSourceClients += $runningClient
    }
}
if ($runningSourceClients.Count -gt 0) {
    $sourceProcessIds = ($runningSourceClients.Id | Sort-Object) -join ", "
    throw "Close the source vanilla sb.exe before publication (PID: $sourceProcessIds). Existing diagnostics-package clients may remain open."
}
if (Test-Path -LiteralPath $DestinationDirectory) {
    throw "Diagnostics client destination already exists: $DestinationDirectory"
}
$actualVanillaExecutableSha256 = (Get-FileHash -LiteralPath $sourceExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualVanillaExecutableSha256 -ne $ExpectedVanillaExecutableSha256) {
    throw "Source sb.exe is not the reviewed vanilla release: expected $ExpectedVanillaExecutableSha256, found $actualVanillaExecutableSha256"
}
foreach ($residue in @(
    (Join-Path $ClientDirectory "wonderbane-extension.dll"),
    (Join-Path $ClientDirectory ".wonderbane-extension")
)) {
    if (Test-Path -LiteralPath $residue) {
        throw "Source client contains extension-package residue: $residue"
    }
}
$actualExtensionSha256 = (Get-FileHash -LiteralPath $ExtensionArtifact -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualExtensionSha256 -ne $ExpectedExtensionSha256) {
    throw "Diagnostics-only extension identity mismatch: expected $ExpectedExtensionSha256, found $actualExtensionSha256"
}

$gitRepositoryPath = $RepositoryShare.Replace("\", "/").TrimEnd("/")
$gitSafeDirectory = "$gitRepositoryPath/"
if ($gitRepositoryPath.StartsWith("//")) {
    $gitSafeDirectory = "%(prefix)/$gitRepositoryPath/"
}
$revisionOutput = @(& git -c "safe.directory=$gitSafeDirectory" -C $RepositoryShare rev-parse HEAD)
if ($LASTEXITCODE -ne 0 -or $revisionOutput.Count -ne 1) {
    throw "Could not resolve the diagnostics repository revision"
}
$repositoryRevision = $revisionOutput[0].Trim()
if (-not $repositoryRevision) {
    throw "Diagnostics repository revision was empty"
}

$destinationParent = Split-Path -Parent $DestinationDirectory
if (-not $destinationParent -or -not (Test-Path -LiteralPath $destinationParent -PathType Container)) {
    throw "Diagnostics client destination must have an existing local parent"
}
$destinationDrive = Split-Path -Qualifier $DestinationDirectory
if (-not $destinationDrive) {
    throw "Diagnostics client destination must use an explicit local drive"
}

$transientRoot = Join-Path $DiagnosticsShare "transient-client-baselines"
$transientName = "wbdiag-$([guid]::NewGuid().ToString('N'))"
$transientBaseline = Join-Path $transientRoot $transientName
$evidenceDirectory = Join-Path (
    Join-Path $DiagnosticsShare "diagnostics-client-packages"
) "wb-55fbad5f-present-$ExtensionVersion-$InstanceId"
$manifestPath = Join-Path $evidenceDirectory "bootstrap.manifest.json"
$baselineEvidencePath = Join-Path $evidenceDirectory "source-baseline.manifest.json"
$publicationReceipt = Join-Path $evidenceDirectory "publication.json"
if (Test-Path -LiteralPath $publicationReceipt) {
    throw "Diagnostics publication evidence already exists: $publicationReceipt"
}
New-Item -ItemType Directory -Path $transientRoot -Force | Out-Null
New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null

$repositorySource = Join-Path $RepositoryShare "src"
$inheritedPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($inheritedPythonPath)) {
    $repositorySource
}
else {
    "$repositorySource$([IO.Path]::PathSeparator)$inheritedPythonPath"
}

try {
    $freezeArguments = @(
        "-m", "shadowbane_lab.client_extension", "freeze-baseline",
        $ClientDirectory, $transientBaseline,
        "--executable", "sb.exe",
        "--repository-revision", $repositoryRevision,
        "--pretty"
    )
    & $PythonExecutable @freezeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Transient client snapshot failed with exit code $LASTEXITCODE"
    }
    $baselineManifest = Join-Path $transientBaseline "client-baseline.json"
    $baseline = Get-Content -LiteralPath $baselineManifest -Raw | ConvertFrom-Json
    if ([string] $baseline.executable.sha256 -ne $ExpectedVanillaExecutableSha256) {
        throw "Transient snapshot executable identity differs from the reviewed source"
    }
    Copy-Item -LiteralPath $baselineManifest -Destination $baselineEvidencePath -Force

    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        $authorArguments = @(
            "-m", "shadowbane_lab.client_extension", "author-bootstrap",
            (Join-Path $transientBaseline "sb.exe"),
            $ExtensionArtifact,
            $manifestPath,
            "--extension-version", $ExtensionVersion,
            "--pretty"
        )
        & $PythonExecutable @authorArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Diagnostics bootstrap manifest authoring failed with exit code $LASTEXITCODE"
        }
    }

    $prepareArguments = @(
        "-m", "shadowbane_lab.client_extension", "prepare-copy",
        $transientBaseline,
        $DestinationDirectory,
        $manifestPath,
        $ExtensionArtifact,
        "--pretty"
    )
    & $PythonExecutable @prepareArguments "--dry-run"
    if ($LASTEXITCODE -ne 0) {
        throw "Diagnostics client dry run failed with exit code $LASTEXITCODE"
    }

    $driveName = $destinationDrive.TrimEnd("\").TrimEnd(":")
    $drive = Get-PSDrive -Name $driveName -PSProvider FileSystem -ErrorAction Stop
    $requiredFreeBytes = [int64] $baseline.total_file_bytes + 512MB
    if ([int64] $drive.Free -lt $requiredFreeBytes) {
        throw "Insufficient free space on $($destinationDrive): require $requiredFreeBytes bytes, found $($drive.Free)"
    }

    & $PythonExecutable @prepareArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Diagnostics client publication failed with exit code $LASTEXITCODE"
    }
    $verificationArguments = @(
        "-m", "shadowbane_lab.client_extension", "verify-copy", $DestinationDirectory
    )
    $verificationOutput = @(& $PythonExecutable @verificationArguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Published diagnostics client verification failed with exit code $LASTEXITCODE"
    }
    $package = ($verificationOutput -join [Environment]::NewLine) | ConvertFrom-Json
    if ([string] $package.extension_sha256 -ne $ExpectedExtensionSha256) {
        throw "Published package extension identity changed after publication"
    }

    $published = [ordered]@{
        schema_version = 1
        status = "published_and_verified"
        completed_at_utc = [DateTime]::UtcNow.ToString("o")
        repository_revision = $repositoryRevision
        instance_id = $InstanceId
        runtime_profile = "diagnostics-only"
        extension_version = $ExtensionVersion
        extension_sha256 = $ExpectedExtensionSha256
        source_executable_sha256 = $ExpectedVanillaExecutableSha256
        result_executable_sha256 = [string] $package.result_executable_sha256
        source_tree_sha256 = [string] $baseline.tree_sha256
        working_tree_sha256 = [string] $package.working_tree_sha256
        package_directory = $DestinationDirectory
        baseline_payload_retained = $false
        baseline_manifest = $baselineEvidencePath
    }
    $utf8 = [Text.UTF8Encoding]::new($false)
    $publicationJson = $published | ConvertTo-Json
    [IO.File]::WriteAllText(
        $publicationReceipt,
        $publicationJson + [Environment]::NewLine,
        $utf8
    )

    $currentParent = Split-Path -Parent $CurrentReceipt
    New-Item -ItemType Directory -Path $currentParent -Force | Out-Null
    $currentTemporary = Join-Path $currentParent ".current-$([guid]::NewGuid().ToString('N')).tmp"
    [IO.File]::WriteAllText(
        $currentTemporary,
        $publicationJson + [Environment]::NewLine,
        $utf8
    )
    Move-Item -LiteralPath $currentTemporary -Destination $CurrentReceipt -Force
}
finally {
    $env:PYTHONPATH = $inheritedPythonPath
    Remove-ExactTransientBaseline -Root $transientRoot -Directory $transientBaseline
}

Write-Output "Diagnostics-only client published and verified: $DestinationDirectory"
Write-Output "Instance: $InstanceId"
Write-Output "Runtime profile: diagnostics-only"
Write-Output "Extension SHA-256: $ExpectedExtensionSha256"
Write-Output "The temporary full client snapshot was removed after publication."
