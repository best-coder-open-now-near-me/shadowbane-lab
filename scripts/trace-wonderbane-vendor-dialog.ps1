[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Label,

    [ValidateRange(2, 3600)]
    [int]$TimeoutSeconds = 60,

    [ValidateRange(0.1, 300.0)]
    [double]$SettleSeconds = 2.0,

    [ValidateNotNullOrEmpty()]
    [string]$OutputDirectory = '\\VBOXSVR\codexdiag'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($SettleSeconds -ge $TimeoutSeconds) {
    throw 'SettleSeconds must be less than TimeoutSeconds.'
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$sourceDirectory = Join-Path $repositoryRoot 'src'
$python = Join-Path $env:USERPROFILE 'shadowbane-lab\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Shadowbane Lab Python was not found at $python or on PATH."
    }
    $python = $pythonCommand.Source
}

if (-not (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
    throw "Shadowbane Lab source directory was not found at $sourceDirectory."
}
if (-not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
}

$safeLabel = [regex]::Replace($Label.Trim().ToLowerInvariant(), '[^a-z0-9._-]+', '-')
$safeLabel = $safeLabel.Trim('-')
if ([string]::IsNullOrWhiteSpace($safeLabel)) {
    throw 'Label must contain at least one letter or number.'
}

$timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$outputPath = Join-Path $OutputDirectory "vendor-dialog-$safeLabel-$timestamp.jsonl"
$env:PYTHONPATH = $sourceDirectory

Write-Host "Arming vendor-dialog capture for '$Label'."
Write-Host "Evidence will be written to $outputPath"

& $python -m shadowbane_lab.cli client trace-native-vendor-dialog `
    --output $outputPath `
    --label $Label `
    --timeout-seconds $TimeoutSeconds `
    --settle-seconds $SettleSeconds

if ($LASTEXITCODE -ne 0) {
    throw "Vendor-dialog capture failed with exit code $LASTEXITCODE."
}
