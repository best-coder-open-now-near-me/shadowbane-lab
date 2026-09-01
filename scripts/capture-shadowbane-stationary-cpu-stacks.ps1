[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$CaptureDirectory,
    [ValidateRange(1, 30)]
    [int]$DurationSeconds = 10,
    [switch]$ConfirmStationary,
    [string]$OutputRoot = '',
    [string]$PythonPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $ConfirmStationary) {
    throw 'Pass -ConfirmStationary only while the reproduced client is visibly stationary.'
}

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
if (-not (Test-Path -LiteralPath $CaptureDirectory -PathType Container)) {
    throw "Diagnostic capture directory was not found: $CaptureDirectory"
}
$resolvedCapture = (Resolve-Path -LiteralPath $CaptureDirectory).Path.TrimEnd('\')
$captureAttributes = (Get-Item -LiteralPath $resolvedCapture).Attributes
if (($captureAttributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'Refusing a reparse-point diagnostic capture directory.'
}

$env:PYTHONPATH = $sourceDirectory
$planOutput = @(
    & $PythonPath -u -m shadowbane_lab.cli `
        diagnose `
        stack-plan `
        $resolvedCapture `
        --json
)
if ($LASTEXITCODE -ne 0) {
    throw "Stationary stack-capture gate rejected this run: $($planOutput -join ' ')"
}
$plan = ($planOutput -join "`n") | ConvertFrom-Json
if (-not $plan.ok -or $plan.status -cne 'recommended') {
    throw 'Stationary stack-capture plan did not return a recommended exact target.'
}
$targetProcessId = [int]$plan.process_identity.process_id
$targetCreationFiletimeUtc = [long]$plan.process_identity.process_creation_filetime_utc
$targetExecutable = [string]$plan.process_identity.executable_path

function Assert-ExactTarget {
    param(
        [Parameter(Mandatory)]
        [int]$ProcessId,
        [Parameter(Mandatory)]
        [long]$CreationFiletimeUtc,
        [Parameter(Mandatory)]
        [string]$ExecutablePath
    )
    $process = Get-Process -Id $ProcessId -ErrorAction Stop
    $observedCreation = $process.StartTime.ToUniversalTime().ToFileTimeUtc()
    if ($observedCreation -ne $CreationFiletimeUtc) {
        throw "PID $ProcessId no longer has creation FILETIME $CreationFiletimeUtc."
    }
    if (-not $process.Path) {
        throw "Cannot resolve the executable path for PID $ProcessId."
    }
    $observedExecutable = (Resolve-Path -LiteralPath $process.Path).Path
    $expectedExecutable = (Resolve-Path -LiteralPath $ExecutablePath).Path
    if (-not [string]::Equals(
        $observedExecutable,
        $expectedExecutable,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "PID $ProcessId executable identity changed before stack capture completed."
    }
}

Assert-ExactTarget `
    -ProcessId $targetProcessId `
    -CreationFiletimeUtc $targetCreationFiletimeUtc `
    -ExecutablePath $targetExecutable

$wprPath = Join-Path $env:SystemRoot 'System32\wpr.exe'
if (-not (Test-Path -LiteralPath $wprPath -PathType Leaf)) {
    throw "Windows Performance Recorder was not found: $wprPath"
}
$statusOutput = (& $wprPath -status 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $statusOutput -notmatch 'WPR is not recording') {
    throw (
        'WPR is already active or its idle state could not be proven. ' +
        'Refusing to merge with or stop another trace.'
    )
}

if (-not $OutputRoot) {
    $OutputRoot = Join-Path (Split-Path -Parent $resolvedCapture) 'cpu-stack-captures'
}
if (-not (Test-Path -LiteralPath $OutputRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $OutputRoot | Out-Null
}
$resolvedOutputRoot = (Resolve-Path -LiteralPath $OutputRoot).Path.TrimEnd('\')
$outputAttributes = (Get-Item -LiteralPath $resolvedOutputRoot).Attributes
if (($outputAttributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'Refusing a reparse-point CPU-stack output root.'
}
if (
    [string]::Equals(
        $resolvedOutputRoot,
        $resolvedCapture,
        [StringComparison]::OrdinalIgnoreCase
    ) -or
    $resolvedOutputRoot.StartsWith(
        "$resolvedCapture\",
        [StringComparison]::OrdinalIgnoreCase
    )
) {
    throw 'CPU-stack output must stay outside the sealed diagnostic capture directory.'
}

$timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$outputDirectory = Join-Path $resolvedOutputRoot (
    "stationary-cpu-stacks-$timestamp-$targetProcessId"
)
New-Item -ItemType Directory -Path $outputDirectory -ErrorAction Stop | Out-Null
$etlPath = Join-Path $outputDirectory 'cpu-sampling.etl'
$receiptPath = Join-Path $outputDirectory 'capture.json'
$startedAtUtc = [DateTime]::UtcNow.ToString('o')
$endedAtUtc = $null
$identityFailure = $null
$traceStarted = $false
try {
    & $wprPath -start CPU -filemode
    if ($LASTEXITCODE -ne 0) {
        throw "WPR CPU profile failed to start with exit code $LASTEXITCODE."
    }
    $traceStarted = $true
    Start-Sleep -Seconds $DurationSeconds
    try {
        Assert-ExactTarget `
            -ProcessId $targetProcessId `
            -CreationFiletimeUtc $targetCreationFiletimeUtc `
            -ExecutablePath $targetExecutable
    }
    catch {
        $identityFailure = $_.Exception.Message
    }
    $endedAtUtc = [DateTime]::UtcNow.ToString('o')
    & $wprPath -stop $etlPath
    if ($LASTEXITCODE -ne 0) {
        throw "WPR CPU profile failed to stop with exit code $LASTEXITCODE."
    }
    $traceStarted = $false
}
finally {
    if ($traceStarted) {
        & $wprPath -cancel | Out-Null
    }
}

if (-not (Test-Path -LiteralPath $etlPath -PathType Leaf)) {
    throw "WPR did not create the expected ETL file: $etlPath"
}
$etlFile = Get-Item -LiteralPath $etlPath
if ($etlFile.Length -le 0) {
    throw 'WPR created an empty CPU-sampling ETL file.'
}
$etlSha256 = (Get-FileHash -LiteralPath $etlPath -Algorithm SHA256).Hash.ToLowerInvariant()
$receipt = [ordered]@{
    schema_version = 1
    status = if ($identityFailure) { 'incomplete' } else { 'complete' }
    captured_at_utc = $endedAtUtc
    started_at_utc = $startedAtUtc
    duration_seconds = $DurationSeconds
    collection_scope = 'system-wide-cpu-sampling-targeted-during-analysis'
    target_authority = 'exact-pid-creation-time-executable-path'
    target_identity = $plan.process_identity
    target_identity_verified_before = $true
    target_identity_verified_after = -not [bool]$identityFailure
    identity_failure = $identityFailure
    operator_confirmed_stationary = $true
    source_capture_directory = $resolvedCapture
    source_manifest_id = $plan.manifest_id
    source_timeline_path = $plan.timeline_path
    source_timeline_sha256 = $plan.timeline_sha256
    recommendation_slow_frame_count = (
        $plan.stationary_resident_unexplained_slow_frame_count
    )
    etl_file = Split-Path -Leaf $etlPath
    etl_size_bytes = $etlFile.Length
    etl_sha256 = $etlSha256
    game_input_injected = $false
    process_memory_written = $false
} | ConvertTo-Json -Depth 10
$utf8 = [Text.UTF8Encoding]::new($false)
$stream = [IO.File]::Open(
    $receiptPath,
    [IO.FileMode]::CreateNew,
    [IO.FileAccess]::Write,
    [IO.FileShare]::None
)
try {
    $bytes = $utf8.GetBytes("$receipt`n")
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush($true)
}
finally {
    $stream.Dispose()
}

Write-Host "CPU-stack ETL: $etlPath"
Write-Host "CPU-stack receipt: $receiptPath"
Write-Host (
    'Collection was system-wide; filter analysis to the exact target PID and creation lifetime ' +
    'recorded in capture.json.'
)
if ($identityFailure) {
    throw "Target identity changed during CPU-stack capture: $identityFailure"
}
