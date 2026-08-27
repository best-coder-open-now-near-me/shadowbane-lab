[CmdletBinding()]
param(
    [string] $LogDirectory = "\\VBOXSVR\codexdiag"
)

$ErrorActionPreference = "Stop"
$pidPath = Join-Path $LogDirectory "go-listener.pid"
if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
    Write-Output "Shadowbane /go listener has no PID file."
    exit 0
}

$listenerProcessId = 0
$pidText = (Get-Content -LiteralPath $pidPath -Raw).Trim()
if (-not [int]::TryParse($pidText, [ref] $listenerProcessId)) {
    throw "Shadowbane /go listener PID file is invalid: $pidText"
}

$process = Get-CimInstance Win32_Process -Filter "ProcessId = $listenerProcessId"
if ($null -eq $process) {
    Write-Output "Shadowbane /go listener is already stopped (former PID $listenerProcessId)."
    exit 0
}
if ($process.Name -ne "python.exe" -or
    $process.CommandLine -notmatch "shadowbane_lab\.cli\s+client\s+listen-go") {
    throw "PID $listenerProcessId does not belong to the Shadowbane /go listener."
}

Stop-Process -Id $listenerProcessId -Force
Write-Output "Shadowbane /go listener stopped (PID $listenerProcessId)."
