[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$BuildDirectory = "",
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$RunProbe
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $RepositoryRoot) {
    $RepositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
$sourceDirectory = Join-Path $RepositoryRoot "native\wonderbane_extension"
if (-not $BuildDirectory) {
    $BuildDirectory = Join-Path $RepositoryRoot "build\wonderbane-client-extension"
}
if (-not (Test-Path -LiteralPath (Join-Path $sourceDirectory "CMakeLists.txt") -PathType Leaf)) {
    throw "WonderBane extension source was not found: $sourceDirectory"
}

$cmake = (Get-Command cmake.exe -ErrorAction Stop).Source
& $cmake -G "Visual Studio 17 2022" -S $sourceDirectory -B $BuildDirectory -A Win32
if ($LASTEXITCODE -ne 0) {
    throw "CMake configuration failed with exit code $LASTEXITCODE"
}
& $cmake --build $BuildDirectory --config $Configuration --clean-first
if ($LASTEXITCODE -ne 0) {
    throw "WonderBane extension build failed with exit code $LASTEXITCODE"
}

$artifact = Join-Path $BuildDirectory "$Configuration\wonderbane-extension.dll"
if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
    throw "The expected extension artifact was not produced: $artifact"
}
if ($RunProbe) {
    $ctest = Join-Path (Split-Path -Parent $cmake) "ctest.exe"
    & $ctest --test-dir $BuildDirectory -C $Configuration --output-on-failure
    if ($LASTEXITCODE -ne 0) {
        throw "WonderBane extension probe failed with exit code $LASTEXITCODE"
    }
}
$hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
[pscustomobject]@{
    Artifact = $artifact
    Configuration = $Configuration
    Machine = "x86"
    Sha256 = $hash
}
