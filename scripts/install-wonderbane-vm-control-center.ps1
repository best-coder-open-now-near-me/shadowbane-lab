[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexrepo",
    [string] $DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string] $GameDirectory = "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane",
    [string] $PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $NodeId = "wonderbane-vm",
    [ValidateRange(1, 32)]
    [int] $ClientCount = 1,
    [ValidateRange(320, 16384)]
    [int] $DisplayWidth = 1920,
    [ValidateRange(240, 16384)]
    [int] $DisplayHeight = 955,
    [string] $LocalStateRoot = "$env:LOCALAPPDATA\ShadowbaneLab",
    [switch] $NoStartupShortcut,
    [switch] $StartNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$gameExecutable = Join-Path $GameDirectory "sb.exe"
$sourceBootstrap = Join-Path $RepositoryShare "scripts\bootstrap-wonderbane-control-center.ps1"
$sourceRunner = Join-Path $RepositoryShare "scripts\start-wonderbane-control-center.ps1"
$managerSource = Join-Path $RepositoryShare "src"
foreach ($required in @(
    @{ Path = $RepositoryShare; Description = "repository share" },
    @{ Path = $DiagnosticsShare; Description = "diagnostics share" },
    @{ Path = $sourceBootstrap; Description = "control-center share bootstrap" },
    @{ Path = $sourceRunner; Description = "control-center runner" },
    @{ Path = $managerSource; Description = "manager source tree" },
    @{ Path = $PythonPath; Description = "Shadowbane Lab Python" },
    @{ Path = $gameExecutable; Description = "WonderBane executable" }
)) {
    if (-not (Test-Path -LiteralPath $required.Path)) {
        throw "$($required.Description) was not found: $($required.Path)"
    }
}
if ($NodeId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
    throw "NodeId must contain only letters, digits, '.', '_', or '-'."
}

New-Item -ItemType Directory -Path $LocalStateRoot -Force | Out-Null
$localRunner = Join-Path $LocalStateRoot "start-wonderbane-control-center.ps1"
$manifestPath = Join-Path $LocalStateRoot "client-manager.json"
Copy-Item -LiteralPath $sourceBootstrap -Destination $localRunner -Force

$manifestAlreadyExists = Test-Path -LiteralPath $manifestPath -PathType Leaf
if (-not $manifestAlreadyExists) {
    $manifest = [ordered]@{
        schema_version = 1
        node_id = $NodeId
        clients = @(
            [ordered]@{
                client_id = "client-01"
                launch = [ordered]@{
                    executable = $gameExecutable
                    arguments = @()
                    working_directory = $GameDirectory
                    environment = [ordered]@{
                        LIBGL_ALWAYS_SOFTWARE = "true"
                        GALLIUM_DRIVER = "llvmpipe"
                        MESA_EXTENSION_MAX_YEAR = "2001"
                        MESA_GL_VERSION_OVERRIDE = $null
                        MESA_GLSL_VERSION_OVERRIDE = $null
                    }
                }
                expected_process_directory = $GameDirectory
                expected_executable_names = @("sb.exe")
                window_tile = [ordered]@{
                    left = 0
                    top = 0
                    width = $DisplayWidth
                    height = $DisplayHeight
                }
            }
        )
    }
    $manifestJson = $manifest | ConvertTo-Json -Depth 8
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($manifestPath, "$manifestJson`r`n", $utf8WithoutBom)
}

$env:PYTHONPATH = $managerSource
if ((-not $manifestAlreadyExists -and $ClientCount -gt 1) -or (
    $manifestAlreadyExists -and $PSBoundParameters.ContainsKey("ClientCount")
)) {
    & $PythonPath `
        -m shadowbane_lab.cli `
        manager configure-slots `
        $manifestPath `
        --count $ClientCount `
        --display-width $DisplayWidth `
        --display-height $DisplayHeight `
        --apply `
        --json
    if ($LASTEXITCODE -ne 0) {
        throw "The WonderBane manager slot configuration failed."
    }
}
elseif ($manifestAlreadyExists) {
    Write-Output "Preserved existing manager manifest and client slot count: $manifestPath"
}
& $PythonPath -m shadowbane_lab.cli manager preflight $manifestPath --json
if ($LASTEXITCODE -ne 0) {
    throw "The generated WonderBane manager manifest failed preflight."
}

$powershellPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcutArguments = (
    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden " +
    "-File `"$localRunner`" " +
    "-RepositoryShare `"$RepositoryShare`" " +
    "-DiagnosticsShare `"$DiagnosticsShare`" " +
    "-LocalStateRoot `"$LocalStateRoot`""
)
$shell = New-Object -ComObject WScript.Shell
$desktopShortcutPath = Join-Path `
    ([Environment]::GetFolderPath("Desktop")) `
    "WonderBane Control Center.lnk"
$desktopShortcut = $shell.CreateShortcut($desktopShortcutPath)
$desktopShortcut.TargetPath = $powershellPath
$desktopShortcut.Arguments = $shortcutArguments
$desktopShortcut.WorkingDirectory = $LocalStateRoot
$desktopShortcut.IconLocation = "$gameExecutable,0"
$desktopShortcut.WindowStyle = 7
$desktopShortcut.Description = "Start the local WonderBane manager and command listener"
$desktopShortcut.Save()

$startupShortcutPath = Join-Path `
    ([Environment]::GetFolderPath("Startup")) `
    "WonderBane Control Center.lnk"
if ($NoStartupShortcut) {
    if (Test-Path -LiteralPath $startupShortcutPath) {
        Remove-Item -LiteralPath $startupShortcutPath -Force
    }
}
else {
    $startupShortcut = $shell.CreateShortcut($startupShortcutPath)
    $startupShortcut.TargetPath = $powershellPath
    $startupShortcut.Arguments = $shortcutArguments
    $startupShortcut.WorkingDirectory = $LocalStateRoot
    $startupShortcut.IconLocation = "$gameExecutable,0"
    $startupShortcut.WindowStyle = 7
    $startupShortcut.Description = "Start WonderBane controls after Windows logon"
    $startupShortcut.Save()
}

Write-Output "WonderBane control-center bootstrap installed."
Write-Output "Manager manifest: $manifestPath"
Write-Output "Desktop shortcut: $desktopShortcutPath"
if (-not $NoStartupShortcut) {
    Write-Output "Logon shortcut: $startupShortcutPath"
}
if ($StartNow) {
    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File $localRunner `
        -RepositoryShare $RepositoryShare `
        -DiagnosticsShare $DiagnosticsShare `
        -LocalStateRoot $LocalStateRoot
    exit $LASTEXITCODE
}
