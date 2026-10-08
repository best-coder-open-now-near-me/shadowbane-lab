[CmdletBinding()]
param(
    [string]$BuildDirectory = "",
    [string]$PythonExecutable = "python",
    [ValidateSet("Debug", "Release")][string]$Configuration = "Release"
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if (-not $BuildDirectory) { $BuildDirectory = Join-Path $repository "build/client-launcher" }
$cmake = (Get-Command cmake.exe -ErrorAction Stop).Source
$python = (Get-Command $PythonExecutable -ErrorAction Stop).Source
& $cmake -S (Join-Path $repository "native/client_launcher") -B $BuildDirectory `
    -G "Visual Studio 17 2022" -A x64 "-DPython3_EXECUTABLE=$python"
if ($LASTEXITCODE -ne 0) { throw "Launcher configuration failed: $LASTEXITCODE" }
& $cmake --build $BuildDirectory --config $Configuration
if ($LASTEXITCODE -ne 0) { throw "Launcher build failed: $LASTEXITCODE" }
& (Join-Path (Split-Path -Parent $cmake) "ctest.exe") --test-dir $BuildDirectory `
    -C $Configuration --output-on-failure
if ($LASTEXITCODE -ne 0) { throw "Launcher tests failed: $LASTEXITCODE" }
$artifact = Join-Path $BuildDirectory "$Configuration/ShadowbaneLauncher.exe"
[pscustomobject]@{
    Artifact = $artifact
    Sha256 = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    Configuration = $Configuration
    Architecture = "x64 launcher / reviewed x86 game"
}
