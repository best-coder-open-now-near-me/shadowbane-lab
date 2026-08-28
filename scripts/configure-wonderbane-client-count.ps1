[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 32)]
    [int] $ClientCount,
    [ValidateRange(320, 16384)]
    [int] $DisplayWidth = 1920,
    [ValidateRange(240, 16384)]
    [int] $DisplayHeight = 955,
    [string] $RepositoryShare = "\\VBOXSVR\codexrepo",
    [string] $PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $LocalStateRoot = "$env:LOCALAPPDATA\ShadowbaneLab",
    [switch] $Restart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$manifestPath = Join-Path $LocalStateRoot "client-manager.json"
$managerSource = Join-Path $RepositoryShare "src"
foreach ($required in @(
    @{ Path = $RepositoryShare; Kind = "Container"; Description = "repository share" },
    @{ Path = $managerSource; Kind = "Container"; Description = "manager source tree" },
    @{ Path = $PythonPath; Kind = "Leaf"; Description = "Shadowbane Lab Python" },
    @{ Path = $manifestPath; Kind = "Leaf"; Description = "manager manifest" }
)) {
    if (-not (Test-Path -LiteralPath $required.Path -PathType $required.Kind)) {
        throw "$($required.Description) was not found: $($required.Path)"
    }
}

$env:PYTHONPATH = $managerSource
& $PythonPath `
    -m shadowbane_lab.cli `
    manager configure-slots `
    $manifestPath `
    --count $ClientCount `
    --display-width $DisplayWidth `
    --display-height $DisplayHeight `
    --apply
if ($LASTEXITCODE -ne 0) {
    throw "WonderBane client slot configuration failed."
}

if (-not $Restart) {
    Write-Output "The running control center still has its prior immutable slot list."
    Write-Output "Re-run with -Restart, or restart the VM, to load the new slots."
    exit 0
}

$managerPidPath = Join-Path $LocalStateRoot "manager.pid"
if (Test-Path -LiteralPath $managerPidPath -PathType Leaf) {
    $managerProcessIdText = (Get-Content -LiteralPath $managerPidPath -Raw).Trim()
    $managerProcessId = 0
    if (-not [int]::TryParse($managerProcessIdText, [ref]$managerProcessId) -or (
        $managerProcessId -le 0
    )) {
        throw "Manager PID file does not contain a positive integer: $managerPidPath"
    }
    $managerProcess = Get-CimInstance `
        Win32_Process `
        -Filter "ProcessId = $managerProcessId" `
        -ErrorAction SilentlyContinue
    if ($null -ne $managerProcess) {
        $expectedManifest = [regex]::Escape($manifestPath)
        if (
            $managerProcess.Name -ne "python.exe" -or
            $managerProcess.CommandLine -notmatch "shadowbane_lab\.cli\s+manager\s+app" -or
            $managerProcess.CommandLine -notmatch $expectedManifest
        ) {
            throw "Refusing to stop PID $managerProcessId because it is not the exact manager process."
        }
        Stop-Process -Id $managerProcessId
        $deadline = (Get-Date).AddSeconds(5)
        while (Get-Process -Id $managerProcessId -ErrorAction SilentlyContinue) {
            if ((Get-Date) -ge $deadline) {
                throw "Manager PID $managerProcessId did not stop within five seconds."
            }
            Start-Sleep -Milliseconds 100
        }
        Write-Output "Stopped the prior control-center manager PID $managerProcessId."
    }
}

$localBootstrap = Join-Path $LocalStateRoot "start-wonderbane-control-center.ps1"
if (-not (Test-Path -LiteralPath $localBootstrap -PathType Leaf)) {
    throw "Local control-center bootstrap was not found: $localBootstrap"
}
& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $localBootstrap `
    -RepositoryShare $RepositoryShare `
    -LocalStateRoot $LocalStateRoot
if ($LASTEXITCODE -ne 0) {
    throw "WonderBane control center did not restart successfully."
}
Write-Output "WonderBane control center restarted with $ClientCount configured slots."
