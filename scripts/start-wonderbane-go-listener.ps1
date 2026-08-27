[CmdletBinding()]
param(
    [string] $RepositoryRoot = "\\VBOXSVR\codexrepo",
    [string] $PythonPath = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $ClientProfile = "\\VBOXSVR\codexdiag\wonderbane-travel.local.json",
    [string] $DestinationState = "\\VBOXSVR\codexdiag\bounded-route-state.json",
    [string] $WorldDef = "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\Config\WorldDef.cfg",
    [string] $LogDirectory = "\\VBOXSVR\codexdiag"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable was not found: $PythonPath"
}
if (-not (Test-Path -LiteralPath $RepositoryRoot -PathType Container)) {
    throw "Repository share was not found: $RepositoryRoot"
}
if (-not (Test-Path -LiteralPath $ClientProfile -PathType Leaf)) {
    throw "Live travel profile was not found: $ClientProfile"
}
if (-not (Test-Path -LiteralPath $WorldDef -PathType Leaf)) {
    throw "WorldDef was not found: $WorldDef"
}
if (-not (Test-Path -LiteralPath $LogDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
}

$existing = @(
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object {
            $_.CommandLine -match "shadowbane_lab\.cli\s+client\s+listen-go"
        }
)
if ($existing.Count -gt 0) {
    $ids = ($existing.ProcessId | Sort-Object) -join ", "
    Write-Output "Shadowbane /go listener already running (PID $ids)."
    exit 0
}

$standardOutput = Join-Path $LogDirectory "go-listener.stdout.jsonl"
$standardError = Join-Path $LogDirectory "go-listener.stderr.log"
$env:PYTHONPATH = Join-Path $RepositoryRoot "src"
$arguments = @(
    "-u",
    "-m",
    "shadowbane_lab.cli",
    "client",
    "listen-go",
    "--destination-state", $DestinationState,
    "--client-profile", $ClientProfile,
    "--world-def", $WorldDef,
    "--max-seconds", "300",
    "--wait-for-client-seconds", "10",
    "--poll-ms", "200",
    "--click-interval-ms", "4000",
    "--live",
    "--json"
)

$process = Start-Process `
    -FilePath $PythonPath `
    -ArgumentList $arguments `
    -WorkingDirectory $RepositoryRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $standardOutput `
    -RedirectStandardError $standardError `
    -PassThru

Start-Sleep -Milliseconds 750
$process.Refresh()
if ($process.HasExited) {
    $detail = if (Test-Path -LiteralPath $standardError) {
        (Get-Content -LiteralPath $standardError -Raw).Trim()
    }
    else {
        "listener exited without an error log"
    }
    throw "Shadowbane /go listener failed to start: $detail"
}

Set-Content -LiteralPath (Join-Path $LogDirectory "go-listener.pid") `
    -Value $process.Id `
    -Encoding ascii
Write-Output "Shadowbane /go listener started (PID $($process.Id))."
