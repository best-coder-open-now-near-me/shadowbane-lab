[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexrepo",
    [string] $DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string] $VanillaClientDirectory = (
        "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane"
    ),
    [string] $PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $LocalStateRoot = "$env:LOCALAPPDATA\ShadowbaneLab",
    [string] $ManagerManifest = "$env:LOCALAPPDATA\ShadowbaneLab\client-manager.json",
    [ValidateRange(1, 32)]
    [int] $ClientCount = 2,
    [ValidateRange(320, 16384)]
    [int] $ResolutionWidth = 1920,
    [ValidateRange(240, 16384)]
    [int] $ResolutionHeight = 955,
    [string] $ExtensionArtifact = (
        "\\VBOXSVR\codexrepo\build\wonderbane-client-extension-final\Release\" +
        "wonderbane-extension.dll"
    ),
    [string] $ExtensionVersion = "1.3.0",
    [string] $ExpectedVanillaExecutableSha256 = (
        "e358237c458ddfe2fc7a86e478f165a8fd067655ab1a8ada5731f790c6995d96"
    ),
    [string] $ExpectedVanillaTexturesCacheSha256 = (
        "cb3ea8c036e4227a7d0a7d02d72f49229c8365e190dd7535318aec753e7c3b3e"
    ),
    [switch] $NoStartupShortcut,
    [switch] $StartNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-GuestLocalPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Description
    )
    $fullPath = [IO.Path]::GetFullPath($Path)
    if ($fullPath.StartsWith("\\")) {
        throw "$Description must be guest-local, not a VirtualBox or UNC share: $fullPath"
    }
}

function Stop-ExactManager {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ManifestPath,
        [Parameter(Mandatory = $true)]
        [string] $StateRoot
    )
    $expectedManifest = [regex]::Escape($ManifestPath)
    $exactManagers = @(
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
            Where-Object {
                $_.CommandLine -match "shadowbane_lab\.cli\s+manager\s+app" -and
                $_.CommandLine -match $expectedManifest
            }
    )
    if ($exactManagers.Count -eq 0) {
        return
    }

    $pidPath = Join-Path $StateRoot "manager.pid"
    if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
        throw "Found an untracked manager process; refusing to stop it: $($exactManagers.ProcessId -join ', ')"
    }
    $trackedText = (Get-Content -LiteralPath $pidPath -Raw).Trim()
    $trackedId = 0
    if (-not [int]::TryParse($trackedText, [ref]$trackedId) -or $trackedId -le 0) {
        throw "Manager PID file is invalid: $pidPath"
    }
    if (@($exactManagers | Where-Object { $_.ProcessId -eq $trackedId }).Count -ne 1) {
        throw "The tracked manager PID does not identify the exact manager command."
    }
    if ($exactManagers.Count -ne 1) {
        throw "Found competing manager processes; refusing to stop any of them."
    }

    Stop-Process -Id $trackedId
    $deadline = (Get-Date).AddSeconds(5)
    while ($null -ne (Get-Process -Id $trackedId -ErrorAction SilentlyContinue)) {
        if ((Get-Date) -ge $deadline) {
            throw "Manager PID $trackedId did not stop within five seconds."
        }
        Start-Sleep -Milliseconds 100
    }
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    Write-Output "Stopped exact WonderBane manager PID $trackedId before deployment."
}

Assert-GuestLocalPath $VanillaClientDirectory "Vanilla client directory"
Assert-GuestLocalPath $LocalStateRoot "Local state root"
Assert-GuestLocalPath $ManagerManifest "Manager manifest"

$repositorySource = Join-Path $RepositoryShare "src"
$installer = Join-Path $RepositoryShare "scripts\install-wonderbane-vm-control-center.ps1"
$stopListener = Join-Path $RepositoryShare "scripts\stop-wonderbane-go-listener.ps1"
$vanillaExecutable = Join-Path $VanillaClientDirectory "sb.exe"
$vanillaTexturesCache = Join-Path $VanillaClientDirectory "cache\Textures.cache"
foreach ($required in @(
    @{ Path = $RepositoryShare; Kind = "Container"; Description = "repository share" },
    @{ Path = $DiagnosticsShare; Kind = "Container"; Description = "diagnostics share" },
    @{ Path = $repositorySource; Kind = "Container"; Description = "repository Python source" },
    @{ Path = $installer; Kind = "Leaf"; Description = "control-center installer" },
    @{ Path = $stopListener; Kind = "Leaf"; Description = "listener stop script" },
    @{ Path = $PythonPath; Kind = "Leaf"; Description = "Shadowbane Lab Python" },
    @{ Path = $vanillaExecutable; Kind = "Leaf"; Description = "vanilla sb.exe" },
    @{ Path = $vanillaTexturesCache; Kind = "Leaf"; Description = "vanilla Textures.cache" },
    @{ Path = $ExtensionArtifact; Kind = "Leaf"; Description = "reviewed extension artifact" }
)) {
    if (-not (Test-Path -LiteralPath $required.Path -PathType $required.Kind)) {
        throw "$($required.Description) was not found: $($required.Path)"
    }
}

