[CmdletBinding()]
param(
    [string] $GameDirectory = "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane",
    [string] $QuarantineRoot = "$env:LOCALAPPDATA\ShadowbaneLab\retired-extension"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$gameItem = Get-Item -LiteralPath $GameDirectory -ErrorAction Stop
if (-not $gameItem.PSIsContainer) {
    throw "GameDirectory is not a directory: $GameDirectory"
}
$gameRoot = [IO.Path]::GetFullPath($gameItem.FullName).TrimEnd('\')
$volumeRoot = [IO.Path]::GetPathRoot($gameRoot).TrimEnd('\')
if (-not $gameRoot -or $gameRoot -eq $volumeRoot) {
    throw "GameDirectory must not be a volume root."
}

$executablePath = Join-Path $gameRoot "sb.exe"
$packagePath = Join-Path $gameRoot ".wonderbane-extension"
$extensionPath = Join-Path $gameRoot "wonderbane-extension.dll"
if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
    throw "WonderBane executable was not found: $executablePath"
}
if (-not (Test-Path -LiteralPath $packagePath -PathType Container)) {
    throw "Extension package marker directory was not found: $packagePath"
}
if (-not (Test-Path -LiteralPath $extensionPath -PathType Leaf)) {
    throw "Extension DLL was not found: $extensionPath"
}

$runningClients = @(
    Get-CimInstance Win32_Process -Filter "Name = 'sb.exe'" -ErrorAction Stop |
        Where-Object {
            $_.ExecutablePath -and
            [IO.Path]::GetFullPath((Split-Path -Parent $_.ExecutablePath)).TrimEnd('\') -eq $gameRoot
        }
)
if ($runningClients.Count -gt 0) {
    throw "The exact WonderBane client is still running; close it before retiring its extension."
}

$quarantineParent = [IO.Path]::GetFullPath($QuarantineRoot).TrimEnd('\')
if (
    $quarantineParent -eq $gameRoot -or
    $quarantineParent.StartsWith("$gameRoot\", [StringComparison]::OrdinalIgnoreCase)
) {
    throw "QuarantineRoot must be outside GameDirectory."
}
New-Item -ItemType Directory -Path $quarantineParent -Force | Out-Null

$executableSha256 = (Get-FileHash -LiteralPath $executablePath -Algorithm SHA256).Hash.ToLowerInvariant()
$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
$quarantinePath = Join-Path $quarantineParent "extension-$timestamp-$($executableSha256.Substring(0, 8))"
if (Test-Path -LiteralPath $quarantinePath) {
    throw "Quarantine destination already exists: $quarantinePath"
}
New-Item -ItemType Directory -Path $quarantinePath | Out-Null
$resolvedQuarantine = [IO.Path]::GetFullPath($quarantinePath).TrimEnd('\')
if (-not $resolvedQuarantine.StartsWith("$quarantineParent\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Resolved quarantine destination left QuarantineRoot."
}

$packageDestination = Join-Path $resolvedQuarantine ".wonderbane-extension"
$extensionDestination = Join-Path $resolvedQuarantine "wonderbane-extension.dll"
$packageMoved = $false
$extensionMoved = $false
try {
    Move-Item -LiteralPath $packagePath -Destination $packageDestination
    $packageMoved = $true
    Move-Item -LiteralPath $extensionPath -Destination $extensionDestination
    $extensionMoved = $true
}
catch {
    if ($extensionMoved -and (Test-Path -LiteralPath $extensionDestination)) {
        Move-Item -LiteralPath $extensionDestination -Destination $extensionPath
    }
    if ($packageMoved -and (Test-Path -LiteralPath $packageDestination)) {
        Move-Item -LiteralPath $packageDestination -Destination $packagePath
    }
    if ((Get-ChildItem -LiteralPath $resolvedQuarantine -Force).Count -eq 0) {
        Remove-Item -LiteralPath $resolvedQuarantine -Force
    }
    throw
}

$receipt = [ordered]@{
    schema_version = 1
    retired_at_utc = [DateTime]::UtcNow.ToString("o")
    game_directory = $gameRoot
    executable_sha256 = $executableSha256
    quarantine_directory = $resolvedQuarantine
    moved_paths = @(
        [ordered]@{
            source = $packagePath
            destination = $packageDestination
        },
        [ordered]@{
            source = $extensionPath
            destination = $extensionDestination
        }
    )
}
$receiptPath = Join-Path $resolvedQuarantine "retirement.json"
$receiptJson = $receipt | ConvertTo-Json -Depth 5
$utf8WithoutBom = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($receiptPath, "$receiptJson`r`n", $utf8WithoutBom)

Write-Output "Retired stale WonderBane extension artifacts to: $resolvedQuarantine"
Write-Output "Receipt: $receiptPath"
