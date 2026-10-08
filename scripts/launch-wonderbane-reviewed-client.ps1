[CmdletBinding()]
param([string] $RuntimeRoot = $PSScriptRoot)

# Dot sourcing exposes the receipt functions for executable regression tests.
function Write-AtomicLaunchJson {
    param([string] $Path, $Value, [switch] $CreateOnly)
    $temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 16), [Text.UTF8Encoding]::new($false))
        if ($CreateOnly -or -not [IO.File]::Exists($Path)) {
            [IO.File]::Move($temporary, $Path)
        } else {
            [IO.File]::Replace($temporary, $Path, [NullString]::Value)
        }
    } finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
}

function Get-LiveLaunchProcess {
    param($Receipt)
    $lookupErrors = @()
    $candidate = Get-Process -Id ([int]$Receipt.process_id) -ErrorAction SilentlyContinue -ErrorVariable lookupErrors
    if ($null -eq $candidate) {
        foreach ($failure in $lookupErrors) {
            if ($failure.FullyQualifiedErrorId -notlike 'NoProcessFoundForGivenId*') { throw $failure }
        }
        return $null
    }
    if ($null -eq $candidate.StartTime -or [string]::IsNullOrWhiteSpace($candidate.Path)) {
        throw 'Existing client identity cannot be inspected; preserve its binding'
    }
    # PID alone is never enough, including when Windows has reused it.
    if ($candidate.StartTime.ToUniversalTime().ToFileTimeUtc() -ne [long]$Receipt.creation_filetime) { return $null }
    if (-not [string]::Equals($candidate.Path, [string]$Receipt.executable, [StringComparison]::OrdinalIgnoreCase)) { throw 'Existing process lifetime has an unexpected executable path' }
    return $candidate
}

function Save-IndividualLaunchRecord {
    param([string] $RuntimeRoot, $Receipt, [switch] $Historical)
    if ([long]$Receipt.process_id -le 0 -or [long]$Receipt.creation_filetime -le 0) {
        throw 'Launch record requires a process lifetime'
    }
    $directory = Join-Path $RuntimeRoot ('launches/' + [long]$Receipt.process_id + '-' + [long]$Receipt.creation_filetime)
    [void][IO.Directory]::CreateDirectory($directory)
    $path = Join-Path $directory 'launch-receipt.json'
    if (Test-Path -LiteralPath $path) {
        $existing = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        foreach ($field in @('source_revision','process_id','creation_filetime','window','executable','loaded_dll_sha256')) {
            # A refreshed primary HWND is an observation, not a new process lifetime.
            if ($Historical -and $field -eq 'window') { continue }
            if ([string]$existing.$field -cne [string]$Receipt.$field) { throw "Conflicting launch record: $path" }
        }
    } else {
        Write-AtomicLaunchJson -Path $path -Value $Receipt -CreateOnly
    }
    return $path
}

function Write-LaunchRecord {
    param([string] $RuntimeRoot, $Receipt)
    $primaryPath = Join-Path $RuntimeRoot 'launch-receipt.json'
    $primary = $null
    if (Test-Path -LiteralPath $primaryPath) {
        $primary = Get-Content -LiteralPath $primaryPath -Raw | ConvertFrom-Json
        # Preserve the historical identity even when advancing a stale primary.
        [void](Save-IndividualLaunchRecord -RuntimeRoot $RuntimeRoot -Receipt $primary -Historical)
    }
    $individualPath = Save-IndividualLaunchRecord -RuntimeRoot $RuntimeRoot -Receipt $Receipt
    $retainPrimary = $null -ne $primary -and $null -ne (Get-LiveLaunchProcess -Receipt $primary)
    if (-not $retainPrimary) { Write-AtomicLaunchJson -Path $primaryPath -Value $Receipt }
    return [pscustomobject]@{receipt_path=$individualPath;primary_preserved=[bool]$retainPrimary}
}

