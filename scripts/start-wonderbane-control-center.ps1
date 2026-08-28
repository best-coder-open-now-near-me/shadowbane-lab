[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexrepo",
    [string] $DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string] $PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $ManagerManifest = "$env:LOCALAPPDATA\ShadowbaneLab\client-manager.json",
    [ValidateRange(1, 300)]
    [int] $ShareWaitSeconds = 90,
    [switch] $SkipListener,
    [switch] $NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$stateRoot = Split-Path -Parent $ManagerManifest
$logRoot = Join-Path $stateRoot "logs"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$bootstrapLog = Join-Path $logRoot "control-center-bootstrap.log"

function Write-BootstrapLog {
    param([string] $Message)
    $record = "{0:o} {1}" -f (Get-Date), $Message
    Add-Content -LiteralPath $bootstrapLog -Value $record -Encoding utf8
    Write-Output $Message
}

function Wait-RequiredPath {
    param(
        [string] $Path,
        [string] $Description,
        [datetime] $Deadline
    )
    while (-not (Test-Path -LiteralPath $Path)) {
        if ((Get-Date) -ge $Deadline) {
            throw "$Description did not become available before the startup deadline: $Path"
        }
        Start-Sleep -Milliseconds 500
    }
}

try {
    $deadline = (Get-Date).AddSeconds($ShareWaitSeconds)
    Wait-RequiredPath $RepositoryShare "Repository share" $deadline
    Wait-RequiredPath $DiagnosticsShare "Diagnostics share" $deadline
    Wait-RequiredPath $PythonPath "Shadowbane Lab Python" $deadline
    Wait-RequiredPath $ManagerManifest "Manager manifest" $deadline

    $managerSource = Join-Path $RepositoryShare "src"
    $listenerScript = Join-Path $RepositoryShare "scripts\start-wonderbane-go-listener.ps1"
    Wait-RequiredPath $managerSource "Manager source tree" $deadline
    if (-not $SkipListener) {
        Wait-RequiredPath $listenerScript "Listener launcher" $deadline
    }
    $env:PYTHONPATH = $managerSource

    if (-not $SkipListener) {
        try {
            $listenerStatus = & powershell.exe `
                -NoProfile `
                -ExecutionPolicy Bypass `
                -File $listenerScript 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Listener bootstrap failed: $($listenerStatus -join ' ')"
            }
            Write-BootstrapLog ($listenerStatus -join " ")
        }
        catch {
            Write-BootstrapLog "WARNING: $($_.Exception.Message)"
        }
    }

    $existingManagers = @(
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
            Where-Object {
                $_.CommandLine -match (
                    "shadowbane_lab\.cli\s+manager\s+app\s+" +
                    [regex]::Escape($ManagerManifest)
                )
            }
    )
    if ($existingManagers.Count -gt 0) {
        Write-BootstrapLog (
            "WonderBane control center is already running (PID(s) " +
            (($existingManagers.ProcessId | Sort-Object) -join ", ") + ")."
        )
        exit 0
    }

    $preflight = @(
        & $PythonPath `
            -m shadowbane_lab.cli `
            manager preflight `
            $ManagerManifest `
            --json 2>&1
    )
    $preflightExitCode = $LASTEXITCODE
    $preflightPath = Join-Path $DiagnosticsShare "manager-preflight-latest.json"
    Set-Content -LiteralPath $preflightPath -Value ($preflight -join "`n") -Encoding utf8
    if ($preflightExitCode -ne 0) {
        throw "Manager preflight failed: $($preflight -join ' ')"
    }

    $managerArguments = @(
        "-u",
        "-m",
        "shadowbane_lab.cli",
        "manager",
        "app",
        $ManagerManifest,
        "--live"
    )
    if ($NoBrowser) {
        $managerArguments += "--no-browser"
    }
    $managerStdout = Join-Path $logRoot "manager.stdout.log"
    $managerStderr = Join-Path $logRoot "manager.stderr.log"
    $managerProcess = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList $managerArguments `
        -WorkingDirectory $RepositoryShare `
        -WindowStyle Hidden `
        -RedirectStandardOutput $managerStdout `
        -RedirectStandardError $managerStderr `
        -PassThru

    Start-Sleep -Milliseconds 1000
    $managerProcess.Refresh()
    if ($managerProcess.HasExited) {
        $detail = if (Test-Path -LiteralPath $managerStderr) {
            (Get-Content -LiteralPath $managerStderr -Raw).Trim()
        }
        else {
            "manager exited without an error log"
        }
        throw "WonderBane control center failed to start: $detail"
    }
    Set-Content `
        -LiteralPath (Join-Path $stateRoot "manager.pid") `
        -Value $managerProcess.Id `
        -Encoding ascii
    Write-BootstrapLog "WonderBane control center started (PID $($managerProcess.Id))."
}
catch {
    Write-BootstrapLog "ERROR: $($_.Exception.Message)"
    throw
}
