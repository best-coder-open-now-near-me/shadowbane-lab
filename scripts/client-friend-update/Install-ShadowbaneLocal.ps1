#Requires -Version 5.1
[CmdletBinding()]
param([string]$ClientDirectory = '')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-PlainPath([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    while ($null -ne $item) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Linked paths are not supported: $Path"
        }
        $item = if ($item -is [IO.DirectoryInfo]) { $item.Parent } else { $item.Directory }
    }
}
function Set-ServerEndpoint([byte[]]$Bytes) {
    if ($Bytes.Length -gt 1048576 -or $Bytes -contains 0) { throw 'ArcaneIP.cfg is not supported plain text' }
    $encoding = [Text.Encoding]::GetEncoding(28591)
    $source = $encoding.GetString($Bytes)
    $bom = ''
    if ($source.StartsWith([string][char]239 + [char]187 + [char]191)) {
        $bom = $source.Substring(0,3); $source = $source.Substring(3)
    }
    $newline = if ($source.Contains("`r`n")) { "`r`n" } else { "`n" }
    foreach ($entry in @(@('SERVER','100.87.213.55'), @('PORT','6000'))) {
        $pattern = '(?m)^([ \t]*' + $entry[0] + '[ \t]*=[ \t]*)([^\r\n]*)'
        $matches = [regex]::Matches($source, $pattern)
        if ($matches.Count -gt 1) { throw ('Duplicate endpoint key: ' + $entry[0]) }
        if ($matches.Count -eq 1) {
            $match = $matches[0]
            $value = $match.Groups[2].Value
            $annotation = [regex]::Match($value, '[ \t]*(?:[#;(]|//).*')
            $replacement = $match.Groups[1].Value + $entry[1] + $annotation.Value
            $source = $source.Remove($match.Index, $match.Length).Insert($match.Index, $replacement)
        } else {
            if ($source.Length -gt 0 -and -not $source.EndsWith("`n")) { $source += $newline }
            $source += $entry[0] + '= ' + $entry[1] + $newline
        }
    }
    return ,$encoding.GetBytes($bom + $source)
}
function Write-Atomic([string]$Path, [byte[]]$Bytes) {
    if (Test-Path -LiteralPath $Path) { Assert-PlainPath $Path }
    $temporary = Join-Path (Split-Path -Parent $Path) ('.shadowbane-update-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllBytes($temporary, $Bytes)
        if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporary, $Path, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $Path) }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}
try {
    Assert-PlainPath $PSScriptRoot
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'package.json') -Raw | ConvertFrom-Json
    if ($manifest.schema_version -ne 1 -or $manifest.server -ne '100.87.213.55' -or $manifest.port -ne 6000) { throw 'Unexpected update manifest' }
    $payloadNames = @('ShadowbaneLauncher.exe','Play-ShadowbaneLocal.cmd','Install-ShadowbaneLocal.cmd','Install-ShadowbaneLocal.ps1','README.txt')
    if (@($manifest.files.PSObject.Properties).Count -ne $payloadNames.Count) { throw 'Unexpected update file inventory' }
    foreach ($name in $payloadNames) {
        $path = Join-Path $PSScriptRoot $name
        Assert-PlainPath $path
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.files.$name) {
            throw ("Update file is damaged or changed: " + $name)
        }
    }
    if (-not $ClientDirectory -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'sb.exe'))) { $ClientDirectory = $PSScriptRoot }
    if (-not $ClientDirectory) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object System.Windows.Forms.FolderBrowserDialog
        $picker.Description = 'Choose the dedicated private-server client folder containing sb.exe.'
        $picker.ShowNewFolderButton = $false
        try {
            if ($picker.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { throw 'Installation canceled; nothing changed.' }
            $ClientDirectory = $picker.SelectedPath
        } finally { $picker.Dispose() }
    }
    $root = (Resolve-Path -LiteralPath $ClientDirectory).Path
    foreach ($relative in @('','Config','cache','sb.exe','cache\CObjects.cache','Config\ArcanePref.cfg')) {
        Assert-PlainPath (Join-Path $root $relative)
    }
    # The exact native launcher enforces its compiled executable/cache pins and
    # confirms the game is closed. Inspection launches nothing and writes nothing.
    $launcher = Join-Path $PSScriptRoot 'ShadowbaneLauncher.exe'
    $inspectionText = (& $launcher --inspect --client-root $root | Out-String)
    $inspectionExit = $LASTEXITCODE
    $inspection = $inspectionText | ConvertFrom-Json
    if ($inspectionExit -ne 0 -or $inspection.status -ne 'preflight_ready' -or -not $inspection.markers_verified) {
        throw ('Client is not ready for this update: ' + $inspection.message)
    }
    $endpoint = Join-Path $root 'Config\ArcaneIP.cfg'
    $oldEndpoint = [byte[]]@()
    if (Test-Path -LiteralPath $endpoint) {
        Assert-PlainPath $endpoint
        $oldEndpoint = [IO.File]::ReadAllBytes($endpoint)
    }
    $newEndpoint = Set-ServerEndpoint $oldEndpoint
    $preferences = Join-Path $root 'Config\ArcanePref.cfg'
    $preferencesHash = (Get-FileHash -LiteralPath $preferences -Algorithm SHA256).Hash
    $targets = @('ShadowbaneLauncher.exe','Play-ShadowbaneLocal.cmd','ShadowbaneLauncher.install.json')
    foreach ($target in $targets) {
        $path = Join-Path $root $target
        if (Test-Path -LiteralPath $path) { Assert-PlainPath $path }
    }
    foreach ($name in @('ShadowbaneLauncher.exe','Play-ShadowbaneLocal.cmd')) {
        $destination = Join-Path $root $name
        $bytes = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot $name))
        if (-not (Test-Path -LiteralPath $destination) -or
            (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.files.$name) {
            Write-Atomic $destination $bytes
        }
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.files.$name) { throw 'Installed file verification failed' }
    }
    Write-Atomic $endpoint $newEndpoint
    if ((Get-FileHash -LiteralPath $preferences -Algorithm SHA256).Hash -ne $preferencesHash) { throw 'Client preferences changed during installation' }
    $receipt = [ordered]@{
        installed_utc = (Get-Date).ToUniversalTime().ToString('o')
        source_commit = $manifest.source_commit
        launcher_sha256 = $manifest.files.'ShadowbaneLauncher.exe'
        server = $manifest.server
        port = $manifest.port
        preferences_preserved = $true
    }
    Write-Atomic (Join-Path $root 'ShadowbaneLauncher.install.json') ([Text.Encoding]::UTF8.GetBytes(($receipt | ConvertTo-Json) + "`r`n"))
    Write-Output ('Installed. Launch ' + (Join-Path $root 'Play-ShadowbaneLocal.cmd'))
    Write-Output 'Keep Tailscale connected. No game files or saved settings were replaced.'
} catch {
    Write-Error $_.Exception.Message -ErrorAction Continue
    exit 1
}
