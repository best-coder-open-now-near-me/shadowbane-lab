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
    $expectedManifest = [regex]::Escape($manifestPath)
    $exactManagers = @(
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
            Where-Object {
                $_.CommandLine -match "shadowbane_lab\.cli\s+manager\s+app" -and
                $_.CommandLine -match $expectedManifest
            }
    )
    $managerProcess = $exactManagers |
        Where-Object { $_.ProcessId -eq $managerProcessId } |
        Select-Object -First 1
    if ($null -ne $managerProcess) {
        $familyIds = [System.Collections.Generic.HashSet[int]]::new()
        [void] $familyIds.Add($managerProcessId)
        do {
            $added = $false
            foreach ($candidate in $exactManagers) {
                if ($familyIds.Contains([int] $candidate.ParentProcessId)) {
                    if ($familyIds.Add([int] $candidate.ProcessId)) {
                        $added = $true
                    }
                }
                if ($familyIds.Contains([int] $candidate.ProcessId)) {
                    $parentIsExact = @(
                        $exactManagers |
                            Where-Object { $_.ProcessId -eq $candidate.ParentProcessId }
                    ).Count -eq 1
                    if (
                        $parentIsExact -and
                        $familyIds.Add([int] $candidate.ParentProcessId)
                    ) {
                        $added = $true
                    }
                }
            }
        } while ($added)
        $familyProcesses = @(
            $exactManagers | Where-Object { $familyIds.Contains([int] $_.ProcessId) }
        )
        if ($familyProcesses.Count -ne $exactManagers.Count) {
            throw "Refusing to stop multiple unrelated manager process families."
        }
        $familyProcessIds = @($familyProcesses.ProcessId | Sort-Object -Descending)
        Stop-Process -Id $familyProcessIds
        $deadline = (Get-Date).AddSeconds(5)
        while (@(Get-Process -Id $familyProcessIds -ErrorAction SilentlyContinue).Count -gt 0) {
            if ((Get-Date) -ge $deadline) {
                throw "Manager process family did not stop within five seconds."
            }
            Start-Sleep -Milliseconds 100
        }
        Write-Output (
            "Stopped the prior control-center manager process family: " +
            ($familyProcessIds -join ", ") + "."
        )
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
