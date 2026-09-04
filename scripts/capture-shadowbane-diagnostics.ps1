[CmdletBinding()]
param(
    [ValidateSet('standard', 'full', 'triggered')]
    [string]$Profile = 'standard',
    [ValidateRange(0, 2147483647)]
    [int]$ProcessId = 0,
    [switch]$AllMatchingProcesses,
    [string]$ClientExecutable =
        "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\sb.exe",
    [string]$ClientDirectory = '',
    [string]$ReferenceExecutable = '',
    [string]$AlignmentProfileDirectory = '',
    [string]$GraphicsRuntimeStatus = '',
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
    [switch]$PerformanceTelemetry,
    [switch]$HotspotProtocol,
    [switch]$NoAnalyze
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($HotspotProtocol) {
    if ($AllMatchingProcesses) {
        throw 'HotspotProtocol requires one exact process, not AllMatchingProcesses.'
    }
    if ($DurationSeconds -eq 0.0) {
        $DurationSeconds = 300.0
    }
    if ($IntervalSeconds -eq 0.0) {
        $IntervalSeconds = 0.125
    }
    if ($IntervalSeconds -lt 0.1 -or $IntervalSeconds -gt 0.2) {
        throw 'HotspotProtocol requires IntervalSeconds from 0.1 through 0.2 (5-10 Hz).'
    }
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
if ($AllMatchingProcesses) {
    if ($ProcessId -gt 0) {
        throw 'ProcessId and AllMatchingProcesses cannot be used together.'
    }
    if ($matchingProcesses.Count -eq 0) {
        throw "No running process matched the exact executable $resolvedClient."
    }

    $commonParameters = @{}
    foreach ($entry in $PSBoundParameters.GetEnumerator()) {
        $commonParameters[$entry.Key] = $entry.Value
    }
    [void]$commonParameters.Remove('AllMatchingProcesses')
    $captureScript = $MyInvocation.MyCommand.Path
    $jobs = @()
    try {
        foreach ($targetProcess in @($matchingProcesses | Sort-Object Id)) {
            $targetParameters = @{}
            foreach ($entry in $commonParameters.GetEnumerator()) {
                $targetParameters[$entry.Key] = $entry.Value
            }
            $targetParameters['ProcessId'] = $targetProcess.Id
            $targetCreationFiletimeUtc = (
                $targetProcess.StartTime.ToUniversalTime().ToFileTimeUtc()
            )
            Write-Host (
                "Attaching diagnostics to PID $($targetProcess.Id), creation FILETIME " +
                "$targetCreationFiletimeUtc, executable $resolvedClient"
            )
            $jobs += Start-Job -Name "shadowbane-diagnostics-$($targetProcess.Id)" -ScriptBlock {
                param(
                    [string]$ScriptPath,
                    [hashtable]$Parameters
                )
                & $ScriptPath @Parameters
            } -ArgumentList $captureScript, $targetParameters
        }
        Receive-Job -Job $jobs -Wait
        $failedJobs = @($jobs | Where-Object { $_.State -ne 'Completed' })
        if ($failedJobs.Count -gt 0) {
            $failedNames = ($failedJobs.Name | Sort-Object) -join ', '
            throw "One or more per-process captures failed: $failedNames"
        }
    }
    finally {
        $runningJobs = @($jobs | Where-Object { $_.State -eq 'Running' })
        if ($runningJobs.Count -gt 0) {
            Stop-Job -Job $runningJobs
        }
        if ($jobs.Count -gt 0) {
            Remove-Job -Job $jobs -Force
        }
    }
    return
}
if ($ProcessId -gt 0) {
    $selectedProcesses = @(
        $matchingProcesses | Where-Object { $_.Id -eq $ProcessId }
    )
    if ($selectedProcesses.Count -ne 1) {
        throw (
            "Requested PID $ProcessId is not one running process for the exact executable " +
            "$resolvedClient."
        )
    }
    $clientProcess = $selectedProcesses[0]
}
elseif ($matchingProcesses.Count -ne 1) {
    $candidateProcessIds = ($matchingProcesses.Id | Sort-Object) -join ', '
    throw (
        "Expected exactly one running process for $resolvedClient; " +
        "found $($matchingProcesses.Count). " +
        "Pass -ProcessId to select an exact live instance. Candidate PIDs: $candidateProcessIds"
    )
}
else {
    $clientProcess = $matchingProcesses[0]
}

$processCreationFiletimeUtc = $clientProcess.StartTime.ToUniversalTime().ToFileTimeUtc()
if (-not $GraphicsRuntimeStatus) {
    $graphicsStatusDirectory = Join-Path (
        Join-Path $env:LOCALAPPDATA 'ShadowbaneLab'
    ) 'client-extension'
    $expectedGraphicsRuntimeStatus = Join-Path $graphicsStatusDirectory (
        "graphics-status-$($clientProcess.Id)-$processCreationFiletimeUtc.json"
    )
    if (Test-Path -LiteralPath $expectedGraphicsRuntimeStatus -PathType Leaf) {
        $GraphicsRuntimeStatus = $expectedGraphicsRuntimeStatus
        Write-Host "Using exact graphics runtime status: $GraphicsRuntimeStatus"
    }
}
elseif (-not (Test-Path -LiteralPath $GraphicsRuntimeStatus -PathType Leaf)) {
    throw "Graphics runtime status was not found: $GraphicsRuntimeStatus"
}

$exportOutputRoot = ''
if ($OutputRoot.StartsWith('\\')) {
    $exportOutputRoot = $OutputRoot
    $OutputRoot = Join-Path $env:LOCALAPPDATA 'shadowbane-lab\diagnostic-staging'
    Write-Host (
        'Network output requested; capturing atomically on local storage before ' +
        "verified bundle export to $exportOutputRoot"
    )
}
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
    '--graphics-present',
    '--native-position',
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
Add-Option -Name '--graphics-runtime-status' -Value $GraphicsRuntimeStatus
if ($GraphicsRuntimeStatus) {
    $arguments.Add('--camera-state')
}
if ($PerformanceTelemetry -or $HotspotProtocol) {
    $arguments.Add('--performance-telemetry')
}
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
if ($HotspotProtocol) {
    $markerPrefix = (
        "& '$PythonPath' -u -m shadowbane_lab.cli diagnose mark " +
        "'$outputDirectory'"
    )
    Write-Host 'Hotspot protocol is active at 5-10 Hz. In another terminal, mark:'
    Write-Host (
        "$markerPrefix 'approach and cross camp center' --phase cold-approach"
    )
    Write-Host (
        "$markerPrefix 'stationary at camp center' --phase stationary"
    )
    Write-Host (
        "$markerPrefix 'leave and cross again warm' --phase warm-return"
    )
    Write-Host "$markerPrefix 'protocol complete' --phase complete --finish"
}
& $PythonPath @arguments
$captureExitCode = $LASTEXITCODE

$manifestDirectory = Join-Path $outputDirectory 'manifests'
$manifest = @(
    Get-ChildItem -LiteralPath $manifestDirectory -Filter '*.manifest.json' -File -ErrorAction SilentlyContinue
)
$analysisPath = ''
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

if ($exportOutputRoot) {
    if ($manifest.Count -ne 1) {
        throw "Cannot export diagnostic evidence without exactly one sealed manifest"
    }
    if (-not (Test-Path -LiteralPath $exportOutputRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $exportOutputRoot -Force | Out-Null
    }
    $captureName = Split-Path -Leaf $outputDirectory
    $localBundle = Join-Path $OutputRoot "$captureName.evidence.zip"
    $exportedBundle = Join-Path $exportOutputRoot "$captureName.evidence.zip"
    $exportReceipt = Join-Path $exportOutputRoot "$captureName.export.json"
    foreach ($path in @($localBundle, $exportedBundle, $exportReceipt)) {
        if (Test-Path -LiteralPath $path) {
            throw "Refusing to replace diagnostic export output: $path"
        }
    }
    & $PythonPath -u -m shadowbane_lab.cli `
        evidence `
        bundle `
        (Join-Path $outputDirectory 'store') `
        $manifest[0].FullName `
        $localBundle `
        --json
    if ($LASTEXITCODE -ne 0) {
        throw "Diagnostic evidence bundling failed with exit code $LASTEXITCODE"
    }
    Copy-Item -LiteralPath $localBundle -Destination $exportedBundle
    $localBundleFile = Get-Item -LiteralPath $localBundle
    $exportedBundleFile = Get-Item -LiteralPath $exportedBundle
    $localBundleSha256 = (
        Get-FileHash -LiteralPath $localBundle -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    $exportedBundleSha256 = (
        Get-FileHash -LiteralPath $exportedBundle -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if (
        $localBundleFile.Length -ne $exportedBundleFile.Length -or
        $localBundleSha256 -cne $exportedBundleSha256
    ) {
        Remove-Item -LiteralPath $exportedBundle -Force -ErrorAction SilentlyContinue
        throw "Exported diagnostic bundle differs from its verified local source"
    }
    $analysisExport = $null
    $analysisSha256 = $null
    if ($analysisPath) {
        $analysisExport = Join-Path $exportOutputRoot "$captureName.analysis.json"
        if (Test-Path -LiteralPath $analysisExport) {
            throw "Refusing to replace diagnostic analysis export: $analysisExport"
        }
        Copy-Item -LiteralPath $analysisPath -Destination $analysisExport
        $localAnalysisSha256 = (
            Get-FileHash -LiteralPath $analysisPath -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        $analysisSha256 = (
            Get-FileHash -LiteralPath $analysisExport -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        if ($localAnalysisSha256 -cne $analysisSha256) {
            Remove-Item -LiteralPath $analysisExport -Force -ErrorAction SilentlyContinue
            throw "Exported diagnostic analysis differs from its local source"
        }
    }
    $receipt = [ordered]@{
        schema_version = 1
        status = 'verified_export'
        exported_at_utc = [DateTime]::UtcNow.ToString('o')
        capture_name = $captureName
        manifest_id = $manifest[0].BaseName.Replace('.manifest', '')
        bundle_file = Split-Path -Leaf $exportedBundle
        bundle_size_bytes = $exportedBundleFile.Length
        bundle_sha256 = $exportedBundleSha256
        analysis_file = if ($analysisExport) { Split-Path -Leaf $analysisExport } else { $null }
        analysis_sha256 = $analysisSha256
    } | ConvertTo-Json
    $utf8 = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText($exportReceipt, "$receipt`n", $utf8)

    $resolvedStagingRoot = (Resolve-Path -LiteralPath $OutputRoot).Path.TrimEnd('\')
    $resolvedOutputDirectory = (Resolve-Path -LiteralPath $outputDirectory).Path
    $resolvedOutputParent = (Split-Path -Parent $resolvedOutputDirectory).TrimEnd('\')
    $outputAttributes = (Get-Item -LiteralPath $resolvedOutputDirectory).Attributes
    if ($resolvedOutputParent -cne $resolvedStagingRoot) {
        throw "Refusing to clean diagnostic staging outside its exact local root"
    }
    if (($outputAttributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to clean a reparse-point diagnostic staging directory"
    }
    Remove-Item -LiteralPath $resolvedOutputDirectory -Recurse -Force
    Remove-Item -LiteralPath $localBundle -Force
    Write-Host "Diagnostic evidence bundle: $exportedBundle"
    Write-Host "Diagnostic export receipt: $exportReceipt"
}
else {
    Write-Host "Diagnostic evidence: $outputDirectory"
}
exit $captureExitCode
