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

function Get-GraphicsLabProcesses {
    @(
        Get-CimInstance Win32_Process | Where-Object {
            ($_.Name -eq "python.exe" -or $_.Name -eq "pythonw.exe") -and
            $_.CommandLine -like "*shadowbane_lab.graphics_lab*"
        }
    )
}

function Get-ReadyGraphicsLabProcess([uint32] $ProcessId) {
    $candidate = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $candidate) {
        return $null
    }
    $candidate.Refresh()
    if ($candidate.MainWindowHandle -eq 0) {
        return $null
    }
    return $candidate
}

function Stop-ExactHeadlessGraphicsLabProcess($Candidate) {
    Start-Sleep -Milliseconds 250
    if ($null -ne (Get-ReadyGraphicsLabProcess -ProcessId $Candidate.ProcessId)) {
        return $false
    }
    $current = Get-CimInstance Win32_Process -Filter (
        "ProcessId = {0}" -f $Candidate.ProcessId
    ) -ErrorAction SilentlyContinue
    if ($null -eq $current) {
        return $true
    }
    if (
        ($current.Name -ne "python.exe" -and $current.Name -ne "pythonw.exe") -or
        $current.CommandLine -notlike "*shadowbane_lab.graphics_lab*" -or
        [string] $current.CreationDate -cne [string] $Candidate.CreationDate
    ) {
        throw "Graphics Lab PID identity changed before stale-process cleanup"
    }
    Stop-Process -Id $Candidate.ProcessId -Force
    Write-Output (
        "Stopped headless WonderBane Graphics Lab process (PID {0})." -f
        $Candidate.ProcessId
    )
    return $true
}

foreach ($existing in Get-GraphicsLabProcesses) {
    if ($null -ne (Get-ReadyGraphicsLabProcess -ProcessId $existing.ProcessId)) {
        Write-Output (
            "WonderBane Graphics Lab is already visible (PID {0})." -f
            $existing.ProcessId
        )
        return
    }
    Stop-ExactHeadlessGraphicsLabProcess -Candidate $existing | Out-Null
}

$pythonDirectory = Split-Path -Parent $PythonExecutable
$pythonw = Join-Path $pythonDirectory "pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
    $pythonw = $PythonExecutable
}
if (-not $env:LOCALAPPDATA) {
    throw "LOCALAPPDATA is required for Graphics Lab startup evidence"
}
$logDirectory = Join-Path $env:LOCALAPPDATA "ShadowbaneLab\graphics-lab\logs"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$launchId = "{0}-{1}" -f (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ"), [Guid]::NewGuid().ToString("N")
$standardOutputPath = Join-Path $logDirectory "$launchId.stdout.log"
$standardErrorPath = Join-Path $logDirectory "$launchId.stderr.log"
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
        RedirectStandardOutput = $standardOutputPath
        RedirectStandardError = $standardErrorPath
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

$deadline = [DateTime]::UtcNow.AddSeconds(10)
while ([DateTime]::UtcNow -lt $deadline) {
    $ready = Get-ReadyGraphicsLabProcess -ProcessId $process.Id
    if ($null -ne $ready) {
        Write-Output (
            "WonderBane Graphics Lab started and is visible (PID {0})." -f
            $process.Id
        )
        Write-Output "Graphics Lab error log: $standardErrorPath"
        return
    }
    if ($null -eq (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        break
    }
    Start-Sleep -Milliseconds 100
}

$launched = Get-CimInstance Win32_Process -Filter (
    "ProcessId = {0}" -f $process.Id
) -ErrorAction SilentlyContinue
if (
    $null -ne $launched -and
    ($launched.Name -eq "python.exe" -or $launched.Name -eq "pythonw.exe") -and
    $launched.CommandLine -like "*shadowbane_lab.graphics_lab*"
) {
    Stop-Process -Id $process.Id -Force
}
$errorTail = ""
if (Test-Path -LiteralPath $standardErrorPath -PathType Leaf) {
    $errorTail = (Get-Content -LiteralPath $standardErrorPath -Tail 20) -join "`n"
}
if (-not $errorTail) {
    $errorTail = "No Python error output was captured."
}
throw (
    "WonderBane Graphics Lab did not create a visible window within 10 seconds. " +
    "Error log: $standardErrorPath`n$errorTail"
)
