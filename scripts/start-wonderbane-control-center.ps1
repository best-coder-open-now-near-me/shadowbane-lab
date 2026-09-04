[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexrepo",
    [string] $DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string] $PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $ManagerManifest = "$env:LOCALAPPDATA\ShadowbaneLab\client-manager.json",
    [ValidateRange(1024, 65535)]
    [int] $ManagerPort = 52739,
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
$dashboardTokenPath = Join-Path $stateRoot "dashboard.token"

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

function Open-CurrentDashboard {
    if ($NoBrowser) {
        return
    }
    if (-not (Test-Path -LiteralPath $dashboardTokenPath -PathType Leaf)) {
        Write-BootstrapLog "Dashboard token is not available yet; no browser was opened."
        return
    }
    $token = (Get-Content -LiteralPath $dashboardTokenPath -Raw).Trim()
    if ($token -notmatch '^[A-Za-z0-9_-]{43,}$') {
        throw "Dashboard token file is malformed: $dashboardTokenPath"
    }
    $dashboardUrl = "http://127.0.0.1:$ManagerPort/#token=$token"
    Start-Process -FilePath $dashboardUrl
    Write-BootstrapLog "Opened the current WonderBane dashboard."
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
    $managerPidPath = Join-Path $stateRoot "manager.pid"
    $runId = "{0}-pid{1}" -f (
        (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
    ), $PID
    $runLogRoot = Join-Path (Join-Path $logRoot "runs") $runId
    New-Item -ItemType Directory -Path $runLogRoot -Force | Out-Null

    if (-not $SkipListener) {
        try {
            # Invoke the reviewed launcher in-process. Capturing a nested native
            # powershell.exe pipeline can keep its output pipe alive through the
            # long-running listener process tree and block manager startup forever.
            $listenerStatus = @(& $listenerScript 2>&1)
            Write-BootstrapLog ($listenerStatus -join " ")
        }
        catch {
            Write-BootstrapLog "WARNING: $($_.Exception.Message)"
        }
    }

    $expectedManifest = [regex]::Escape($ManagerManifest)
    $existingManagers = @(
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
            Where-Object {
                $_.CommandLine -match (
                    "shadowbane_lab\.cli\s+manager\s+app\s+" +
                    $expectedManifest
                )
            }
    )
    $trackedManager = $null
    if (Test-Path -LiteralPath $managerPidPath -PathType Leaf) {
        $trackedText = (Get-Content -LiteralPath $managerPidPath -Raw).Trim()
        $trackedId = 0
        if ([int]::TryParse($trackedText, [ref]$trackedId) -and $trackedId -gt 0) {
            $trackedManager = $existingManagers |
                Where-Object { $_.ProcessId -eq $trackedId } |
                Select-Object -First 1
        }
        if ($null -eq $trackedManager) {
            Remove-Item -LiteralPath $managerPidPath -Force
            Write-BootstrapLog "Removed a stale manager PID file."
        }
    }
    if ($null -ne $trackedManager) {
        Write-BootstrapLog (
            "WonderBane control center is already running (PID " +
            $trackedManager.ProcessId + ")."
        )
        Open-CurrentDashboard
        exit 0
    }
    if ($existingManagers.Count -gt 0) {
        throw (
            "Found an untracked WonderBane manager process (PID(s) " +
            (($existingManagers.ProcessId | Sort-Object) -join ", ") +
            "); refusing to start a competing dashboard."
        )
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
    $preflightRunPath = Join-Path $runLogRoot "manager-preflight.json"
    $preflightText = $preflight -join "`n"
    $utf8WithoutBom = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText($preflightRunPath, "$preflightText`n", $utf8WithoutBom)
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
        "--live",
        "--pid-file",
        $managerPidPath,
        "--port",
        "$ManagerPort",
        "--authorization-token-file",
        $dashboardTokenPath
    )
    if ($NoBrowser) {
        $managerArguments += "--no-browser"
    }
    $managerStdout = Join-Path $runLogRoot "manager.stdout.log"
    $managerStderr = Join-Path $runLogRoot "manager.stderr.log"
    $managerProcess = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList $managerArguments `
        -WorkingDirectory $RepositoryShare `
        -WindowStyle Hidden `
        -RedirectStandardOutput $managerStdout `
        -RedirectStandardError $managerStderr `
        -PassThru

    $startupDeadline = (Get-Date).AddSeconds(10)
    $runtimeManagerId = 0
    while ((Get-Date) -lt $startupDeadline) {
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
        if (Test-Path -LiteralPath $managerPidPath -PathType Leaf) {
            $runtimeText = (Get-Content -LiteralPath $managerPidPath -Raw).Trim()
            if ([int]::TryParse($runtimeText, [ref]$runtimeManagerId) -and (
                $runtimeManagerId -gt 0
            )) {
                $runtimeProcess = Get-CimInstance `
                    Win32_Process `
                    -Filter "ProcessId = $runtimeManagerId" `
                    -ErrorAction SilentlyContinue
                if (
                    $null -ne $runtimeProcess -and
                    $runtimeProcess.Name -eq "python.exe" -and
                    $runtimeProcess.CommandLine -match "shadowbane_lab\.cli\s+manager\s+app" -and
                    $runtimeProcess.CommandLine -match $expectedManifest
                ) {
                    $latestRun = [ordered]@{
                        schema_version = 1
                        started_at_utc = [DateTime]::UtcNow.ToString("o")
                        process_id = $runtimeManagerId
                        run_directory = $runLogRoot
                        preflight = $preflightRunPath
                        standard_output = $managerStdout
                        standard_error = $managerStderr
                    } | ConvertTo-Json
                    [IO.File]::WriteAllText(
                        (Join-Path $logRoot "manager-latest.json"),
                        "$latestRun`n",
                        $utf8WithoutBom
                    )
                    Write-BootstrapLog (
                        "WonderBane control center started (runtime PID $runtimeManagerId)."
                    )
                    exit 0
                }
            }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "WonderBane control center did not publish a valid runtime PID within ten seconds."
}
catch {
    Write-BootstrapLog "ERROR: $($_.Exception.Message)"
    throw
}
