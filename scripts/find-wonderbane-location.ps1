<#
.SYNOPSIS
Keeps an interactive WonderBane location-metadata prompt open.

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\find-wonderbane-location.ps1

.EXAMPLE
.\scripts\find-wonderbane-location.ps1 -Query "Black Drake Swamp"
#>
[CmdletBinding()]
param(
    [string] $WorldDef = "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\Config\WorldDef.cfg",
    [string] $NamedDestinationOverrides = "",
    [string] $RepositoryRoot = "",
    [string] $PythonPath = "",
    [ValidateRange(1, 50)]
    [int] $Limit = 8,
    [string] $Query = "",
    [switch] $AsJson,
    [switch] $NoOverrides
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $RepositoryRoot) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
if (-not (Test-Path -LiteralPath $WorldDef -PathType Leaf)) {
    throw "WorldDef was not found: $WorldDef"
}
if (-not (Test-Path -LiteralPath $RepositoryRoot -PathType Container)) {
    throw "Repository root was not found: $RepositoryRoot"
}

if (-not $PythonPath) {
    $pythonCandidates = @(
        (Join-Path $RepositoryRoot ".venv\Scripts\python.exe"),
        (Join-Path $env:USERPROFILE "shadowbane-lab\.venv\Scripts\python.exe")
    )
    $PythonPath = @(
        $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    ) | Select-Object -First 1
    if (-not $PythonPath) {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($null -ne $pythonCommand) {
            $PythonPath = $pythonCommand.Source
        }
    }
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python 3.11 or newer was not found. Supply its path with -PythonPath."
}

$arguments = @(
    "-m", "shadowbane_lab.location_lookup",
    "--world-def", $WorldDef,
    "--limit", "$Limit"
)
if ($Query) {
    $arguments += @("--query", $Query)
}
if ($AsJson) {
    $arguments += "--json"
}
if (-not $NoOverrides) {
    if (-not $NamedDestinationOverrides) {
        $NamedDestinationOverrides = Join-Path `
            $RepositoryRoot `
            "configs\wonderbane-named-destinations.json"
    }
    if (Test-Path -LiteralPath $NamedDestinationOverrides -PathType Leaf) {
        $arguments += @("--overrides", $NamedDestinationOverrides)
    }
    elseif ($PSBoundParameters.ContainsKey("NamedDestinationOverrides")) {
        throw "Named-destination overrides were not found: $NamedDestinationOverrides"
    }
}

$sourceRoot = Join-Path $RepositoryRoot "src"
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = if ($previousPythonPath) {
        "$sourceRoot$([IO.Path]::PathSeparator)$previousPythonPath"
    }
    else {
        $sourceRoot
    }
    & $PythonPath @arguments
    $pythonExitCode = $LASTEXITCODE
}
finally {
    if ($null -eq $previousPythonPath) {
        Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONPATH = $previousPythonPath
    }
}
exit $pythonExitCode