function Invoke-ReviewedClientLaunch {
    param([string] $RuntimeRoot)
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    if ([IntPtr]::Size -ne 4) { throw 'Use the SysWOW64 PowerShell launcher for this 32-bit game' }
    $RuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
    $config = Get-Content -LiteralPath (Join-Path $RuntimeRoot 'reviewed-launch.json') -Raw | ConvertFrom-Json
    if ($config.schema_version -ne 1) { throw 'Unsupported reviewed launcher configuration' }
    foreach ($field in @('client_sha256','extension_sha256','official_sha256','baseline_guard_sha256')) {
        if ([string]$config.$field -cnotmatch '^[0-9a-f]{64}$') { throw "Invalid reviewed digest: $field" }
    }
    if ([string]$config.source_revision -cnotmatch '^[0-9a-f]{40}$') { throw 'Invalid reviewed source' }
    $status = Get-Content -LiteralPath (Join-Path $RuntimeRoot 'prepare-status.json') -Raw | ConvertFrom-Json
    if ($status.state -ne 'prepared_verified' -or $status.source_revision -ne $config.source_revision) { throw 'Runtime differs from reviewed launch configuration' }
    if ([string]$status.host_version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw 'Invalid prepared host version' }
    $python = Join-Path $RuntimeRoot ('host-' + $status.host_version + '/Scripts/python.exe')
    $client = Join-Path $RuntimeRoot 'client'
    $exe = Join-Path $client 'sb.exe'
    $extension = Join-Path $client 'wonderbane-extension.dll'
    $baseline = Join-Path $RuntimeRoot 'check-vendor-client-baseline.ps1'
    foreach ($entry in @(@($exe,$config.client_sha256),@($extension,$config.extension_sha256),@($baseline,$config.baseline_guard_sha256))) {
        if ((Get-FileHash -LiteralPath $entry[0] -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry[1]) { throw "Reviewed file changed: $($entry[0])" }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $RuntimeRoot 'settings-imported.json'))) { throw 'Settings import receipt is missing' }
    & $baseline -OfficialExecutable $config.official_executable -ExpectedSourceSha256 $config.official_sha256

    # Serialize only launch bookkeeping; the lock is released while clients run.
    $lock = $null
    $wait = [Diagnostics.Stopwatch]::StartNew()
    while ($null -eq $lock) {
        try { $lock = [IO.File]::Open((Join-Path $RuntimeRoot 'launch.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
        catch [IO.IOException] {
            if ($wait.Elapsed.TotalSeconds -ge 60) { throw 'Another launch is still completing; try again shortly' }
            Start-Sleep -Milliseconds 200
        }
    }
    $priorPythonPath=$env:PYTHONPATH; $priorPythonHome=$env:PYTHONHOME
    try {
        $env:PYTHONPATH=$null; $env:PYTHONHOME=$null
        $attempt = Join-Path $RuntimeRoot ('launches/attempt-' + [Guid]::NewGuid().ToString('N'))
        [void][IO.Directory]::CreateDirectory($attempt)
        $verify = Join-Path $attempt 'verification.json'
        # Retain complete native stderr without PowerShell terminating its capture.
        $ErrorActionPreference='Continue'
        try { & $python -m shadowbane_lab.client_extension verify-launchable-copy $client --pretty *> $verify; $verifyExit=$LASTEXITCODE }
        finally { $ErrorActionPreference='Stop' }
        if ($verifyExit -ne 0) { throw "Launch verification failed; see $verify" }
        $env:LIBGL_ALWAYS_SOFTWARE='true'; $env:GALLIUM_DRIVER='llvmpipe'; $env:MESA_EXTENSION_MAX_YEAR='2001'
        $env:MESA_GL_VERSION_OVERRIDE=$null; $env:MESA_GLSL_VERSION_OVERRIDE=$null; $env:WONDERBANE_TERRAIN_TRACE=$null
        $env:WONDERBANE_TARGETED_ACTION_TRACE='1'; $env:WONDERBANE_MOVEMENT_TRACE='1'
        $game = Start-Process -FilePath $exe -WorkingDirectory $client -WindowStyle Normal -PassThru
        $creation = $game.StartTime.ToUniversalTime().ToFileTimeUtc()
        $pending = [ordered]@{state='started_unverified';process_id=$game.Id;creation_filetime=$creation;executable=$exe}
        Write-AtomicLaunchJson -Path (Join-Path $attempt 'startup.json') -Value $pending -CreateOnly
        $timer = [Diagnostics.Stopwatch]::StartNew()
        $module = $null
        while ($timer.Elapsed.TotalSeconds -lt 30) {
            $game.Refresh()
            if ($game.HasExited) { throw "New client PID $($game.Id) exited with code $($game.ExitCode); existing clients were not stopped" }
            $module = $game.Modules | Where-Object ModuleName -ieq 'wonderbane-extension.dll' | Select-Object -First 1
            if ($null -ne $module -and $game.MainWindowHandle -ne [IntPtr]::Zero) { break }
            Start-Sleep -Milliseconds 250
        }
        if ($null -eq $module -or $game.MainWindowHandle -eq [IntPtr]::Zero) { throw "Client PID $($game.Id) started but its extension/window was not verified; inspect $attempt" }
        if (-not [string]::Equals([IO.Path]::GetFullPath($module.FileName),[IO.Path]::GetFullPath($extension),[StringComparison]::OrdinalIgnoreCase)) { throw 'Loaded extension path differs from reviewed client' }
        $hash = (Get-FileHash -LiteralPath $module.FileName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -cne $config.extension_sha256) { throw 'Loaded extension digest differs from reviewed client' }
        $receipt = [ordered]@{source_revision=$config.source_revision;process_id=$game.Id;creation_filetime=$creation;window=[long]$game.MainWindowHandle;executable=$exe;loaded_dll_sha256=$hash;utc=[DateTime]::UtcNow.ToString('o')}
        if ($null -eq (Get-LiveLaunchProcess -Receipt ([pscustomobject]$receipt))) { throw 'New client exited before receipt publication' }
        $records = Write-LaunchRecord -RuntimeRoot $RuntimeRoot -Receipt ([pscustomobject]$receipt)
        Write-AtomicLaunchJson -Path (Join-Path $attempt 'startup.json') -Value ([ordered]@{state='verified';receipt_path=$records.receipt_path;primary_preserved=$records.primary_preserved})
        [pscustomobject]@{state='launched_verified';launch=$receipt;receipt_path=$records.receipt_path;primary_preserved=$records.primary_preserved} | ConvertTo-Json -Depth 8
    } finally {
        $env:PYTHONPATH=$priorPythonPath; $env:PYTHONHOME=$priorPythonHome
        $lock.Dispose()
    }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-ReviewedClientLaunch -RuntimeRoot $RuntimeRoot }