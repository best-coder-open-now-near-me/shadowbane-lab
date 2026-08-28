[CmdletBinding()]
param(
    [string] $ClientExecutable =
        "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\sb.exe",
    [string] $OutputDirectory = "\\VBOXSVR\codexdiag\incoming-captures",
    [ValidateRange(32, 2048)]
    [int] $MaxFileSizeMB = 256,
    [string] $CaptureRoot = "$env:LOCALAPPDATA\shadowbane-lab\incoming-captures"
)

$ErrorActionPreference = "Stop"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-PacketMonitor {
    param([Parameter(Mandatory)][string[]] $Arguments)

    $output = @(& "$env:SystemRoot\System32\pktmon.exe" @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        $detail = ($output | Out-String).Trim()
        throw "pktmon $($Arguments -join ' ') failed: $detail"
    }
    return $output
}

if (-not (Test-Administrator)) {
    $elevatedArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", ('"{0}"' -f $PSCommandPath),
        "-ClientExecutable", ('"{0}"' -f $ClientExecutable),
        "-OutputDirectory", ('"{0}"' -f $OutputDirectory),
        "-MaxFileSizeMB", "$MaxFileSizeMB",
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

$startErrorPath = Join-Path $OutputDirectory "wonderbane-incoming-start-error.json"
$sharedActivePath = Join-Path $OutputDirectory "wonderbane-incoming-active.json"
$started = $false
trap {
    $failure = [ordered]@{
        schema_version = 1
        status = "failed"
        failed_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        error = $_.Exception.Message
        position = $_.InvocationInfo.PositionMessage
    }
    try {
        if (-not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
            New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
        }
        $failure |
            ConvertTo-Json -Depth 4 |
            Set-Content -LiteralPath $startErrorPath -Encoding utf8
        if ($started) {
            Remove-Item -LiteralPath $sharedActivePath -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
        Write-Warning "Could not write the shared capture error report: $($_.Exception.Message)"
    }
    [Console]::Error.WriteLine($failure.error)
    exit 1
}

$packetMonitor = "$env:SystemRoot\System32\pktmon.exe"
if (-not (Test-Path -LiteralPath $packetMonitor -PathType Leaf)) {
    throw "Windows Packet Monitor was not found: $packetMonitor"
}
if (-not (Test-Path -LiteralPath $ClientExecutable -PathType Leaf)) {
    throw "WonderBane executable was not found: $ClientExecutable"
}

$resolvedClientExecutable = (Resolve-Path -LiteralPath $ClientExecutable).Path
$processName = [IO.Path]::GetFileNameWithoutExtension($resolvedClientExecutable)
$clientProcesses = @(
    Get-Process -Name $processName -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Path -and
            [string]::Equals(
                (Resolve-Path -LiteralPath $_.Path).Path,
                $resolvedClientExecutable,
                [StringComparison]::OrdinalIgnoreCase
            )
        }
)
if ($clientProcesses.Count -ne 1) {
    throw "Expected exactly one running $resolvedClientExecutable process; found $($clientProcesses.Count)."
}
$clientProcess = $clientProcesses[0]

if (-not (Test-Path -LiteralPath $CaptureRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $CaptureRoot -Force | Out-Null
}
$activeStatePath = Join-Path $CaptureRoot "wonderbane-incoming.active.json"
if (Test-Path -LiteralPath $activeStatePath -PathType Leaf) {
    throw "An incoming capture is already active or awaiting finalization. Run the stop script first: $activeStatePath"
}

$statusOutput = @(& $packetMonitor status 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Could not query Packet Monitor: $(($statusOutput | Out-String).Trim())"
}
$statusText = ($statusOutput | Out-String).Trim()
if ($statusText -notmatch "(?i)not running") {
    throw "Packet Monitor is already in use. Refusing to replace another capture. Status: $statusText"
}

$tcpConnections = @(
    Get-NetTCPConnection `
        -OwningProcess $clientProcess.Id `
        -State Established `
        -ErrorAction SilentlyContinue |
        Sort-Object LocalAddress, LocalPort, RemoteAddress, RemotePort
)
$udpEndpoints = @(
    Get-NetUDPEndpoint `
        -OwningProcess $clientProcess.Id `
        -ErrorAction SilentlyContinue |
        Sort-Object LocalAddress, LocalPort
)
if ($tcpConnections.Count + $udpEndpoints.Count -eq 0) {
    throw "The running WonderBane client has no TCP or UDP endpoints to capture. Log in, then retry."
}
if ($tcpConnections.Count + $udpEndpoints.Count -gt 32) {
    throw "WonderBane exposes more than Packet Monitor's 32-filter limit. Refine the endpoint selection before capturing."
}

$startedAt = (Get-Date).ToUniversalTime()
$captureId = "wonderbane-incoming-$($startedAt.ToString('yyyyMMddTHHmmssfffZ'))"
$etlPath = Join-Path $CaptureRoot "$captureId.etl"
$pcapPath = Join-Path $CaptureRoot "$captureId.pcapng"
$manifestPath = Join-Path $CaptureRoot "$captureId.json"
$clientHash = (Get-FileHash -LiteralPath $resolvedClientExecutable -Algorithm SHA256).Hash.ToLowerInvariant()

$endpoints = [Collections.Generic.List[object]]::new()
foreach ($connection in $tcpConnections) {
    $endpoints.Add([pscustomobject]@{
        protocol = "tcp"
        local_address = $connection.LocalAddress
        local_port = $connection.LocalPort
        remote_address = $connection.RemoteAddress
        remote_port = $connection.RemotePort
    })
}
foreach ($endpoint in $udpEndpoints) {
    $endpoints.Add([pscustomobject]@{
        protocol = "udp"
        local_address = $endpoint.LocalAddress
        local_port = $endpoint.LocalPort
        remote_address = $null
        remote_port = $null
    })
}

try {
    Invoke-PacketMonitor -Arguments @("filter", "remove") | Out-Null
    $filterNumber = 0
    foreach ($connection in $tcpConnections) {
        $filterNumber += 1
        $remoteAddress = $connection.RemoteAddress -replace "%.*$", ""
        $filterArguments = @(
            "filter", "add", "sb-tcp-$filterNumber",
            "-t", "TCP",
            "-i", "$remoteAddress",
            "-p", "$($connection.LocalPort)", "$($connection.RemotePort)"
        )
        Invoke-PacketMonitor -Arguments $filterArguments | Out-Null
    }
    foreach ($endpoint in $udpEndpoints) {
        $filterNumber += 1
        Invoke-PacketMonitor -Arguments @(
            "filter", "add", "sb-udp-$filterNumber",
            "-t", "UDP",
            "-p", "$($endpoint.LocalPort)"
        ) | Out-Null
    }

    Invoke-PacketMonitor -Arguments @(
        "start",
        "--capture",
        "--comp", "nics",
        "--pkt-size", "0",
        "--file-name", $etlPath,
        "--file-size", "$MaxFileSizeMB",
        "--log-mode", "circular"
    ) | Out-Null
    $started = $true

    $manifest = [ordered]@{
        schema_version = 1
        capture_id = $captureId
        status = "recording"
        started_at_utc = $startedAt.ToString("o")
        stopped_at_utc = $null
        client = [ordered]@{
            process_id = $clientProcess.Id
            executable_path = $resolvedClientExecutable
            executable_sha256 = $clientHash
        }
        endpoints = @($endpoints)
        packet_monitor = [ordered]@{
            component_scope = "nics"
            packet_size = 0
            log_mode = "circular"
            maximum_file_size_mb = $MaxFileSizeMB
        }
        local_etl_path = $etlPath
        local_pcapng_path = $pcapPath
        output_directory = $OutputDirectory
        warning = "The capture is scoped to current sb.exe endpoints but may contain account, session, or chat data. Keep it private."
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    [ordered]@{
        schema_version = 1
        capture_id = $captureId
        manifest_path = $manifestPath
        etl_path = $etlPath
        pcapng_path = $pcapPath
        output_directory = $OutputDirectory
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $activeStatePath -Encoding utf8
    if (-not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    }
    [ordered]@{
        schema_version = 1
        capture_id = $captureId
        status = "recording"
        started_at_utc = $startedAt.ToString("o")
        client_sha256 = $clientHash
    } |
        ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath $sharedActivePath -Encoding utf8
    Remove-Item -LiteralPath $startErrorPath -Force -ErrorAction SilentlyContinue
}
catch {
    if ($started) {
        & $packetMonitor stop 2>&1 | Out-Null
    }
    & $packetMonitor filter remove 2>&1 | Out-Null
    throw
}

Write-Output "WonderBane incoming capture started."
Write-Output "Capture ID: $captureId"
Write-Output "Client SHA-256: $clientHash"
Write-Output "Endpoints: $($endpoints.Count)"
Write-Output "Local ETL: $etlPath"
Write-Output "Leave and re-enter character creation once, then run stop-wonderbane-incoming-capture.ps1."
Write-Warning "Raw packets may contain account, session, or chat data. Do not publish the capture."