$actualVanillaHash = (Get-FileHash -LiteralPath $vanillaExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualVanillaHash -ne $ExpectedVanillaExecutableSha256.ToLowerInvariant()) {
    throw (
        "Vanilla sb.exe hash is not the reviewed official build. Expected " +
        "$ExpectedVanillaExecutableSha256 but found $actualVanillaHash."
    )
}
$actualTexturesCacheHash = (
    Get-FileHash -LiteralPath $vanillaTexturesCache -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($actualTexturesCacheHash -ne $ExpectedVanillaTexturesCacheSha256.ToLowerInvariant()) {
    throw (
        "Vanilla Textures.cache hash is not the reviewed unmodified cache. Expected " +
        "$ExpectedVanillaTexturesCacheSha256 but found $actualTexturesCacheHash."
    )
}
foreach ($extensionResidue in @(
    (Join-Path $VanillaClientDirectory "wonderbane-extension.dll"),
    (Join-Path $VanillaClientDirectory ".wonderbane-extension")
)) {
    if (Test-Path -LiteralPath $extensionResidue) {
        throw "Vanilla source contains extension-package residue: $extensionResidue"
    }
}

$liveClients = @(
    Get-CimInstance Win32_Process -Filter "Name = 'sb.exe'"
)
if ($liveClients.Count -gt 0) {
    throw (
        "Close every WonderBane client before provisioning. Active sb.exe PID(s): " +
        (($liveClients.ProcessId | Sort-Object) -join ", ")
    )
}

New-Item -ItemType Directory -Path $LocalStateRoot -Force | Out-Null
Stop-ExactManager -ManifestPath $ManagerManifest -StateRoot $LocalStateRoot
& $stopListener -LogDirectory $DiagnosticsShare
if ($LASTEXITCODE -ne 0) {
    throw "WonderBane command listener did not stop cleanly."
}
$unexpectedListeners = @(
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -match "shadowbane_lab\.cli\s+client\s+listen-go" }
)
if ($unexpectedListeners.Count -gt 0) {
    throw (
        "Found an untracked WonderBane listener after the guarded stop: " +
        (($unexpectedListeners.ProcessId | Sort-Object) -join ", ")
    )
}

if (Test-Path -LiteralPath $ManagerManifest -PathType Leaf) {
    $installArguments = @{
        RepositoryShare = $RepositoryShare
        DiagnosticsShare = $DiagnosticsShare
        GameDirectory = $VanillaClientDirectory
        PythonPath = $PythonPath
        LocalStateRoot = $LocalStateRoot
    }
}
else {
    $installArguments = @{
        RepositoryShare = $RepositoryShare
        DiagnosticsShare = $DiagnosticsShare
        GameDirectory = $VanillaClientDirectory
        PythonPath = $PythonPath
        LocalStateRoot = $LocalStateRoot
        ClientCount = 1
    }
}
if ($NoStartupShortcut) {
    $installArguments["NoStartupShortcut"] = $true
}
& $installer @installArguments
if ($LASTEXITCODE -ne 0) {
    throw "WonderBane control-center installation failed with exit code $LASTEXITCODE"
}

