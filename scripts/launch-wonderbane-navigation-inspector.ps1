[CmdletBinding()]
param(
    [string]$RuntimeDirectory = (Split-Path -Parent $PSScriptRoot),
    [ValidateRange(30, 3600)]
    [int]$ClientStartupTimeoutSeconds = 900,
    [ValidateRange(5, 120)]
    [int]$InspectorStartupTimeoutSeconds = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$runtime = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$client = Join-Path $runtime 'client'
$executable = Join-Path $client 'sb.exe'
$patcher = Join-Path $client 'WonderBanePatcher.exe'
$python = Join-Path $runtime 'python\Scripts\python.exe'
$pythonw = Join-Path $runtime 'python\Scripts\pythonw.exe'
$extension = Join-Path $client 'wonderbane-extension.dll'
foreach ($path in @($executable, $patcher, $python, $pythonw, $extension)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Prepared inspector runtime is incomplete: $path"
    }
}

function Get-PreparedClient {
    @(
        Get-CimInstance Win32_Process -Filter "Name='sb.exe'" |
            Where-Object {
                $_.ExecutablePath -and
                $_.ExecutablePath.Equals(
                    $script:executable,
                    [StringComparison]::OrdinalIgnoreCase
                )
            }
    )
}

function Wait-PreparedClient {
    param([datetime]$Deadline)

    while ((Get-Date) -lt $Deadline) {
        $matches = @(Get-PreparedClient)
        if ($matches.Count -gt 1) {
            throw (
                'The prepared patcher started more than one client (PIDs ' +
                (($matches.ProcessId | Sort-Object) -join ', ') + ').'
            )
        }
        if ($matches.Count -eq 1) {
            return $matches[0]
        }
        Start-Sleep -Milliseconds 250
    }
    throw (
        "The prepared client did not start within $ClientStartupTimeoutSeconds seconds. " +
        'Use Launch in the WonderBane Patcher, then run this shortcut again.'
    )
}

function Get-InspectorProcesses {
    param([int]$ClientProcessId)

    $pidPattern = "(?:^|\s)--pid\s+$ClientProcessId(?:\s|$)"
    @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -in @('python.exe', 'pythonw.exe') -and
                $_.CommandLine -match 'shadowbane_lab\.navigation_inspector' -and
                $_.CommandLine -match $pidPattern
            }
    )
}

