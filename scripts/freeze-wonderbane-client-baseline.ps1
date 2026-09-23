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

$gitRepositoryPath = $RepositoryShare.Replace("\", "/").TrimEnd("/")
$gitSafeDirectory = "$gitRepositoryPath/"
if ($gitRepositoryPath.StartsWith("//")) {
    # Git for Windows recommends its runtime-prefix form for UNC safe directories.
    # Keep the exception command-scoped; do not mutate the VM user's global config.
    $gitSafeDirectory = "%(prefix)/$gitRepositoryPath/"
}
$revisionOutput = @(
    & git `
        -c "safe.directory=$gitSafeDirectory" `
        -C $RepositoryShare `
        rev-parse HEAD
)
$gitExitCode = $LASTEXITCODE
if ($gitExitCode -ne 0 -or $revisionOutput.Count -ne 1) {
    throw "Could not resolve the repository revision from $RepositoryShare"
}
$revision = $revisionOutput[0].Trim()
if (-not $revision) {
    throw "Repository revision lookup returned an empty value from $RepositoryShare"
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

$baselineEvidence = Get-Content `
    -LiteralPath (Join-Path $FrozenDirectory "client-baseline.json") `
    -Raw | ConvertFrom-Json
$executableSha256 = [string] $baselineEvidence.executable.sha256
$treeSha256 = [string] $baselineEvidence.tree_sha256
if ($executableSha256.Length -ne 64 -or $treeSha256.Length -ne 64) {
    throw "Frozen baseline evidence did not contain complete SHA-256 identities"
}
$contentBuildId = "wb-{0}-{1}" -f `
    $executableSha256.Substring(0, 8), `
    $treeSha256.Substring(0, 8)

Write-Output "Frozen WonderBane baseline: $FrozenDirectory"
Write-Output "WonderBane content build: $contentBuildId"
