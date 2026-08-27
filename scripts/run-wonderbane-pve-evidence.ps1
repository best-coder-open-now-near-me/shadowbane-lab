[CmdletBinding()]
param(
    [string] $RepositoryRoot = "\\VBOXSVR\codexrepo",
    [string] $PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $ClientProfile = "\\VBOXSVR\codexrepo\configs\wonderbane-pve.local.json",
    [string] $CombatLog = "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\Logs\shadowbane-combat.log.txt",
    [string] $HotbarConfig = "",
    [string] $EvidenceOutput = "",
    [ValidateRange(1, 10)]
    [int] $MaximumKills = 1,
    [ValidateRange(1, 900)]
    [int] $MaximumSeconds = 30
)

$ErrorActionPreference = "Stop"

foreach ($path in @($RepositoryRoot, $PythonPath, $ClientProfile, $CombatLog)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required bounded-PvE path was not found: $path"
    }
}
if (-not $HotbarConfig) {
    $hotbars = @(
        Get-ChildItem `
            "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\Config\SCREEN_GAME_*_Wonderbane.cfg" `
            -File
    )
    if ($hotbars.Count -ne 1) {
        throw "Expected exactly one WonderBane character hotbar; found $($hotbars.Count)."
    }
    $HotbarConfig = $hotbars[0].FullName
}
if (-not (Test-Path -LiteralPath $HotbarConfig -PathType Leaf)) {
    throw "WonderBane character hotbar was not found: $HotbarConfig"
}
if (-not $EvidenceOutput) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $EvidenceOutput = "\\VBOXSVR\codexdiag\pve-evidence-$timestamp.json"
}
if (Test-Path -LiteralPath $EvidenceOutput) {
    throw "Refusing to overwrite existing PvE evidence: $EvidenceOutput"
}

$visibleClients = @(
    Get-Process -Name "sb" -ErrorAction Stop |
        Where-Object { $_.MainWindowHandle -ne 0 }
)
if ($visibleClients.Count -ne 1) {
    throw "Expected exactly one visible Shadowbane client; found $($visibleClients.Count)."
}

Add-Type -AssemblyName Microsoft.VisualBasic
if (-not [Microsoft.VisualBasic.Interaction]::AppActivate($visibleClients[0].Id)) {
    throw "Could not focus visible Shadowbane PID $($visibleClients[0].Id)."
}
Start-Sleep -Milliseconds 500

$env:PYTHONPATH = Join-Path $RepositoryRoot "src"
& $PythonPath -u -m shadowbane_lab.cli client run-pve `
    --client-profile $ClientProfile `
    --combat-log $CombatLog `
    --hotbar-config $HotbarConfig `
    --policy "proc-assassin" `
    --max-kills $MaximumKills `
    --max-seconds $MaximumSeconds `
    --wait-for-client-seconds 5 `
    --poll-ms 100 `
    --evidence-output $EvidenceOutput `
    --live `
    --json
$exitCode = $LASTEXITCODE

Write-Output "PvE evidence: $EvidenceOutput"
exit $exitCode
