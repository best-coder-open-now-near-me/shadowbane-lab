[CmdletBinding(DefaultParameterSetName = 'Capture')]
param(
    [Parameter(ParameterSetName = 'Capture')]
    [Parameter(ParameterSetName = 'Preflight')]
    [ValidateRange(0, 2147483647)]
    [int] $ProcessId = 0,
    [Parameter(ParameterSetName = 'Capture')]
    [Parameter(ParameterSetName = 'Preflight')]
    [string] $ClientExecutable = (
        "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\sb.exe"
    ),
    [Parameter(ParameterSetName = 'Capture')]
    [ValidateRange(1.0, 3600.0)]
    [double] $DurationSeconds = 600.0,
    [Parameter(ParameterSetName = 'Capture')]
    [ValidateRange(0.1, 0.2)]
    [double] $IntervalSeconds = 0.125,
    [Parameter(Mandatory, ParameterSetName = 'Preflight')]
    [switch] $PreflightOnly,

    [Parameter(Mandatory, ParameterSetName = 'Marker')]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')]
    [string] $Marker,
    [Parameter(ParameterSetName = 'Marker')]
    [ValidateLength(0, 256)]
    [string] $Note = '',
    [string] $PythonPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$packageRoot = $PSScriptRoot
$manifestPath = Join-Path $packageRoot 'package-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Vanilla diagnostics package manifest was not found: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne 1 -or
    $manifest.package_id -cne 'shadowbane-vanilla-diagnostics') {
    throw 'Vanilla diagnostics package identity is invalid.'
}
$outputRoot = [string] $manifest.required_output_root
if (-not $outputRoot.StartsWith('\\VBOXSVR\codexdiag\vanilla-diagnostics')) {
    throw "Package output is outside the isolated codexdiag boundary: $outputRoot"
}
$expectedPackageParent = [IO.Path]::GetFullPath((Join-Path $outputRoot 'packages'))
$resolvedPackageRoot = [IO.Path]::GetFullPath($packageRoot)
$packagePrefix = $expectedPackageParent.TrimEnd('\') + '\'
if (-not $resolvedPackageRoot.StartsWith(
    $packagePrefix,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw "Run the published package from $packagePrefix, not $resolvedPackageRoot"
}

$manifestPaths = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
foreach ($file in @($manifest.files)) {
    $relative = [string] $file.path
    if ([string]::IsNullOrWhiteSpace($relative) -or
        [IO.Path]::IsPathRooted($relative) -or
        $relative.Contains('..')) {
        throw "Package manifest contains an unsafe path: $relative"
    }
    if (-not $manifestPaths.Add($relative.Replace('/', '\'))) {
        throw "Package manifest contains a duplicate path: $relative"
    }
    $candidate = Join-Path $packageRoot $relative
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Package file is missing: $relative"
    }
    $item = Get-Item -LiteralPath $candidate
    if ($item.Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) {
        throw "Package file must not be a reparse point: $relative"
    }
    if ($item.Length -ne [int64] $file.length) {
        throw "Package file length mismatch: $relative"
    }
    $actualHash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
    if ($actualHash -cne ([string] $file.sha256).ToUpperInvariant()) {
        throw "Package file hash mismatch: $relative"
    }
}
foreach ($candidate in @(
    Get-ChildItem -LiteralPath $packageRoot -File -Recurse |
        Where-Object { $_.Extension -in @('.dll', '.exe', '.pyd', '.ps1', '.py', '.pyw') }
)) {
    $relative = $candidate.FullName.Substring($resolvedPackageRoot.Length).TrimStart('\')
    if (-not $manifestPaths.Contains($relative)) {
        throw "Package contains unmanifested executable code: $relative"
    }
}

if (-not $PythonPath) {
    $workspacePython = Join-Path $env:USERPROFILE 'shadowbane-lab\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $workspacePython -PathType Leaf) {
        $PythonPath = $workspacePython
    }
    else {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($null -eq $pythonCommand) {
            throw 'Python was not found in the workspace environment or on PATH.'
        }
        $PythonPath = $pythonCommand.Source
    }
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python was not found: $PythonPath"
}
$runner = Join-Path $packageRoot 'run_vanilla_diagnostics.py'

if ($PSCmdlet.ParameterSetName -eq 'Marker') {
    & $PythonPath @(
        '-E', '-s', '-B', $runner, 'mark',
        '--package-root', $packageRoot,
        '--output-root', $outputRoot,
        '--label', $Marker,
        '--note', $Note
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Observation marker failed with exit code $LASTEXITCODE."
    }
    return
}

if (-not (Test-Path -LiteralPath $ClientExecutable -PathType Leaf)) {
    throw "Vanilla Shadowbane executable was not found: $ClientExecutable"
}
$resolvedClient = (Resolve-Path -LiteralPath $ClientExecutable).Path
if ([IO.Path]::GetFileName($resolvedClient) -ine 'sb.exe') {
    throw "The selected client executable is not sb.exe: $resolvedClient"
}
$matchingProcesses = @(
    Get-Process -Name 'sb' -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Path -and
            [string]::Equals(
                (Resolve-Path -LiteralPath $_.Path).Path,
                $resolvedClient,
                [StringComparison]::OrdinalIgnoreCase
            )
        }
)
if ($ProcessId -gt 0) {
    $matchingProcesses = @($matchingProcesses | Where-Object Id -eq $ProcessId)
}
if ($matchingProcesses.Count -ne 1) {
    $candidateIds = ($matchingProcesses.Id | Sort-Object) -join ', '
    throw (
        "Expected exactly one live process for $resolvedClient, found " +
        "$($matchingProcesses.Count). Candidate PID(s): $candidateIds"
    )
}
$game = $matchingProcesses[0]
if ($PSCmdlet.ParameterSetName -eq 'Preflight') {
    Write-Host "Preflighting exact vanilla sb.exe PID $($game.Id) without starting capture."
    Write-Host "No extension telemetry will be loaded or read."
    Write-Host "Evidence boundary: $outputRoot"
    & $PythonPath @(
        '-E', '-s', '-B', $runner, 'preflight',
        '--package-root', $packageRoot,
        '--output-root', $outputRoot,
        '--pid', $game.Id,
        '--client-executable', $resolvedClient
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Vanilla diagnostics preflight failed with exit code $LASTEXITCODE."
    }
    Write-Host 'Preflight accepted. No timed capture was started.'
    return
}


Write-Host "Capturing OS-only vanilla diagnostics for exact sb.exe PID $($game.Id)."
Write-Host "No extension telemetry will be loaded or read."
Write-Host "Evidence boundary: $outputRoot"
& $PythonPath @(
    '-E', '-s', '-B', $runner, 'capture',
    '--package-root', $packageRoot,
    '--output-root', $outputRoot,
    '--pid', $game.Id,
    '--client-executable', $resolvedClient,
    '--duration', $DurationSeconds,
    '--interval', $IntervalSeconds
)
if ($LASTEXITCODE -ne 0) {
    throw "Vanilla diagnostics capture failed with exit code $LASTEXITCODE."
}
