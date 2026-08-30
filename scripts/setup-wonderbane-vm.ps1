[CmdletBinding()]
param(
    [string]$InstallDirectory,
    [string]$RepositoryUrl = "https://github.com/best-coder-open-now-near-me/shadowbane-lab.git",
    [string]$Branch = "feat/simulator-foundation",
    [switch]$SkipPrerequisiteInstall,
    [switch]$SkipTests,
    [switch]$InspectClient,
    [string]$ClientLauncherPath,
    [ValidateRange(1, 300)]
    [int]$ClientDiscoveryTimeoutSeconds = 90,
    [switch]$UpdateExisting
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Invoke-Native {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($ArgumentList -join ' ')"
    }
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Get-ExecutablePath {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return $null
    }
    return $command.Source
}

function Test-WingetPackageInstalled {
    param(
        [string]$WingetPath,
        [string]$PackageId
    )
    $listOutput = @(& $WingetPath list `
        --id $PackageId `
        --exact `
        --source winget `
        --accept-source-agreements `
        --disable-interactivity 2>&1)
    return $LASTEXITCODE -eq 0 -and ($listOutput -join "`n") -match [regex]::Escape($PackageId)
}

function Install-WingetPackage {
    param(
        [string]$PackageId,
        [string]$DisplayName
    )
    $winget = Get-ExecutablePath "winget.exe"
    if ($null -eq $winget) {
        throw "Windows Package Manager (winget) is required to install $DisplayName. Install Microsoft App Installer, then rerun this script."
    }
    if (Test-WingetPackageInstalled $winget $PackageId) {
        Write-Host "$DisplayName is already installed."
        Refresh-ProcessPath
        return
    }
    Write-Step "Installing $DisplayName"
    & $winget @(
        "install",
        "--id", $PackageId,
        "--exact",
        "--source", "winget",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--silent",
        "--disable-interactivity"
    )
    $installExitCode = $LASTEXITCODE
    if ($installExitCode -ne 0 -and -not (Test-WingetPackageInstalled $winget $PackageId)) {
        throw "Winget failed to install $DisplayName with exit code $installExitCode."
    }
    Refresh-ProcessPath
}

function Get-GitExecutable {
    $candidates = @()
    $commandPath = Get-ExecutablePath "git.exe"
    if (-not [string]::IsNullOrWhiteSpace($commandPath)) {
        $candidates += $commandPath
    }
    foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if (-not [string]::IsNullOrWhiteSpace($root)) {
            $candidates += Join-Path $root "Git\cmd\git.exe"
            $candidates += Join-Path $root "Git\bin\git.exe"
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Git\cmd\git.exe"
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Git\bin\git.exe"
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

function Get-PythonLauncher {
    $py = Get-ExecutablePath "py.exe"
    if ($null -ne $py -and $py -notmatch "\\Microsoft\\WindowsApps\\") {
        foreach ($version in @("3.12", "3.13", "3.11")) {
            & $py "-$version" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return [PSCustomObject]@{ FilePath = $py; Prefix = @("-$version") }
            }
        }
    }

    $knownPythonPaths = @(
        (Get-ExecutablePath "python.exe"),
        (Get-ExecutablePath "python3.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:ProgramFiles "Python312\python.exe")
    )
    foreach ($candidate in $knownPythonPaths) {
        if (
            [string]::IsNullOrWhiteSpace($candidate) -or
            $candidate -match "\\Microsoft\\WindowsApps\\" -or
            -not (Test-Path -LiteralPath $candidate)
        ) {
            continue
        }
        & $candidate -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return [PSCustomObject]@{ FilePath = $candidate; Prefix = @() }
        }
    }
    return $null
}

function Invoke-PythonLauncher {
    param(
        [object]$Launcher,
        [string[]]$ArgumentList
    )
    $combined = @($Launcher.Prefix) + $ArgumentList
    Invoke-Native $Launcher.FilePath $combined
}

if ([string]::IsNullOrWhiteSpace($InstallDirectory)) {
    $candidateCheckout = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    if (Test-Path -LiteralPath (Join-Path $candidateCheckout ".git")) {
        $InstallDirectory = $candidateCheckout
    }
    else {
        $InstallDirectory = Join-Path $env:USERPROFILE "shadowbane-lab"
    }
}
$InstallDirectory = [IO.Path]::GetFullPath($InstallDirectory)

$git = Get-GitExecutable
if ($null -eq $git) {
    if ($SkipPrerequisiteInstall) {
        throw "Git is not installed and -SkipPrerequisiteInstall was supplied."
    }
    Install-WingetPackage "Git.Git" "Git for Windows"
    $git = Get-GitExecutable
    if ($null -eq $git) {
        throw "Git installation completed but git.exe is not available in PATH. Open a new PowerShell window and rerun the script."
    }
}

$python = Get-PythonLauncher
if ($null -eq $python) {
    if ($SkipPrerequisiteInstall) {
        throw "Python 3.11+ is not installed and -SkipPrerequisiteInstall was supplied."
    }
    Install-WingetPackage "Python.Python.3.12" "Python 3.12 from python.org"
    $python = Get-PythonLauncher
    if ($null -eq $python) {
        throw "Python installation completed but a compatible interpreter is not available. Disable Windows App Execution Aliases for python.exe/python3.exe, open a new PowerShell window, and rerun the script."
    }
}

$gitDirectory = Join-Path $InstallDirectory ".git"
if (-not (Test-Path -LiteralPath $gitDirectory)) {
    if (Test-Path -LiteralPath $InstallDirectory) {
        $existingItems = @(Get-ChildItem -LiteralPath $InstallDirectory -Force)
        if ($existingItems.Count -ne 0) {
            throw "Install directory exists and is not an empty Git checkout: $InstallDirectory"
        }
    }
    else {
        $parentDirectory = Split-Path -Parent $InstallDirectory
        New-Item -ItemType Directory -Path $parentDirectory -Force | Out-Null
    }
    Write-Step "Cloning the public repository without authentication"
    Invoke-Native $git @(
        "clone",
        "--branch", $Branch,
        "--single-branch",
        $RepositoryUrl,
        $InstallDirectory
    )
}
elseif ($UpdateExisting) {
    Write-Step "Updating the existing checkout"
    $trackedChanges = & $git -C $InstallDirectory status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect the existing checkout."
    }
    if (-not [string]::IsNullOrWhiteSpace(($trackedChanges -join "`n"))) {
        throw "Tracked changes exist in $InstallDirectory; refusing to switch or update branches."
    }
    Invoke-Native $git @("-C", $InstallDirectory, "fetch", "origin", $Branch)
    Invoke-Native $git @("-C", $InstallDirectory, "switch", $Branch)
    Invoke-Native $git @("-C", $InstallDirectory, "pull", "--ff-only", "origin", $Branch)
}

$currentBranchOutput = & $git -C $InstallDirectory branch --show-current
if ($LASTEXITCODE -ne 0) {
    throw "Unable to determine the current Git branch in $InstallDirectory."
}
$currentBranch = ($currentBranchOutput -join "").Trim()
if ($currentBranch -ne $Branch) {
    throw "Expected branch '$Branch' but checkout is on '$currentBranch'. Rerun with -UpdateExisting after preserving any tracked changes."
}

$venvDirectory = Join-Path $InstallDirectory ".venv"
$venvPython = Join-Path $venvDirectory "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Step "Creating the Python virtual environment"
    Invoke-PythonLauncher $python @("-m", "venv", $venvDirectory)
}

