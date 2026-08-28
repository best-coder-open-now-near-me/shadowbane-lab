[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexrepo",
    [string] $DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string] $LocalStateRoot = "$env:LOCALAPPDATA\ShadowbaneLab",
    [ValidateRange(1, 300)]
    [int] $ShareWaitSeconds = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$logRoot = Join-Path $LocalStateRoot "logs"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$bootstrapLog = Join-Path $logRoot "share-bootstrap.log"

function Write-ShareBootstrapLog {
    param([string] $Message)
    Add-Content `
        -LiteralPath $bootstrapLog `
        -Value ("{0:o} {1}" -f (Get-Date), $Message) `
        -Encoding utf8
}

try {
    $runner = Join-Path $RepositoryShare "scripts\start-wonderbane-control-center.ps1"
    $deadline = (Get-Date).AddSeconds($ShareWaitSeconds)
    foreach ($required in @($RepositoryShare, $DiagnosticsShare, $runner)) {
        while (-not (Test-Path -LiteralPath $required)) {
            if ((Get-Date) -ge $deadline) {
                throw "VirtualBox share dependency did not become available: $required"
            }
            Start-Sleep -Milliseconds 500
        }
    }
    Write-ShareBootstrapLog "VirtualBox shares are ready; starting current repository runner."
    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File $runner `
        -RepositoryShare $RepositoryShare `
        -DiagnosticsShare $DiagnosticsShare `
        -ManagerManifest (Join-Path $LocalStateRoot "client-manager.json") `
        -ShareWaitSeconds $ShareWaitSeconds
    exit $LASTEXITCODE
}
catch {
    Write-ShareBootstrapLog "ERROR: $($_.Exception.Message)"
    throw
}
