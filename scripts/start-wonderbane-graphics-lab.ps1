[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexrepo",
    [string] $PythonExecutable = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

foreach ($required in @(
    @{ Path = $RepositoryShare; Description = "graphics repository share" },
    @{ Path = $PythonExecutable; Description = "guest Python environment" },
    @{
        Path = (Join-Path $RepositoryShare "src\shadowbane_lab\graphics_lab\__main__.py")
        Description = "WonderBane Graphics Lab"
    }
)) {
    if (-not (Test-Path -LiteralPath $required.Path)) {
        throw "$($required.Description) was not found: $($required.Path)"
    }
}

$pythonDirectory = Split-Path -Parent $PythonExecutable
$pythonw = Join-Path $pythonDirectory "pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
    $pythonw = $PythonExecutable
}
$existing = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "python.exe" -or $_.Name -eq "pythonw.exe") -and
    $_.CommandLine -like "*shadowbane_lab.graphics_lab*"
} | Select-Object -First 1
if ($null -ne $existing) {
    Write-Output "WonderBane Graphics Lab is already running (PID $($existing.ProcessId))."
    return
}
$previousPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
try {
    [Environment]::SetEnvironmentVariable(
        "PYTHONPATH",
        (Join-Path $RepositoryShare "src"),
        "Process"
    )
    $startArguments = @{
        FilePath = $pythonw
        ArgumentList = @("-m", "shadowbane_lab.graphics_lab")
        WorkingDirectory = $RepositoryShare
        PassThru = $true
    }
    $process = Start-Process @startArguments
}
finally {
    [Environment]::SetEnvironmentVariable(
        "PYTHONPATH",
        $previousPythonPath,
        "Process"
    )
}

Write-Output "WonderBane Graphics Lab started (PID $($process.Id))."