Write-Step "Installing Python, test, and PyAutoGUI dependencies"
Invoke-Native $venvPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Native $venvPython @(
    "-m", "pip", "install", "--editable", "${InstallDirectory}[test,client]"
)

$templateProfile = Join-Path $InstallDirectory "configs\wonderbane.template.json"
$localProfile = Join-Path $InstallDirectory "configs\wonderbane.local.json"
if (-not (Test-Path -LiteralPath $localProfile)) {
    Write-Step "Creating the VM-local, live-locked calibration profile"
    Copy-Item -LiteralPath $templateProfile -Destination $localProfile
}
else {
    Write-Host "Preserving existing local calibration: $localProfile"
}

Write-Step "Validating the local calibration profile"
Invoke-Native $venvPython @(
    "-m", "shadowbane_lab.cli", "client", "validate-profile", $localProfile
)

if (-not $SkipTests) {
    Write-Step "Running static checks and the desktop-safe test suite"
    Push-Location $InstallDirectory
    try {
        Invoke-Native $venvPython @("-m", "ruff", "check", ".")
        Invoke-Native $venvPython @("-m", "unittest", "discover", "-s", "tests")
    }
    finally {
        Pop-Location
    }
}

$discoveredClientDirectory = $null
if ($InspectClient) {
    if ([string]::IsNullOrWhiteSpace($ClientLauncherPath)) {
        $defaultLauncher = Join-Path $env:USERPROFILE "Downloads\WonderbaneClient\Wonderbane\Launch-WonderBane-TextFix.cmd"
        if (Test-Path -LiteralPath $defaultLauncher -PathType Leaf) {
            $ClientLauncherPath = $defaultLauncher
        }
        else {
            throw "-InspectClient requires -ClientLauncherPath. The default WonderBane text-fix launcher was not found at: $defaultLauncher"
        }
    }
    if (-not (Test-Path -LiteralPath $ClientLauncherPath -PathType Leaf)) {
        throw "Client launcher does not exist: $ClientLauncherPath"
    }
    $resolvedLauncher = (Resolve-Path -LiteralPath $ClientLauncherPath).Path
    $launcherExtension = [IO.Path]::GetExtension($resolvedLauncher).ToLowerInvariant()
    if ($launcherExtension -notin @(".cmd", ".bat", ".exe")) {
        throw "Client launcher must be a .cmd, .bat, or .exe file: $resolvedLauncher"
    }
    $discoveredClientDirectory = Split-Path -Parent $resolvedLauncher

    Write-Step "Discovering the visible WonderBane client without changing focus"
    $null = & $venvPython -m shadowbane_lab.cli client discover `
        --process-directory $discoveredClientDirectory `
        --wait-seconds 0 `
        --json 2>$null
    $clientAlreadyRunning = $LASTEXITCODE -eq 0
    if (-not $clientAlreadyRunning) {
        Write-Host "Launching WonderBane through: $resolvedLauncher"
        if ($launcherExtension -in @(".cmd", ".bat")) {
            Start-Process `
                -FilePath $env:ComSpec `
                -ArgumentList @("/d", "/c", "`"$resolvedLauncher`"") `
                -WorkingDirectory $discoveredClientDirectory `
                -WindowStyle Hidden
        }
        else {
            Start-Process `
                -FilePath $resolvedLauncher `
                -WorkingDirectory $discoveredClientDirectory
        }
    }
    else {
        Write-Host "A visible WonderBane client is already running; leaving it untouched."
    }

    $discoveryWaitSeconds = if ($clientAlreadyRunning) {
        0
    }
    else {
        $ClientDiscoveryTimeoutSeconds
    }
    & $venvPython -m shadowbane_lab.cli client discover `
        --process-directory $discoveredClientDirectory `
        --wait-seconds $discoveryWaitSeconds
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Client discovery did not find one unambiguous visible WonderBane window. Setup remains valid; close duplicate game or patcher windows and rerun the discovery command shown below."
    }
}

Write-Host "`nWonderBane VM setup is complete." -ForegroundColor Green
Write-Host "Repository: $InstallDirectory"
Write-Host "Calibration: $localProfile"
Write-Host "Live input remains disabled until calibration is reviewed."
Write-Host "`nNext commands:"
Write-Host "  cd `"$InstallDirectory`""
Write-Host "  .\.venv\Scripts\python.exe -m shadowbane_lab.cli client inspect"
if ($null -ne $discoveredClientDirectory) {
    Write-Host "  .\.venv\Scripts\python.exe -m shadowbane_lab.cli client discover --process-directory `"$discoveredClientDirectory`""
}
Write-Host "  notepad .\configs\wonderbane.local.json"
