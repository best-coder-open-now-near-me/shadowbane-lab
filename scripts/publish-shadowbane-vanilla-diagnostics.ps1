[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $OutputDirectory,
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+$')]
    [string] $PackageVersion = '1.0.0',
    [string] $SourceRoot = (Split-Path -Parent $PSScriptRoot),
    [string] $PythonPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$sourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$status = @(& git -C $sourceRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect repository state: $SourceRoot"
}
if ($status.Count -ne 0) {
    throw 'Refusing to publish vanilla diagnostics from a dirty checkout.'
}
$revisionOutput = @(& git -C $sourceRoot rev-parse HEAD)
if ($LASTEXITCODE -ne 0 -or $revisionOutput.Count -ne 1) {
    throw "Could not resolve the source revision: $SourceRoot"
}
$sourceRevision = $revisionOutput[0].Trim().ToLowerInvariant()
$shortRevision = $sourceRevision.Substring(0, 8)
$packageName = "shadowbane-vanilla-diagnostics-$PackageVersion-$shortRevision"
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$outputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$destination = Join-Path $outputDirectory $packageName
if (Test-Path -LiteralPath $destination) {
    throw "Published package already exists: $destination"
}
$staging = Join-Path $outputDirectory (".$packageName.staging-" + [Guid]::NewGuid().ToString('N'))
$packageSource = Join-Path $sourceRoot 'src\shadowbane_vanilla_diagnostics'
$launcherSource = Join-Path $sourceRoot 'scripts\capture-shadowbane-vanilla-diagnostics.ps1'
$runnerSource = Join-Path $sourceRoot 'scripts\run_vanilla_diagnostics.py'
foreach ($required in @($packageSource, $launcherSource, $runnerSource)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Vanilla diagnostics release input was not found: $required"
    }
}

try {
    New-Item -ItemType Directory -Path $staging | Out-Null
    Copy-Item -LiteralPath $launcherSource -Destination $staging
    Copy-Item -LiteralPath $runnerSource -Destination $staging
    Copy-Item -LiteralPath $packageSource -Destination $staging -Recurse
    Get-ChildItem -LiteralPath $staging -Directory -Recurse -Filter '__pycache__' |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $staging -File -Recurse -Filter '*.pyc' |
        Remove-Item -Force
    $inventory = @(
        Get-ChildItem -LiteralPath $staging -File -Recurse |
            Sort-Object FullName |
            ForEach-Object {
                [ordered]@{
                    path = $_.FullName.Substring($staging.Length).TrimStart('\').Replace('\', '/')
                    length = $_.Length
                    sha256 = (
                        Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
                    ).Hash.ToLowerInvariant()
                }
            }
    )
    $manifest = [ordered]@{
        schema_version = 1
        package_id = 'shadowbane-vanilla-diagnostics'
        package_version = $PackageVersion
        source_revision = $sourceRevision
        created_at_utc = [DateTime]::UtcNow.ToString('o')
        required_output_root = '\\VBOXSVR\codexdiag\vanilla-diagnostics'
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
        (Join-Path $staging 'package-manifest.json'),
        $manifestJson,
        [Text.UTF8Encoding]::new($false)
    )

    if (-not $PythonPath) {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($null -eq $pythonCommand) {
            throw 'Python was not found on PATH for package verification.'
        }
        $PythonPath = $pythonCommand.Source
    }
    $runner = Join-Path $staging 'run_vanilla_diagnostics.py'
    & $PythonPath '-E' '-s' '-B' $runner 'verify-package' '--package-root' $staging
    if ($LASTEXITCODE -ne 0) {
        throw "Published package verification failed with exit code $LASTEXITCODE."
    }
    [IO.Directory]::Move($staging, $destination)
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}

Write-Output $destination