$gitRepositoryPath = $RepositoryShare.Replace("\", "/").TrimEnd("/")
$gitSafeDirectory = "$gitRepositoryPath/"
if ($gitRepositoryPath.StartsWith("//")) {
    $gitSafeDirectory = "%(prefix)/$gitRepositoryPath/"
}
$revisionOutput = @(
    & git -c "safe.directory=$gitSafeDirectory" -C $RepositoryShare rev-parse HEAD
)
if ($LASTEXITCODE -ne 0 -or $revisionOutput.Count -ne 1) {
    throw "Could not resolve the repository revision from $RepositoryShare"
}
$repositoryRevision = $revisionOutput[0].Trim()
if (-not $repositoryRevision) {
    throw "Repository revision lookup returned an empty value."
}

$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
$deploymentId = "vanilla-$timestamp"
$baselineRoot = Join-Path $LocalStateRoot "client-baselines"
$runtimeRoot = Join-Path $LocalStateRoot "client-runtimes"
$inputRoot = Join-Path $LocalStateRoot "deployment-inputs"
$baselineDirectory = Join-Path $baselineRoot $deploymentId
$deploymentDirectory = Join-Path $runtimeRoot $deploymentId
$deploymentInputDirectory = Join-Path $inputRoot $deploymentId
$patchManifest = Join-Path $deploymentInputDirectory "$deploymentId.bootstrap-manifest.json"
foreach ($path in @($baselineRoot, $runtimeRoot, $deploymentInputDirectory)) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

$sourceBytes = (
    Get-ChildItem -LiteralPath $VanillaClientDirectory -File -Recurse |
        Measure-Object -Property Length -Sum
).Sum
$requiredBytes = [int64] ($sourceBytes * ($ClientCount + 1) + 1GB)
$stateDriveRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($LocalStateRoot))
$stateDriveName = $stateDriveRoot.TrimEnd("\").TrimEnd(":")
$stateDrive = Get-PSDrive -Name $stateDriveName -PSProvider FileSystem
if ($stateDrive.Free -lt $requiredBytes) {
    throw (
        "Insufficient guest-local disk space. The vanilla baseline plus $ClientCount runtimes " +
        "require at least $([Math]::Ceiling($requiredBytes / 1GB)) GiB free; drive " +
        "$stateDriveRoot has $([Math]::Round($stateDrive.Free / 1GB, 2)) GiB."
    )
}

$inheritedPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($inheritedPythonPath)) {
    $repositorySource
}
else {
    "$repositorySource$([IO.Path]::PathSeparator)$inheritedPythonPath"
}

& $PythonPath -m shadowbane_lab.client_extension `
    freeze-baseline `
    $VanillaClientDirectory `
    $baselineDirectory `
    --executable "sb.exe" `
    --repository-revision $repositoryRevision `
    --pretty
if ($LASTEXITCODE -ne 0) {
    throw "Local vanilla baseline capture failed with exit code $LASTEXITCODE"
}

& $PythonPath -m shadowbane_lab.client_extension `
    author-bootstrap `
    (Join-Path $baselineDirectory "sb.exe") `
    $ExtensionArtifact `
    $patchManifest `
    --extension-version $ExtensionVersion `
    --pretty
if ($LASTEXITCODE -ne 0) {
    throw "Bootstrap manifest authoring failed with exit code $LASTEXITCODE"
}

& $PythonPath -m shadowbane_lab.cli `
    manager provision-runtimes `
    $ManagerManifest `
    $baselineDirectory `
    $deploymentDirectory `
    $patchManifest `
    $ExtensionArtifact `
    --deployment-id $deploymentId `
    --slot-count $ClientCount `
    --resolution-width $ResolutionWidth `
    --resolution-height $ResolutionHeight `
    --apply `
    --json
if ($LASTEXITCODE -ne 0) {
    throw "Isolated runtime deployment failed with exit code $LASTEXITCODE"
}

& $PythonPath -m shadowbane_lab.cli manager preflight $ManagerManifest --json
if ($LASTEXITCODE -ne 0) {
    throw "The isolated manager manifest failed preflight."
}

Write-Output "WonderBane isolated runtime setup completed."
Write-Output "Vanilla baseline: $baselineDirectory"
Write-Output "Runtime deployment: $deploymentDirectory"
Write-Output "Manager slots: $ClientCount at ${ResolutionWidth}x${ResolutionHeight}"

if ($StartNow) {
    $localBootstrap = Join-Path $LocalStateRoot "start-wonderbane-control-center.ps1"
    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File $localBootstrap `
        -RepositoryShare $RepositoryShare `
        -DiagnosticsShare $DiagnosticsShare `
        -ManagerManifest $ManagerManifest
    if ($LASTEXITCODE -ne 0) {
        throw "WonderBane control center did not start successfully."
    }
}
