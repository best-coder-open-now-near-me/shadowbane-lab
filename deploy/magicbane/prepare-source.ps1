param(
    [Parameter(Mandatory=$true)][string]$SourceRepository,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$revision = '65952a25afe3fc86cb4cf23a5ff375d1b2f854b5'
$base = 'bafb48fe14e5356a64137954cf2d79205835a204'
$head = & git -C $SourceRepository rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $head -ne $revision) { throw 'Check out the exact reviewed server commit first.' }
$tree = & git -C $SourceRepository rev-parse 'HEAD^{tree}'
if ($LASTEXITCODE -ne 0 -or $tree -ne '173a4699d597b8cf0e4bec933b669545839d55ea') { throw 'Server source tree mismatch.' }
$changes = & git -C $SourceRepository status --porcelain
if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Server source checkout must be clean.' }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$bundle = Join-Path (Resolve-Path -LiteralPath $OutputDirectory).Path 'source.bundle'
if (Test-Path -LiteralPath $bundle) { throw 'Build input already exists; inspect it before replacing.' }
& git -C $SourceRepository bundle create $bundle HEAD "^$base"
if ($LASTEXITCODE -ne 0) { throw 'Source bundle creation failed.' }
& git -C $SourceRepository bundle verify $bundle
if ($LASTEXITCODE -ne 0) { throw 'Source bundle verification failed.' }
Write-Output "Prepared exact server source $revision"
