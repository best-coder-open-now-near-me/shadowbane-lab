[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexdiagtools",
    [string] $PythonExecutable = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [ValidatePattern("(?-i)^[a-z0-9][a-z0-9-]{0,31}$")]
    [string] $InstanceId = "primary",
    [string] $CurrentReceipt = "",
    [ValidateRange(1, 60)]
    [int] $StatusTimeoutSeconds = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($CurrentReceipt)) {
    $instanceReceipt = Join-Path $env:LOCALAPPDATA (
        "ShadowbaneLab\diagnostics-client\current-$InstanceId.json"
    )
    $legacyReceipt = Join-Path $env:LOCALAPPDATA (
        "ShadowbaneLab\diagnostics-client\current.json"
    )
    if (
        $InstanceId -eq "primary" -and
        -not (Test-Path -LiteralPath $instanceReceipt -PathType Leaf) -and
        (Test-Path -LiteralPath $legacyReceipt -PathType Leaf)
    ) {
        $CurrentReceipt = $legacyReceipt
    }
    else {
        $CurrentReceipt = $instanceReceipt
    }
}

foreach ($required in @(
    @{ Path = $RepositoryShare; Kind = "Container"; Description = "diagnostics repository share" },
    @{ Path = $PythonExecutable; Kind = "Leaf"; Description = "guest Python environment" },
    @{ Path = $CurrentReceipt; Kind = "Leaf"; Description = "diagnostics publication receipt" }
)) {
    if (-not (Test-Path -LiteralPath $required.Path -PathType $required.Kind)) {
        throw "$($required.Description) was not found: $($required.Path)"
    }
}
$receipt = Get-Content -LiteralPath $CurrentReceipt -Raw | ConvertFrom-Json
if (
    [int] $receipt.schema_version -ne 1 -or
    [string] $receipt.status -ne "published_and_verified" -or
    [string] $receipt.runtime_profile -ne "diagnostics-only" -or
    [bool] $receipt.baseline_payload_retained
) {
    throw "Diagnostics publication receipt does not describe a passive verified package"
}
$receiptHasInstanceId = $receipt.PSObject.Properties.Name -contains "instance_id"
if ($receiptHasInstanceId) {
    if ([string] $receipt.instance_id -ne $InstanceId) {
        throw "Diagnostics publication receipt belongs to instance '$($receipt.instance_id)', not '$InstanceId'"
    }
}
elseif ($InstanceId -ne "primary") {
    throw "Legacy diagnostics publication receipts may be used only for the primary instance"
}
$packageDirectory = [string] $receipt.package_directory
if (-not (Test-Path -LiteralPath $packageDirectory -PathType Container)) {
    throw "Published diagnostics package was not found: $packageDirectory"
}

$repositorySource = Join-Path $RepositoryShare "src"
$inheritedPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($inheritedPythonPath)) {
    $repositorySource
}
else {
    "$repositorySource$([IO.Path]::PathSeparator)$inheritedPythonPath"
}
try {
    $verificationArguments = @(
        "-m", "shadowbane_lab.client_extension", "verify-copy", $packageDirectory
    )
    $verificationOutput = @(& $PythonExecutable @verificationArguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Diagnostics client verification failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:PYTHONPATH = $inheritedPythonPath
}
$package = ($verificationOutput -join [Environment]::NewLine) | ConvertFrom-Json
foreach ($field in @(
    "extension_sha256",
    "result_executable_sha256",
    "working_tree_sha256"
)) {
    if ([string] $package.$field -ne [string] $receipt.$field) {
        throw "Diagnostics package no longer matches receipt field '$field'"
    }
}

$gameExecutable = Join-Path $packageDirectory ([string] $package.executable_relative_path)
$extensionArtifact = Join-Path $packageDirectory ([string] $package.extension_relative_path)
$actualExecutableSha256 = (
    Get-FileHash -LiteralPath $gameExecutable -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($actualExecutableSha256 -ne [string] $receipt.result_executable_sha256) {
    throw "Diagnostics sb.exe no longer matches its publication identity"
}
$actualExtensionSha256 = (
    Get-FileHash -LiteralPath $extensionArtifact -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($actualExtensionSha256 -ne [string] $receipt.extension_sha256) {
    throw "Diagnostics extension no longer matches its publication identity"
}

$resolvedGameExecutable = [IO.Path]::GetFullPath(
    (Resolve-Path -LiteralPath $gameExecutable).Path
)
foreach ($runningClient in @(Get-Process -Name "sb" -ErrorAction SilentlyContinue)) {
    try {
        $runningPath = $runningClient.Path
    }
    catch {
        throw "Could not inspect existing sb.exe PID $($runningClient.Id); refusing an ambiguous concurrent launch"
    }
    if (-not $runningPath) {
        throw "Existing sb.exe PID $($runningClient.Id) has no inspectable executable path; refusing an ambiguous concurrent launch"
    }
    if ([string]::Equals(
        [IO.Path]::GetFullPath($runningPath),
        $resolvedGameExecutable,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Diagnostics instance '$InstanceId' is already running from this verified package (PID $($runningClient.Id))"
    }
}

$startArguments = @{
    FilePath = $gameExecutable
    WorkingDirectory = $packageDirectory
    PassThru = $true
}
$game = Start-Process @startArguments
$creationFiletimeUtc = $game.StartTime.ToUniversalTime().ToFileTimeUtc()
$statusDirectory = Join-Path $env:LOCALAPPDATA "ShadowbaneLab\client-extension"
$statusPath = Join-Path $statusDirectory "graphics-status-$($game.Id)-$creationFiletimeUtc.json"
$deadline = [DateTime]::UtcNow.AddSeconds($StatusTimeoutSeconds)
$status = $null
while ([DateTime]::UtcNow -lt $deadline) {
    if ($game.HasExited) {
        throw "Diagnostics client exited before publishing renderer status"
    }
    if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
        try {
            $candidate = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
            if (
                [string] $candidate.runtime_profile -eq "diagnostics-only" -and
                [int] $candidate.process_identity.process_id -eq $game.Id -and
                [int64] $candidate.process_identity.process_creation_filetime_utc -eq
                    $creationFiletimeUtc
            ) {
                $status = $candidate
                break
            }
        }
        catch {
            # Retry only while the bounded status startup window remains open.
        }
    }
    Start-Sleep -Milliseconds 100
}
if ($null -eq $status) {
    throw "Diagnostics client did not publish an identity-bound passive renderer status in time"
}

Write-Output "Launched WonderBane diagnostics-only client (PID $($game.Id))"
Write-Output "Instance: $InstanceId"
Write-Output "Runtime profile: $($status.runtime_profile)"
Write-Output "Package: $packageDirectory"
Write-Output "Renderer status: $statusPath"
