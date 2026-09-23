[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+$')]
    [string] $Version,
    [Parameter(Mandatory)]
    [string] $OutputDirectory,
    [string] $SourceRoot = (Split-Path -Parent $PSScriptRoot),
    [string] $PythonPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-InventoryEntry {
    param(
        [Parameter(Mandatory)]
        [string] $Root,
        [Parameter(Mandatory)]
        [System.IO.FileInfo] $File
    )

    return [ordered]@{
        path = $File.FullName.Substring($Root.Length).TrimStart('\').Replace('\', '/')
        length = $File.Length
        sha256 = (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$sourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$status = @(& git -C $sourceRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect repository state: $sourceRoot"
}
if ($status.Count -ne 0) {
    throw 'Refusing to build portable vanilla diagnostics from a dirty checkout.'
}
$revisionOutput = @(& git -C $sourceRoot rev-parse HEAD)
if ($LASTEXITCODE -ne 0 -or $revisionOutput.Count -ne 1) {
    throw "Could not resolve the source revision: $sourceRoot"
}
$sourceRevision = $revisionOutput[0].Trim().ToLowerInvariant()

if (-not $PythonPath) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw 'Python was not found on PATH for the portable build.'
    }
    $PythonPath = $pythonCommand.Source
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$pythonMachine = @(& $PythonPath -c 'import platform; print(platform.machine())')
if ($LASTEXITCODE -ne 0 -or $pythonMachine.Count -ne 1 -or $pythonMachine[0] -ne 'AMD64') {
    throw 'The portable Windows release must be built with 64-bit AMD64 Python.'
}
$pyInstallerVersion = @(& $PythonPath -m PyInstaller --version)
if ($LASTEXITCODE -ne 0 -or $pyInstallerVersion.Count -ne 1) {
    throw 'PyInstaller is not available in the selected Python environment.'
}
if ($pyInstallerVersion[0].Trim() -ne '6.22.2') {
    throw "Expected PyInstaller 6.22.2, found $($pyInstallerVersion[0].Trim())."
}

$entryPoint = Join-Path $sourceRoot 'scripts\run_vanilla_diagnostics_app.py'
$locationEntryPoint = Join-Path $sourceRoot 'scripts\run_shadowbane_location_lookup.py'
$readmeSource = Join-Path $sourceRoot 'docs\portable-vanilla-diagnostics.txt'
$druidSource = Join-Path $sourceRoot 'utilities\druid-aoe'
$locationUtilitySource = Join-Path $sourceRoot 'utilities\location-lookup'
$locationOverridesSource = Join-Path $sourceRoot 'configs\wonderbane-named-destinations.json'
$requiredFiles = @($entryPoint, $locationEntryPoint, $readmeSource, $locationOverridesSource)
foreach ($required in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Portable build input was not found: $required"
    }
}
foreach ($required in @($druidSource, $locationUtilitySource)) {
    if (-not (Test-Path -LiteralPath $required -PathType Container)) {
        throw "Portable utility source was not found: $required"
    }
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$outputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$packageName = "ShadowbaneVanillaDiagnostics-$Version-win-x64"
$archiveDestination = Join-Path $outputDirectory "$packageName.zip"
$checksumDestination = "$archiveDestination.sha256"
foreach ($destination in @($archiveDestination, $checksumDestination)) {
    if (Test-Path -LiteralPath $destination) {
        throw "Portable release output already exists: $destination"
    }
}

$buildRoot = Join-Path $outputDirectory ('.portable-build-' + [Guid]::NewGuid().ToString('N'))
$packageRoot = Join-Path $buildRoot $packageName
$distRoot = Join-Path $buildRoot 'pyinstaller-dist'
$workRoot = Join-Path $buildRoot 'pyinstaller-work'
$specRoot = Join-Path $buildRoot 'pyinstaller-spec'
$diagnosticsSelfTestResult = Join-Path $buildRoot 'diagnostics-self-test.json'
$locationSelfTestResult = Join-Path $buildRoot 'location-self-test.json'
$archiveStaging = Join-Path $buildRoot "$packageName.zip"
$checksumStaging = "$archiveStaging.sha256"

try {
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    & $PythonPath -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name 'ShadowbaneVanillaDiagnostics' `
        --paths (Join-Path $sourceRoot 'src') `
        --distpath $distRoot `
        --workpath $workRoot `
        --specpath $specRoot `
        $entryPoint
    if ($LASTEXITCODE -ne 0) {
        throw "Diagnostics PyInstaller build failed with exit code $LASTEXITCODE."
    }

    & $PythonPath -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --console `
        --name 'ShadowbaneLocationLookup' `
        --paths (Join-Path $sourceRoot 'src') `
        --distpath $distRoot `
        --workpath $workRoot `
        --specpath $specRoot `
        $locationEntryPoint
    if ($LASTEXITCODE -ne 0) {
        throw "Location lookup PyInstaller build failed with exit code $LASTEXITCODE."
    }

    $diagnosticsExecutableSource = Join-Path $distRoot 'ShadowbaneVanillaDiagnostics.exe'
    $locationExecutableSource = Join-Path $distRoot 'ShadowbaneLocationLookup.exe'
    foreach ($expected in @($diagnosticsExecutableSource, $locationExecutableSource)) {
        if (-not (Test-Path -LiteralPath $expected -PathType Leaf)) {
            throw "PyInstaller did not produce the expected executable: $expected"
        }
    }
    Copy-Item -LiteralPath $diagnosticsExecutableSource -Destination $packageRoot
    Copy-Item -LiteralPath $locationExecutableSource -Destination $packageRoot
    Copy-Item -LiteralPath $readmeSource -Destination (Join-Path $packageRoot 'README.txt')
    Copy-Item -LiteralPath $druidSource -Destination (Join-Path $packageRoot 'Druid AoE Macro') -Recurse
    $locationData = Join-Path $packageRoot 'Location Data'
    New-Item -ItemType Directory -Path $locationData | Out-Null
    Copy-Item -LiteralPath $locationUtilitySource -Destination (Join-Path $packageRoot 'Location Lookup') -Recurse
    Copy-Item -LiteralPath $locationOverridesSource -Destination $locationData

    $inventory = @(
        Get-ChildItem -LiteralPath $packageRoot -File -Recurse |
            Sort-Object FullName |
            ForEach-Object { Get-InventoryEntry -Root $packageRoot -File $_ }
    )
    $manifest = [ordered]@{
        schema_version = 1
        package_id = 'shadowbane-vanilla-diagnostics'
        package_version = $Version
        source_revision = $sourceRevision
        created_at_utc = [DateTime]::UtcNow.ToString('o')
        required_output_root = '{PACKAGE_ROOT}\evidence'
        allowed_executable_sha256 = @(
            '55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc'
            'e358237c458ddfe2fc7a86e478f165a8fd067655ab1a8ada5731f790c6995d96'
        )
        files = $inventory
        channels = @(
            'exact-process-identity'
            'process-cpu-memory-io'
            'window-state'
            'input-timing-no-content'
            'visible-window-surface-fingerprint-no-pixels'
            'dwm-frame-presentation-proxy'
            'process-network-endpoints-no-payload'
            'operator-markers'
        )
    }
    $manifestJson = ($manifest | ConvertTo-Json -Depth 8) + "`n"
    [IO.File]::WriteAllText(
        (Join-Path $packageRoot 'package-manifest.json'),
        $manifestJson,
        [Text.UTF8Encoding]::new($false)
    )

    $diagnosticsSelfTestArguments = @(
        '--self-test'
        '--self-test-result'
        ('"{0}"' -f $diagnosticsSelfTestResult)
    )
    $diagnosticsSelfTestProcess = Start-Process `
        -FilePath (Join-Path $packageRoot 'ShadowbaneVanillaDiagnostics.exe') `
        -ArgumentList $diagnosticsSelfTestArguments `
        -Wait `
        -PassThru
    if ($diagnosticsSelfTestProcess.ExitCode -ne 0) {
        throw "Packaged diagnostics self-test failed: $($diagnosticsSelfTestProcess.ExitCode)."
    }
    $diagnosticsSelfTest = Get-Content -LiteralPath $diagnosticsSelfTestResult -Raw | ConvertFrom-Json
    if ($diagnosticsSelfTest.ok -ne $true) {
        throw "Packaged diagnostics self-test did not report success: $diagnosticsSelfTestResult"
    }

    $locationSelfTestArguments = @(
        '--self-test'
        '--self-test-result'
        ('"{0}"' -f $locationSelfTestResult)
    )
    $locationSelfTestProcess = Start-Process `
        -FilePath (Join-Path $packageRoot 'ShadowbaneLocationLookup.exe') `
        -ArgumentList $locationSelfTestArguments `
        -Wait `
        -PassThru
    if ($locationSelfTestProcess.ExitCode -ne 0) {
        throw "Packaged location self-test failed: $($locationSelfTestProcess.ExitCode)."
    }
    $locationSelfTest = Get-Content -LiteralPath $locationSelfTestResult -Raw | ConvertFrom-Json
    if ($locationSelfTest.ok -ne $true) {
        throw "Packaged location self-test did not report success: $locationSelfTestResult"
    }

    Compress-Archive `
        -LiteralPath $packageRoot `
        -DestinationPath $archiveStaging `
        -CompressionLevel Optimal
    $archiveHash = (Get-FileHash -LiteralPath $archiveStaging -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText(
        $checksumStaging,
        "$archiveHash  $packageName.zip`n",
        [Text.Encoding]::ASCII
    )
    Move-Item -LiteralPath $archiveStaging -Destination $archiveDestination
    Move-Item -LiteralPath $checksumStaging -Destination $checksumDestination
}
finally {
    if (Test-Path -LiteralPath $buildRoot) {
        Remove-Item -LiteralPath $buildRoot -Recurse -Force
    }
}

[ordered]@{
    archive = $archiveDestination
    checksum = $checksumDestination
    package_version = $Version
    source_revision = $sourceRevision
} | ConvertTo-Json
