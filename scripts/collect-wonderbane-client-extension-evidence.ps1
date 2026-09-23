[CmdletBinding()]
param(
    [string]$RepositoryShare = "\\VBOXSVR\codexrepo",
    [string]$DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string]$PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string]$ClientDirectory = "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane",
    [string]$ExecutableRelativePath = "sb.exe"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

foreach ($required in @($RepositoryShare, $DiagnosticsShare, $PythonPath, $ClientDirectory)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required extension-evidence input was not found: $required"
    }
}
$runningClient = Get-Process -Name "sb" -ErrorAction SilentlyContinue
if ($runningClient) {
    throw "Close every running sb.exe before freezing client-extension evidence."
}

$env:PYTHONPATH = Join-Path $RepositoryShare "src"
& $PythonPath -c "import capstone; print(capstone.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw (
        "Capstone is required for the read-only entry review. Install the repo's " +
        "client-extension extra in this venv before retrying."
    )
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
$evidenceRoot = Join-Path `
    (Join-Path $DiagnosticsShare "client-extension-evidence") `
    "wonderbane-$timestamp"
if (Test-Path -LiteralPath $evidenceRoot) {
    throw "Extension evidence destination already exists: $evidenceRoot"
}
New-Item -ItemType Directory -Path $evidenceRoot | Out-Null
$baselineDirectory = Join-Path $evidenceRoot "client-baseline"
$freezeScript = Join-Path $RepositoryShare "scripts\freeze-wonderbane-client-baseline.ps1"
& $freezeScript `
    -RepositoryShare $RepositoryShare `
    -DiagnosticsShare $DiagnosticsShare `
    -PythonPath $PythonPath `
    -ClientDirectory $ClientDirectory `
    -ExecutableRelativePath $ExecutableRelativePath `
    -FrozenDirectory $baselineDirectory
if ($LASTEXITCODE -ne 0) {
    throw "WonderBane baseline capture failed with exit code $LASTEXITCODE"
}

$frozenExecutable = Join-Path $baselineDirectory $ExecutableRelativePath
$inspectionPath = Join-Path $evidenceRoot "bootstrap-inspection.json"
& $PythonPath `
    -m shadowbane_lab.client_extension `
    inspect-bootstrap `
    $frozenExecutable `
    --output $inspectionPath `
    --pretty
if ($LASTEXITCODE -ne 0) {
    throw "WonderBane bootstrap inspection failed with exit code $LASTEXITCODE"
}

Write-Output "Frozen baseline: $baselineDirectory"
Write-Output "Bootstrap evidence: $inspectionPath"
Write-Warning "Keep this evidence private because it contains a short executable byte window."
