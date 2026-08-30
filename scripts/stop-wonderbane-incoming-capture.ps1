[CmdletBinding()]
param(
    [string] $CaptureRoot = "$env:LOCALAPPDATA\shadowbane-lab\incoming-captures"
)

$ErrorActionPreference = "Stop"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-CapturePath {
    param(
        [Parameter(Mandatory)][string] $Path,
        [Parameter(Mandatory)][string] $Root
    )

    $absolutePath = [IO.Path]::GetFullPath($Path)
    $absoluteRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    if (-not $absolutePath.StartsWith($absoluteRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Capture state points outside the capture root: $absolutePath"
    }
    return $absolutePath
}

if (-not (Test-Administrator)) {
    $elevatedArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"{0}"' -f $PSCommandPath),
        "-CaptureRoot", ('"{0}"' -f $CaptureRoot)
    )
    $elevated = Start-Process `
        -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
        -ArgumentList $elevatedArguments `
        -Verb RunAs `
        -Wait `
        -PassThru
    exit $elevated.ExitCode
}

$packetMonitor = "$env:SystemRoot\System32\pktmon.exe"
if (-not (Test-Path -LiteralPath $packetMonitor -PathType Leaf)) {
    throw "Windows Packet Monitor was not found: $packetMonitor"
}
$activeStatePath = Join-Path $CaptureRoot "wonderbane-incoming.active.json"
if (-not (Test-Path -LiteralPath $activeStatePath -PathType Leaf)) {
    Write-Output "There is no active WonderBane incoming capture."
    exit 0
}

$state = Get-Content -LiteralPath $activeStatePath -Raw | ConvertFrom-Json
if ($state.schema_version -ne 1 -or -not $state.capture_id) {
    throw "The active capture state is invalid: $activeStatePath"
}
$manifestPath = Assert-CapturePath -Path $state.manifest_path -Root $CaptureRoot
$etlPath = Assert-CapturePath -Path $state.etl_path -Root $CaptureRoot
$pcapPath = Assert-CapturePath -Path $state.pcapng_path -Root $CaptureRoot
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "The capture manifest is missing: $manifestPath"
}

$statusOutput = @(& $packetMonitor status 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Could not query Packet Monitor: $(($statusOutput | Out-String).Trim())"
}
$statusText = ($statusOutput | Out-String).Trim()
if ($statusText -notmatch "(?i)not running") {
    if ($statusText -notmatch [regex]::Escape([string] $state.capture_id)) {
        throw "Packet Monitor is running a different capture. Refusing to stop it. Status: $statusText"
    }
    $stopOutput = @(& $packetMonitor stop 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not stop Packet Monitor: $(($stopOutput | Out-String).Trim())"
    }
}
& $packetMonitor filter remove 2>&1 | Out-Null

if (-not (Test-Path -LiteralPath $etlPath -PathType Leaf)) {
    throw "Packet Monitor stopped, but the ETL capture is missing: $etlPath"
}
if (-not (Test-Path -LiteralPath $pcapPath -PathType Leaf)) {
    $conversionOutput = @(& $packetMonitor etl2pcap $etlPath --out $pcapPath 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not convert the ETL capture to pcapng: $(($conversionOutput | Out-String).Trim())"
    }
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$manifest.status = "completed"
$manifest.stopped_at_utc = (Get-Date).ToUniversalTime().ToString("o")
$manifest | Add-Member `
    -NotePropertyName pcapng_size_bytes `
    -NotePropertyValue (Get-Item -LiteralPath $pcapPath).Length `
    -Force
$manifest | Add-Member `
    -NotePropertyName pcapng_sha256 `
    -NotePropertyValue (Get-FileHash -LiteralPath $pcapPath -Algorithm SHA256).Hash.ToLowerInvariant() `
    -Force
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8

$outputDirectory = [string] $state.output_directory
if (-not (Test-Path -LiteralPath $outputDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}
$outputPcapPath = Join-Path $outputDirectory ([IO.Path]::GetFileName($pcapPath))
$outputManifestPath = Join-Path $outputDirectory ([IO.Path]::GetFileName($manifestPath))
$sharedActivePath = Join-Path $outputDirectory "wonderbane-incoming-active.json"
Copy-Item -LiteralPath $pcapPath -Destination $outputPcapPath
$manifest | Add-Member -NotePropertyName output_pcapng_path -NotePropertyValue $outputPcapPath -Force
$manifest | Add-Member -NotePropertyName output_manifest_path -NotePropertyValue $outputManifestPath -Force
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Copy-Item -LiteralPath $manifestPath -Destination $outputManifestPath

Remove-Item -LiteralPath $activeStatePath
Remove-Item -LiteralPath $sharedActivePath -Force -ErrorAction SilentlyContinue

Write-Output "WonderBane incoming capture completed."
Write-Output "Capture ID: $($state.capture_id)"
Write-Output "PCAPNG: $outputPcapPath"
Write-Output "Manifest: $outputManifestPath"
Write-Output "SHA-256: $($manifest.pcapng_sha256)"
Write-Warning "Raw packets may contain account, session, or chat data. Do not publish the capture."
