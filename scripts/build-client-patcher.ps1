#Requires -Version 5.1
[CmdletBinding()]
param([string]$OutputDirectory = '')
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repository 'build/client-patcher' }
[void][IO.Directory]::CreateDirectory($OutputDirectory)
$compiler = Join-Path $env:SystemRoot 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$source = Join-Path $repository 'native/client_patcher'
$references = @('/r:System.dll','/r:System.Core.dll','/r:System.Drawing.dll','/r:System.Windows.Forms.dll','/r:System.Web.Extensions.dll','/r:System.IO.Compression.dll','/r:System.IO.Compression.FileSystem.dll')
& $compiler /nologo /target:winexe /platform:x64 /optimize+ /warnaserror+ @references ("/win32manifest:" + (Join-Path $source 'patcher.manifest')) ("/out:" + (Join-Path $OutputDirectory 'ShadowbanePatcher.exe')) (Join-Path $source 'PatcherCore.cs') (Join-Path $source 'PatcherForm.cs')
if ($LASTEXITCODE -ne 0) { throw 'Patcher compilation failed' }
& $compiler /nologo /target:exe /platform:x64 /optimize+ /warnaserror+ @references ("/out:" + (Join-Path $OutputDirectory 'PatcherTests.exe')) (Join-Path $source 'PatcherCore.cs') (Join-Path $source 'PatcherTests.cs')
if ($LASTEXITCODE -ne 0) { throw 'Patcher test compilation failed' }
& (Join-Path $OutputDirectory 'PatcherTests.exe')
if ($LASTEXITCODE -ne 0) { throw 'Patcher tests failed' }
Get-FileHash -LiteralPath (Join-Path $OutputDirectory 'ShadowbanePatcher.exe') -Algorithm SHA256
