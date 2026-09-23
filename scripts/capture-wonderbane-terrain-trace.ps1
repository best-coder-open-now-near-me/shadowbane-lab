[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexrepo",
    [string] $PythonExecutable = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [int] $ProcessId = 0,
    [long] $ProcessCreationFiletimeUtc = 0,
    [ValidateRange(1, 60)] [int] $TimeoutSeconds = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    throw "Guest Python was not found: $PythonExecutable"
}
$terrainSource = Join-Path $RepositoryShare "src"
if (-not (Test-Path -LiteralPath $terrainSource -PathType Container)) {
    throw "Reviewed tracing source was not found: $terrainSource"
}
if ($ProcessId -lt 0 -or $ProcessCreationFiletimeUtc -lt 0) {
    throw "Process identity values cannot be negative"
}
$terrainArguments = @("-m", "shadowbane_lab.diagnostics.terrain_trace", "--timeout", "$TimeoutSeconds")
if ($ProcessId -gt 0) { $terrainArguments += @("--pid", "$ProcessId") }
if ($ProcessCreationFiletimeUtc -gt 0) {
    $terrainArguments += @("--creation-filetime", "$ProcessCreationFiletimeUtc")
}
$terrainPreviousPythonPath = $env:PYTHONPATH
$terrainPreviousBytecode = $env:PYTHONDONTWRITEBYTECODE
try {
    $env:PYTHONPATH = $terrainSource
    $env:PYTHONDONTWRITEBYTECODE = "1"
    & $PythonExecutable @terrainArguments
    $terrainExitCode = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $terrainPreviousPythonPath
    $env:PYTHONDONTWRITEBYTECODE = $terrainPreviousBytecode
}
if ($terrainExitCode -eq 2) {
    Write-Warning "Local evidence was saved with coverage limits; review the reported limitations."
    exit 2
} elseif ($terrainExitCode -ne 0) {
    throw "Terrain capture did not complete successfully (exit $terrainExitCode). No automatic retry."
}
