[CmdletBinding()]
param([string]$PythonPath = '', [string]$OutputRoot = '')
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path -Parent $PSScriptRoot
if (-not $PythonPath) {
    $localPython = Join-Path $sourceRoot '.venv/Scripts/python.exe'
    $PythonPath = if (Test-Path -LiteralPath $localPython) { $localPython } else { 'python.exe' }
}
$previous = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $sourceRoot 'src'
    $arguments = @('-m','shadowbane_lab.character_capture.dashboard')
    if ($OutputRoot) { $arguments += @('--output-root', $OutputRoot) }
    & $PythonPath @arguments
    if ($LASTEXITCODE -ne 0) { throw "Recorder exited with code $LASTEXITCODE." }
} finally { $env:PYTHONPATH = $previous }
