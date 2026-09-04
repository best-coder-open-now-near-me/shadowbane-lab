$ErrorActionPreference = "Stop"

$source = Join-Path $PSScriptRoot "druid-aoe.ps1"
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Macro runner was not found: $source"
}

$installDirectory = Join-Path $env:LOCALAPPDATA "ShadowbaneLab\macros"
$runner = Join-Path $installDirectory "druid-aoe.ps1"
New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $runner -Force
$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$installedHash = (Get-FileHash -LiteralPath $runner -Algorithm SHA256).Hash
if ($sourceHash -ne $installedHash) {
    throw "Installed macro hash does not match its source."
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Shadowbane Druid AoE Macro.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$shortcut.WorkingDirectory = $installDirectory
$shortcut.Description = "Keyboard-only Shadowbane Druid PvE AoE rotation"
$shortcut.Save()

Write-Host "Installed Druid AoE macro: $runner" -ForegroundColor Green
Write-Host "SHA256: $installedHash"
Write-Host "Desktop shortcut: $shortcutPath"
Write-Host "Launching paused; use F8 in Shadowbane to toggle it."
Start-Process -FilePath $shortcut.TargetPath -ArgumentList $shortcut.Arguments -WorkingDirectory $installDirectory
