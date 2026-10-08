[CmdletBinding()]
param([string]$PythonExecutable = "python", [switch]$SkipPublish)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = (Get-Command $PythonExecutable -ErrorAction Stop).Source
$dotnet = (Get-Command dotnet.exe -ErrorAction Stop).Source
Push-Location $repository
try {
    & $python scripts/generate-client-patcher-profile.py --output build/client-patcher/profile.json
    if ($LASTEXITCODE -ne 0) { throw "Profile generation failed" }
    foreach ($project in @("ReleaseTool/Patcher.ReleaseTool", "App/ShadowbanePatcher", "Tests/Patcher.Tests")) {
        & $dotnet build "client/patcher/$project.csproj" -c Release --nologo
        if ($LASTEXITCODE -ne 0) { throw "Patcher build failed: $project" }
    }
    $testArguments = @((Join-Path $repository "build/client-patcher/Patcher.Tests/bin/Release/net10.0-windows/Patcher.Tests.dll"),
        (Join-Path $repository "build/client-patcher/Patcher.ReleaseTool/bin/Release/net10.0-windows/Patcher.ReleaseTool.dll"),
        (Join-Path $repository "build/client-patcher/ShadowbanePatcher/bin/Release/net10.0-windows/ShadowbanePatcher.dll"))
    & $dotnet @testArguments
    if ($LASTEXITCODE -ne 0) { throw "Patcher validation failed" }
    & (Join-Path $repository "scripts/build-client-desktop-launcher.ps1") -PythonExecutable $python
    if (-not $SkipPublish) {
        & $dotnet publish client/patcher/App/ShadowbanePatcher.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -o build/client-patcher/publish --nologo
        if ($LASTEXITCODE -ne 0) { throw "Standalone patcher publication failed" }
        Get-Item build/client-patcher/publish/ShadowbanePatcher.exe | Select-Object FullName,Length
        Get-FileHash build/client-patcher/publish/ShadowbanePatcher.exe -Algorithm SHA256
    }
}
finally { Pop-Location }
