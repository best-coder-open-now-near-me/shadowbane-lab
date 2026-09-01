[CmdletBinding()]
param(
    [ValidateSet('standard', 'full', 'triggered')]
    [string]$Profile = 'standard',
    [string]$ClientExecutable =
        "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\sb.exe",
    [string]$ClientDirectory = '',
    [string]$ReferenceExecutable = '',
    [string]$AlignmentProfileDirectory = '',
    [string]$OutputRoot =
        "$env:LOCALAPPDATA\shadowbane-lab\diagnostics",
    [string]$PythonPath = '',
    [ValidateRange(0.0, 86400.0)]
    [double]$DurationSeconds = 0.0,
    [ValidateRange(0.0, 60.0)]
    [double]$IntervalSeconds = 0.0,
    [ValidateRange(0.0, 3600.0)]
    [double]$PreTriggerSeconds = 0.0,
    [ValidateRange(0.0, 3600.0)]
    [double]$PostTriggerSeconds = 0.0,
    [string[]]$Log = @(),
    [string]$ExtensionEvents = '',
    [string]$NetworkSummary = '',
    [string]$PacketCapture = '',
    [string]$EtwTrace = '',
    [string]$ProcessDump = '',
    [string[]]$Snapshot = @(),
    [string[]]$ChannelFile = @(),
    [string[]]$Trigger = @(),
    [string]$ManualTriggerFile = '',
    [string]$ScreenshotRegion = '',
    [ValidateRange(0.1, 3600.0)]
    [double]$ScreenshotIntervalSeconds = 5.0,
    [ValidateRange(0.0, 16384.0)]
    [double]$InitialLogMiB = 1.0,
    [ValidateRange(0.001, 16384.0)]
    [double]$MaximumChannelMiB = 64.0,
    [switch]$NoAnalyze
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$sourceDirectory = Join-Path $repositoryRoot 'src'
if (-not (Test-Path -LiteralPath $sourceDirectory -PathType Container)) {
    throw "Shadowbane Lab source directory was not found: $sourceDirectory"
}

if (-not $PythonPath) {
    $workspacePython = Join-Path $env:USERPROFILE 'shadowbane-lab\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $workspacePython -PathType Leaf) {
        $PythonPath = $workspacePython
    }
    else {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($null -eq $pythonCommand) {
            throw 'Python was not found in the workspace virtual environment or on PATH.'
        }
        $PythonPath = $pythonCommand.Source
    }
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python was not found: $PythonPath"
}
if (-not (Test-Path -LiteralPath $ClientExecutable -PathType Leaf)) {
    throw "WonderBane client executable was not found: $ClientExecutable"
}

$resolvedClient = (Resolve-Path -LiteralPath $ClientExecutable).Path
if (-not $ClientDirectory) {
    $ClientDirectory = Split-Path -Parent $resolvedClient
}
if (-not (Test-Path -LiteralPath $ClientDirectory -PathType Container)) {
    throw "WonderBane client directory was not found: $ClientDirectory"
}
if ($ReferenceExecutable -and -not (
    Test-Path -LiteralPath $ReferenceExecutable -PathType Leaf
)) {
    throw "Reference client executable was not found: $ReferenceExecutable"
}
if ($AlignmentProfileDirectory -and -not (
    Test-Path -LiteralPath $AlignmentProfileDirectory -PathType Container
)) {
    throw "Alignment profile directory was not found: $AlignmentProfileDirectory"
}

$processName = [IO.Path]::GetFileNameWithoutExtension($resolvedClient)
$matchingProcesses = @(
    Get-Process -Name $processName -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Path -and
            [string]::Equals(
                (Resolve-Path -LiteralPath $_.Path).Path,
                $resolvedClient,
                [StringComparison]::OrdinalIgnoreCase
            )
        }
)
if ($matchingProcesses.Count -ne 1) {
    throw (
        "Expected exactly one running process for $resolvedClient; " +
        "found $($matchingProcesses.Count)."
    )
}
$clientProcess = $matchingProcesses[0]

