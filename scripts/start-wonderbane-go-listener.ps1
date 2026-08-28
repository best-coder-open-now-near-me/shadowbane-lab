[CmdletBinding()]
param(
    [string] $RepositoryRoot = "\\VBOXSVR\codexrepo",
    [string] $PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $ClientProfile = "\\VBOXSVR\codexdiag\wonderbane-travel.local.json",
    [string] $DestinationState = "\\VBOXSVR\codexdiag\bounded-route-state.json",
    [string] $WorldDef = "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\Config\WorldDef.cfg",
    [string] $NamedDestinationOverrides = "\\VBOXSVR\codexrepo\configs\wonderbane-named-destinations.json",
    [string] $PveClientProfile = "\\VBOXSVR\codexrepo\configs\wonderbane-pve.local.json",
    [string] $PveHotbarConfig = "",
    [Alias("PveNavigationCacheDirectory")]
    [string] $NavigationCacheDirectory = "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\cache",
    [ValidateRange(1, 10)]
    [int] $PveMaxKills = 3,
    [ValidateRange(20, 1000)]
    [double] $PveCampRadius = 120,
    [ValidateRange(100, 100000)]
    [int] $PveRetainedTraceSteps = 2000,
    [switch] $BoundedPve,
    [string] $LogDirectory = "\\VBOXSVR\codexdiag",
    [string] $LearnedNavigationState = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable was not found: $PythonPath"
}
if (-not (Test-Path -LiteralPath $RepositoryRoot -PathType Container)) {
    throw "Repository share was not found: $RepositoryRoot"
}
if (-not (Test-Path -LiteralPath $ClientProfile -PathType Leaf)) {
    throw "Live travel profile was not found: $ClientProfile"
}
if (-not (Test-Path -LiteralPath $WorldDef -PathType Leaf)) {
    throw "WorldDef was not found: $WorldDef"
}
if (-not (Test-Path -LiteralPath $NamedDestinationOverrides -PathType Leaf)) {
    throw "Named-destination overrides were not found: $NamedDestinationOverrides"
}
if (-not (Test-Path -LiteralPath $PveClientProfile -PathType Leaf)) {
    throw "Live PvE profile was not found: $PveClientProfile"
}
if (-not (Test-Path -LiteralPath $NavigationCacheDirectory -PathType Container)) {
    throw "WonderBane client cache directory was not found: $NavigationCacheDirectory"
}
if (-not $PveHotbarConfig) {
    $hotbars = @(
        Get-ChildItem `
            "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\Config\SCREEN_GAME_*_Wonderbane.cfg" `
            -File `
            -ErrorAction SilentlyContinue
    )
    if ($hotbars.Count -eq 1) {
        $PveHotbarConfig = $hotbars[0].FullName
    }
}
if ($PveHotbarConfig -and -not (Test-Path -LiteralPath $PveHotbarConfig -PathType Leaf)) {
    throw "WonderBane character hotbar was not found: $PveHotbarConfig"
}
if (-not (Test-Path -LiteralPath $LogDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
}
if (-not $LearnedNavigationState) {
    $LearnedNavigationState = Join-Path $LogDirectory "learned-navigation-state.json"
}

$existing = @(
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object {
            $_.CommandLine -match "shadowbane_lab\.cli\s+client\s+listen-go"
        }
)
if ($existing.Count -gt 0) {
    $listenerProcessIds = @($existing.ProcessId | Sort-Object)
    $ids = $listenerProcessIds -join ", "
    Stop-Process -Id $listenerProcessIds
    $stopDeadline = (Get-Date).AddSeconds(5)
    while (@(
        $listenerProcessIds | ForEach-Object {
            Get-Process -Id $_ -ErrorAction SilentlyContinue
        }
    ).Count -gt 0) {
        if ((Get-Date) -ge $stopDeadline) {
            throw "Listener PIDs $ids did not all stop within five seconds."
        }
        Start-Sleep -Milliseconds 100
    }
    Write-Output "Stopped existing Shadowbane listener PIDs $ids before restart."
}

$standardOutput = Join-Path $LogDirectory "go-listener.stdout.jsonl"
$standardError = Join-Path $LogDirectory "go-listener.stderr.log"
$env:PYTHONPATH = Join-Path $RepositoryRoot "src"
$arguments = @(
    "-u",
    "-m",
    "shadowbane_lab.cli",
    "client",
    "listen-go",
    "--destination-state", $DestinationState,
    "--client-profile", $ClientProfile,
    "--world-def", $WorldDef,
    "--named-destination-overrides", $NamedDestinationOverrides,
    "--pve-client-profile", $PveClientProfile,
    "--pve-evidence-directory", $LogDirectory,
    "--navigation-cache-directory", $NavigationCacheDirectory,
    "--learned-navigation-state", $LearnedNavigationState,
    "--pve-max-kills", "$PveMaxKills",
    "--pve-max-seconds", "300",
    "--pve-max-encounter-seconds", "120",
    "--pve-recovery-timeout-seconds", "30",
    "--pve-poll-ms", "100",
    "--pve-camp-radius", "$PveCampRadius",
    "--pve-retained-trace-steps", "$PveRetainedTraceSteps",
    "--max-seconds", "300",
    "--wait-for-client-seconds", "10",
    "--poll-ms", "200",
    "--click-interval-ms", "2000",
    "--live",
    "--json"
)
if ($PveHotbarConfig) {
    $arguments += @(
        "--hotkey-config", $PveHotbarConfig,
        "--pve-hotbar-config", $PveHotbarConfig
    )
}
if (-not $BoundedPve) {
    $arguments += "--pve-continuous"
}

$process = Start-Process `
    -FilePath $PythonPath `
    -ArgumentList $arguments `
    -WorkingDirectory $RepositoryRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $standardOutput `
    -RedirectStandardError $standardError `
    -PassThru

Start-Sleep -Milliseconds 750
$process.Refresh()
if ($process.HasExited) {
    $detail = if (Test-Path -LiteralPath $standardError) {
        (Get-Content -LiteralPath $standardError -Raw).Trim()
    }
    else {
        "listener exited without an error log"
    }
    throw "Shadowbane chat listener failed to start: $detail"
}

Set-Content -LiteralPath (Join-Path $LogDirectory "go-listener.pid") `
    -Value $process.Id `
    -Encoding ascii
Write-Output "Shadowbane chat listener started (PID $($process.Id))."
