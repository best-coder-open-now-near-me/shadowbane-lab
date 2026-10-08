#Requires -Version 7.0
[CmdletBinding()]
param([string]$ServiceRoot = 'E:\Services\ShadowbaneReports')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this one-time server setup as administrator.'
}
$ServiceRoot = (Resolve-Path -LiteralPath $ServiceRoot).Path
$python = Join-Path $ServiceRoot 'runtime\Scripts\pythonw.exe'
$config = Join-Path $ServiceRoot 'receiver.json'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $config)) {
    throw 'Install the report receiver and private configuration first.'
}
$tailscale = 'C:\Program Files\Tailscale\tailscale.exe'
$beforeText = & $tailscale serve status --json
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the existing private HTTPS service.' }
$before = $beforeText | ConvertFrom-Json -AsHashtable
# Add one route; never reset or replace the separately owned updates handler.
& $tailscale serve --bg --https=443 --set-path=/shadowbane-reports/ --yes http://127.0.0.1:8765
if ($LASTEXITCODE -ne 0) { throw 'The private HTTPS report route was not enabled.' }
$afterText = & $tailscale serve status --json
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify the private HTTPS configuration.' }
$after = $afterText | ConvertFrom-Json -AsHashtable
if ($before.ContainsKey('Web')) {
foreach ($hostEntry in $before.Web.GetEnumerator()) {
    foreach ($handler in $hostEntry.Value.Handlers.GetEnumerator()) {
        if ($handler.Key -eq '/shadowbane-reports/') { continue }
        if (($after.Web[$hostEntry.Key].Handlers[$handler.Key] | ConvertTo-Json -Compress -Depth 10) -ne
            ($handler.Value | ConvertTo-Json -Compress -Depth 10)) {
            throw "Existing private route changed: $($handler.Key)"
        }
    }
}
}
$action = New-ScheduledTaskAction -Execute $python -Argument "-m shadowbane_lab.character_capture.receiver --root `"$ServiceRoot\data`" --config `"$config`" --port 8765" -WorkingDirectory $ServiceRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
$existingTask = Get-ScheduledTask -TaskName 'Shadowbane Report Receiver' -ErrorAction SilentlyContinue
if ($existingTask -and (@($existingTask.Actions).Count -ne 1 -or
    $existingTask.Actions[0].Execute -ne $python -or
    $existingTask.Actions[0].Arguments -ne $action.Arguments)) {
    throw 'A different startup task already uses the report receiver name.'
}
Register-ScheduledTask -TaskName 'Shadowbane Report Receiver' -Action $action -Trigger $trigger -Principal $taskPrincipal -Settings $settings -Force | Out-Null
# Stop only this receiver after its startup task has been registered.
$pidFile = Join-Path $ServiceRoot 'receiver.pid'
if (Test-Path -LiteralPath $pidFile) {
    $receiverId = [int](Get-Content -LiteralPath $pidFile -Raw)
    $running = Get-CimInstance Win32_Process -Filter "ProcessId=$receiverId" -ErrorAction SilentlyContinue
    if ($running -and $running.ExecutablePath -eq $python -and
        $running.CommandLine -like '*shadowbane_lab.character_capture.receiver*') {
        Stop-Process -Id $receiverId
    }
}
Remove-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name ShadowbaneReportReceiver -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName 'Shadowbane Report Receiver'
[ordered]@{
    configured_at_utc = [DateTime]::UtcNow.ToString('o')
    private_https_route = '/shadowbane-reports/'
    startup_task = 'Shadowbane Report Receiver'
    existing_routes_preserved = $true
} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $ServiceRoot 'admin-setup-receipt.json')
Write-Output 'Private report delivery enabled. Now verify a report upload through HTTPS.'