if (-not (Test-Path -LiteralPath $OutputRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
}
$timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$outputDirectory = Join-Path $OutputRoot "shadowbane-$Profile-$timestamp-$($clientProcess.Id)"
if (Test-Path -LiteralPath $outputDirectory) {
    throw "Refusing to reuse diagnostic output: $outputDirectory"
}

$arguments = [Collections.Generic.List[string]]::new()
foreach ($value in @(
    '-u',
    '-m',
    'shadowbane_lab.cli',
    'diagnose',
    'capture',
    $outputDirectory,
    '--pid',
    "$($clientProcess.Id)",
    '--profile',
    $Profile,
    '--client-executable',
    $resolvedClient,
    '--client-directory',
    (Resolve-Path -LiteralPath $ClientDirectory).Path,
    '--repository',
    $repositoryRoot,
    '--screenshot-interval',
    "$ScreenshotIntervalSeconds",
    '--initial-log-mib',
    "$InitialLogMiB",
    '--max-channel-mib',
    "$MaximumChannelMiB"
)) {
    $arguments.Add($value)
}

function Add-Option {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [string]$Value
    )
    if ($Value) {
        $arguments.Add($Name)
        $arguments.Add($Value)
    }
}

if ($DurationSeconds -gt 0) {
    Add-Option -Name '--duration' -Value "$DurationSeconds"
}
if ($IntervalSeconds -gt 0) {
    Add-Option -Name '--interval' -Value "$IntervalSeconds"
}
if ($PreTriggerSeconds -gt 0) {
    Add-Option -Name '--pre-trigger' -Value "$PreTriggerSeconds"
}
if ($PostTriggerSeconds -gt 0) {
    Add-Option -Name '--post-trigger' -Value "$PostTriggerSeconds"
}
Add-Option -Name '--reference-executable' -Value $ReferenceExecutable
Add-Option -Name '--alignment-profile-directory' -Value $AlignmentProfileDirectory
Add-Option -Name '--extension-events' -Value $ExtensionEvents
Add-Option -Name '--network-summary' -Value $NetworkSummary
Add-Option -Name '--packet-capture' -Value $PacketCapture
Add-Option -Name '--etw-trace' -Value $EtwTrace
Add-Option -Name '--process-dump' -Value $ProcessDump
Add-Option -Name '--manual-trigger-file' -Value $ManualTriggerFile
Add-Option -Name '--screenshot-region' -Value $ScreenshotRegion
foreach ($path in $Log) {
    Add-Option -Name '--log' -Value $path
}
foreach ($path in $Snapshot) {
    Add-Option -Name '--snapshot' -Value $path
}
foreach ($value in $ChannelFile) {
    Add-Option -Name '--channel-file' -Value $value
}
foreach ($value in $Trigger) {
    Add-Option -Name '--trigger' -Value $value
}
$arguments.Add('--json')

$env:PYTHONPATH = $sourceDirectory
Write-Host "Capturing $Profile diagnostics for PID $($clientProcess.Id)."
Write-Host "Evidence directory: $outputDirectory"
& $PythonPath @arguments
$captureExitCode = $LASTEXITCODE

$manifestDirectory = Join-Path $outputDirectory 'manifests'
$manifest = @(
    Get-ChildItem -LiteralPath $manifestDirectory -Filter '*.manifest.json' -File -ErrorAction SilentlyContinue
)
if (-not $NoAnalyze -and $manifest.Count -eq 1) {
    $analysisPath = Join-Path $outputDirectory 'analysis.json'
    $analysisArguments = @(
        '-u',
        '-m',
        'shadowbane_lab.cli',
        'diagnose',
        'analyze',
        (Join-Path $outputDirectory 'store'),
        $manifest[0].FullName,
        '--output',
        $analysisPath,
        '--json'
    )
    & $PythonPath @analysisArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Diagnostic analysis failed with exit code $LASTEXITCODE."
    }
    Write-Host "Analysis: $analysisPath"
}
elseif (-not $NoAnalyze) {
    Write-Warning "Expected one sealed manifest for analysis; found $($manifest.Count)."
}

Write-Host "Diagnostic evidence: $outputDirectory"
exit $captureExitCode
