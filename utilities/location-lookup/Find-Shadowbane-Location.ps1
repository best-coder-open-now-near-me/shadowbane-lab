<#
.SYNOPSIS
Runs the portable name-based Shadowbane location lookup.

.EXAMPLE
.\Find-Shadowbane-Location.ps1

.EXAMPLE
.\Find-Shadowbane-Location.ps1 -Query "Black Drake Swamp"
#>
[CmdletBinding()]
param(
    [string] $WorldDef = '',
    [ValidateRange(1, 50)]
    [int] $Limit = 8,
    [string] $Query = '',
    [switch] $AsJson,
    [switch] $NoOverrides
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$lookup = Join-Path (Split-Path -Parent $PSScriptRoot) 'ShadowbaneLocationLookup.exe'
if (-not (Test-Path -LiteralPath $lookup -PathType Leaf)) {
    throw "Portable location lookup executable was not found: $lookup"
}
$arguments = @('--limit', "$Limit")
if ($WorldDef) {
    $arguments += @('--world-def', $WorldDef)
}
if ($Query) {
    $arguments += @('--query', $Query)
}
if ($AsJson) {
    $arguments += '--json'
}
if ($NoOverrides) {
    $arguments += '--no-overrides'
}

& $lookup @arguments
exit $LASTEXITCODE
