[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexrepo",
    [string] $DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string] $PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $ClientDirectory = (
        "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane"
    ),
    [string] $ExecutableRelativePath = "sb.exe",
    [string] $FrozenDirectory = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

foreach ($required in @($RepositoryShare, $DiagnosticsShare, $PythonPath, $ClientDirectory)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required baseline input was not found: $required"
    }
}
if (-not $FrozenDirectory) {
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
    $FrozenDirectory = Join-Path `
        (Join-Path $DiagnosticsShare "client-baselines") `
        "wonderbane-$timestamp"
}
if (Test-Path -LiteralPath $FrozenDirectory) {
    throw "Frozen baseline destination already exists: $FrozenDirectory"
}

$revision = (& git -C $RepositoryShare rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $revision) {
    throw "Could not resolve the repository revision from $RepositoryShare"
}
$env:PYTHONPATH = Join-Path $RepositoryShare "src"
& $PythonPath `
    -m shadowbane_lab.client_extension `
    freeze-baseline `
    $ClientDirectory `
    $FrozenDirectory `
    --executable $ExecutableRelativePath `
    --repository-revision $revision `
    --pretty
if ($LASTEXITCODE -ne 0) {
    throw "WonderBane baseline capture failed with exit code $LASTEXITCODE"
}

Write-Output "Frozen WonderBane baseline: $FrozenDirectory"