function Remove-StaleInspectorProcesses {
    $inspectors = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -in @('python.exe', 'pythonw.exe') -and
                $_.CommandLine -match 'shadowbane_lab\.navigation_inspector'
            }
    )
    foreach ($inspector in $inspectors) {
        $match = [regex]::Match($inspector.CommandLine, '(?:^|\s)--pid\s+(\d+)(?:\s|$)')
        if (-not $match.Success) {
            continue
        }
        $targetProcessId = [int]$match.Groups[1].Value
        $target = Get-CimInstance `
            Win32_Process `
            -Filter "ProcessId=$targetProcessId" `
            -ErrorAction SilentlyContinue
        if ($null -eq $target -or $target.Name -ne 'sb.exe') {
            Stop-Process -Id $inspector.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Wait-InspectorWindow {
    param(
        [int]$ClientProcessId,
        [datetime]$Deadline
    )

    while ((Get-Date) -lt $Deadline) {
        foreach ($candidate in @(Get-InspectorProcesses -ClientProcessId $ClientProcessId)) {
            $process = Get-Process -Id $candidate.ProcessId -ErrorAction SilentlyContinue
            if (
                $null -ne $process -and
                $process.MainWindowTitle -eq 'WonderBane Navigation Inspector'
            ) {
                return @(Get-InspectorProcesses -ClientProcessId $ClientProcessId)
            }
        }
        Start-Sleep -Milliseconds 250
    }
    $detail = if (Test-Path -LiteralPath $script:panelErrorLog -PathType Leaf) {
        (Get-Content -LiteralPath $script:panelErrorLog -Raw).Trim()
    }
    else {
        'the panel did not publish an error log'
    }
    throw "The navigation inspector panel did not open: $detail"
}

function Wait-InspectorTarget {
    param([int]$ClientProcessId)

    $probe = @'
import sys
import time
from pathlib import Path
from shadowbane_lab.graphics_lab.control import discover_graphics_targets

process_id = int(sys.argv[1])
executable = Path(sys.argv[2]).resolve()
deadline = time.monotonic() + float(sys.argv[3])
while time.monotonic() < deadline:
    matches = [
        target
        for target in discover_graphics_targets()
        if target.process_id == process_id
        and target.executable_path.resolve() == executable
    ]
    if len(matches) == 1:
        raise SystemExit(0)
    if len(matches) > 1:
        raise SystemExit(2)
    time.sleep(0.25)
raise SystemExit(1)
'@
    & $script:python `
        -c $probe `
        $ClientProcessId `
        $script:executable `
        $InspectorStartupTimeoutSeconds
    if ($LASTEXITCODE -ne 0) {
        throw (
            'The prepared client did not expose one exact inspector channel within ' +
            "$InspectorStartupTimeoutSeconds seconds (probe exit $LASTEXITCODE)."
        )
    }
}

function Invoke-RuntimeVerification {
    & $script:python `
        -m shadowbane_lab.client_extension `
        verify-runtime-copy `
        $script:client `
        --pretty
    if ($LASTEXITCODE -ne 0) {
        throw 'Prepared client integrity verification failed.'
    }
}

$settings = @{
    PYTHONPATH = $null
    LIBGL_ALWAYS_SOFTWARE = 'true'
    GALLIUM_DRIVER = 'llvmpipe'
    LP_NUM_THREADS = '3'
    MESA_EXTENSION_MAX_YEAR = '2001'
    MESA_GL_VERSION_OVERRIDE = $null
    MESA_GLSL_VERSION_OVERRIDE = $null
}
$previous = @{}
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $mutexBytes = $sha256.ComputeHash(
        [Text.Encoding]::UTF8.GetBytes($runtime.ToLowerInvariant())
    )
}
finally {
    $sha256.Dispose()
}
$mutexHash = -join @($mutexBytes | ForEach-Object { $_.ToString('x2') })
$launcherMutex = New-Object Threading.Mutex(
    $false,
    "Global\WonderBaneInspectorLauncher-$mutexHash"
)
$ownsMutex = $false
$patcherProcess = $null
$gameStatus = 'existing'
$panelStatus = 'existing'
try {
    $ownsMutex = $launcherMutex.WaitOne(0)
    if (-not $ownsMutex) {
        throw 'This prepared runtime already has a launcher waiting for the patcher.'
    }

    $games = @(Get-PreparedClient)
    if ($games.Count -gt 1) {
        throw "More than one prepared client is running (PIDs $($games.ProcessId -join ', '))."
    }
    Invoke-RuntimeVerification
    if ($games.Count -eq 0) {
        $gameStatus = 'started_by_patcher'
        foreach ($name in $settings.Keys) {
            $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
            [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
        }
        try {
            $patcherProcess = Start-Process `
                -FilePath $patcher `
                -WorkingDirectory $client `
                -WindowStyle Normal `
                -PassThru
        }
        finally {
            foreach ($name in $previous.Keys) {
                [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
            }
        }
        Write-Host 'WonderBane Patcher opened. Use Launch there to start the prepared client.'
        $game = Wait-PreparedClient -Deadline (
            (Get-Date).AddSeconds($ClientStartupTimeoutSeconds)
        )
        Invoke-RuntimeVerification
    }
    else {
        $game = $games[0]
    }

    $env:PYTHONPATH = $null
    Wait-InspectorTarget -ClientProcessId $game.ProcessId
    Remove-StaleInspectorProcesses
    $panels = @(Get-InspectorProcesses -ClientProcessId $game.ProcessId)
    $logRoot = Join-Path $env:LOCALAPPDATA 'ShadowbaneLab\navigation-inspector'
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $panelOutputLog = Join-Path $logRoot "panel-$($game.ProcessId).stdout.log"
    $panelErrorLog = Join-Path $logRoot "panel-$($game.ProcessId).stderr.log"
    if ($panels.Count -eq 0) {
        $panelStatus = 'started'
        $null = Start-Process `
            -FilePath $pythonw `
            -ArgumentList @(
                '-m',
                'shadowbane_lab.navigation_inspector',
                '--pid',
                [string]$game.ProcessId
            ) `
            -WorkingDirectory $runtime `
            -WindowStyle Normal `
            -RedirectStandardOutput $panelOutputLog `
            -RedirectStandardError $panelErrorLog `
            -PassThru
    }
    $panels = @(
        Wait-InspectorWindow `
            -ClientProcessId $game.ProcessId `
            -Deadline ((Get-Date).AddSeconds($InspectorStartupTimeoutSeconds))
    )

    [pscustomobject]@{
        patcher_process_id = if ($null -eq $patcherProcess) {
            $null
        }
        else {
            $patcherProcess.Id
        }
        process_id = $game.ProcessId
        process_creation_filetime = (
            Get-Process -Id $game.ProcessId
        ).StartTime.ToUniversalTime().ToFileTimeUtc()
        executable = $executable
        game_status = $gameStatus
        panel_status = $panelStatus
        panel_process_ids = @($panels.ProcessId | Sort-Object -Unique)
        status = 'ready'
    }
}
finally {
    if ($ownsMutex) {
        $launcherMutex.ReleaseMutex()
    }
    $launcherMutex.Dispose()
}
