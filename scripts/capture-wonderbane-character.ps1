[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CharacterName,
    [string]$ServerName = "Wonderbane",
    [int]$ProcessId = 0,
    [string]$OutputRoot = "",
    [string]$PythonPath = "",
    [ValidateRange(3, 60)]
    [int]$CaptureDelaySeconds = 8,
    [switch]$NativeOnly
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $repo "captures\character-transfer" }
if ($ProcessId -lt 0) { throw "ProcessId must be positive when specified." }
if (-not $PythonPath) {
    $candidates = @(
        (Join-Path $repo ".venv\Scripts\python.exe"),
        (Join-Path $env:USERPROFILE "shadowbane-lab\.venv\Scripts\python.exe")
    )
    $PythonPath = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
    if (-not $PythonPath) {
        $command = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($command) { $PythonPath = $command.Source }
    }
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python 3.11+ was not found. Pass -PythonPath with the lab Python executable."
}
$oldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repo "src"
    & $PythonPath -c 'import sys; sys.exit(sys.version_info < (3, 11))'
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ is required." }
    if (-not $NativeOnly) {
        & $PythonPath -c 'from PIL import ImageGrab'
        if ($LASTEXITCODE -ne 0) {
            throw "Pillow is required for equipment pictures. Install the project's client dependencies into this Python environment."
        }
    }
    $captureArgs = @(
        "-m", "shadowbane_lab.character_capture.transfer",
        "--character", $CharacterName, "--server", $ServerName,
        "--output-root", $OutputRoot, "--delay", $CaptureDelaySeconds
    )
    if ($ProcessId -gt 0) { $captureArgs += @("--pid", $ProcessId) }
    if ($NativeOnly) { $captureArgs += "--native-only" }
    & $PythonPath @captureArgs
    if ($LASTEXITCODE -ne 0) { throw "Character capture failed (exit $LASTEXITCODE). See the message above." }
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}
