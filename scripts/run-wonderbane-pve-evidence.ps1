[CmdletBinding()]
param(
    [string] $RepositoryRoot = "\\VBOXSVR\codexrepo",
    [string] $PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $ClientProfile = "\\VBOXSVR\codexrepo\configs\wonderbane-pve.local.json",
    [string] $HotbarConfig = "",
    [string] $EvidenceOutput = "",
    [ValidateRange(1, 10)]
    [int] $MaximumKills = 1,
    [ValidateRange(1, 900)]
    [int] $MaximumSeconds = 180,
    [ValidateRange(5, 300)]
    [int] $MaximumEncounterSeconds = 120,
    [ValidateRange(1, 300)]
    [int] $RecoveryTimeoutSeconds = 30,
    [ValidateRange(0, 300)]
    [int] $WaitForClientSeconds = 15
)

$ErrorActionPreference = "Stop"

foreach ($path in @($RepositoryRoot, $PythonPath, $ClientProfile)) {
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

$env:PYTHONPATH = Join-Path $RepositoryRoot "src"
& $PythonPath -u -m shadowbane_lab.cli client run-pve `
    --client-profile $ClientProfile `
    --combat-source "hud" `
    --hotbar-config $HotbarConfig `
    --policy "proc-assassin" `
    --max-kills $MaximumKills `
    --max-seconds $MaximumSeconds `
    --max-encounter-seconds $MaximumEncounterSeconds `
    --recovery-timeout-seconds $RecoveryTimeoutSeconds `
    --recovery-health-fraction 0.75 `
    --recovery-mana-fraction 0.15 `
    --recovery-stamina-fraction 0.25 `
    --wait-for-client-seconds $WaitForClientSeconds `
    --poll-ms 100 `
    --evidence-output $EvidenceOutput `
    --live `
    --json
$exitCode = $LASTEXITCODE

Write-Output "PvE evidence: $EvidenceOutput"
exit $exitCode
