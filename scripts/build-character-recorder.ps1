[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PythonPath,
    [Parameter(Mandatory)][string]$OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path -Parent $PSScriptRoot
$status = @(& git -C $sourceRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $status.Count) { throw 'Build from a clean, committed source checkout.' }
$revision = (& git -C $sourceRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not read source revision.' }
$toolVersion = (& $PythonPath -m PyInstaller --version)
if ($LASTEXITCODE -ne 0 -or $toolVersion.Trim() -ne '6.22.2') {
    throw 'The isolated build environment must provide PyInstaller 6.22.2.'
}
$output = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $output -Force | Out-Null
$name = 'ShadowbaneRecorder-' + $revision.Substring(0,12)
$buildRoot = Join-Path $output ('.build-' + $revision.Substring(0,12))
$package = Join-Path $output $name
$zip = Join-Path $output ($name + '.zip')
foreach ($path in @($buildRoot, $package, $zip)) {
    if (Test-Path -LiteralPath $path) { throw "Output already exists: $path" }
}
New-Item -ItemType Directory -Path $buildRoot | Out-Null
$arguments = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
    '--name', $name, '--paths', (Join-Path $sourceRoot 'src'),
    '--distpath', $output, '--workpath', (Join-Path $buildRoot 'work'),
    '--specpath', $buildRoot,
    '--add-data', ((Join-Path $sourceRoot 'src/shadowbane_lab/client_observation/data') +
                   ';shadowbane_lab/client_observation/data'),
    '--add-data', ((Join-Path $sourceRoot 'src/shadowbane_lab/character_capture/dictation.ps1') +
                   ';shadowbane_lab/character_capture'),
    (Join-Path $sourceRoot 'scripts/run_character_recorder.py')
)
& $PythonPath @arguments
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed; inspect the retained build diagnostics.' }
Copy-Item -LiteralPath (Join-Path $sourceRoot 'docs/character-recorder.txt') -Destination $package
$metadata = [ordered]@{
    format = 'shadowbane.tester-recorder-package'
    version = '1.0.0'
    source_revision = $revision
    built_at_utc = [DateTime]::UtcNow.ToString('o')
    pyinstaller = $toolVersion.Trim()
}
$metadata | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $package 'build-info.json')
$executable = Join-Path $package ($name + '.exe')
$selfTest = Join-Path $buildRoot 'self-test.json'
$process = Start-Process -FilePath $executable -ArgumentList @('--self-test', ('"' + $selfTest + '"')) -WindowStyle Hidden -PassThru -Wait
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $selfTest)) {
    throw 'Packaged recorder self-test failed; package was not archived.'
}
$result = Get-Content -Raw -LiteralPath $selfTest | ConvertFrom-Json
if (-not $result.passed) { throw 'Packaged recorder self-test did not pass.' }
$inventory = @(Get-ChildItem -LiteralPath $package -Recurse -File | ForEach-Object {
    [ordered]@{
        path = $_.FullName.Substring($package.Length + 1).Replace('\','/')
        bytes = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
})
[ordered]@{ source_revision=$revision; files=$inventory } | ConvertTo-Json -Depth 5 |
    Set-Content -Encoding utf8 (Join-Path $package 'package-files.json')
Compress-Archive -LiteralPath $package -DestinationPath $zip -CompressionLevel Optimal
$digest = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
("$digest  " + [IO.Path]::GetFileName($zip)) | Set-Content -Encoding ascii ($zip + '.sha256')
Write-Output "Package: $zip"
Write-Output "SHA256: $digest"
Write-Output "Self-test: $selfTest"
