# Executable receipt regressions. No game, native module or external process is launched.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$script:checks = 0
function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
    $script:checks++
}
function Assert-Rejected([scriptblock]$Action, [string]$Message) {
    $rejected = $false
    try { & $Action | Out-Null } catch { $rejected = $true }
    Assert-True $rejected $Message
}
function New-Receipt([int]$ProcessId, [long]$Creation) {
    return [pscustomobject][ordered]@{
        source_revision = ('a' * 40)
        process_id = $ProcessId
        creation_filetime = $Creation
        window = 123456
        executable = 'C:\Reviewed Client\sb.exe'
        loaded_dll_sha256 = ('b' * 64)
        utc = '2026-10-08T18:00:00.1234567Z'
    }
}
function Read-Json([string]$Path) { Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
function Hash-File([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
function New-Case([string]$Name) {
    $path = Join-Path $script:testRoot $Name
    [void][IO.Directory]::CreateDirectory($path)
    return $path
}

# Dot sourcing must not invoke the launcher. This sentinel catches accidental entry.
function Start-Process { throw 'Dot sourcing or receipt tests attempted a process launch' }
$launcher = Join-Path (Split-Path -Parent $PSScriptRoot) 'launch-wonderbane-reviewed-client.ps1'
. $launcher
$realLiveProcess = ${function:Get-LiveLaunchProcess}
$script:live = @{}
function Get-LiveLaunchProcess {
    param($Receipt)
    if ($script:live.ContainsKey(([string]$Receipt.process_id + '-' + [string]$Receipt.creation_filetime))) {
        return [pscustomobject]@{ Id = $Receipt.process_id }
    }
    return $null
}
$script:testRoot = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) ('reviewed-launch-tests-' + [Guid]::NewGuid().ToString('N'))))
[void][IO.Directory]::CreateDirectory($script:testRoot)
try {
    $first = New-Receipt 101 134359570353507178
    $second = New-Receipt 202 134359570353507999
    $firstKey = [string]$first.process_id + '-' + [string]$first.creation_filetime
    $secondKey = [string]$second.process_id + '-' + [string]$second.creation_filetime

    $case = New-Case 'first-and-second'
    $record = Write-LaunchRecord -RuntimeRoot $case -Receipt $first
    $primary = Join-Path $case 'launch-receipt.json'
    $individual = Join-Path $case ('launches/' + $firstKey + '/launch-receipt.json')
    Assert-True ($record.receipt_path -eq $individual -and -not $record.primary_preserved) 'First receipt destination/result differs'
    Assert-True ((Read-Json $primary).process_id -eq 101 -and (Read-Json $individual).creation_filetime -eq $first.creation_filetime) 'First primary and individual identities differ'
    $firstHash = Hash-File $individual
    $primaryHash = Hash-File $primary
    $script:live[$firstKey] = $true
    $record = Write-LaunchRecord -RuntimeRoot $case -Receipt $second
    Assert-True $record.primary_preserved 'A live primary was not preserved for a second client'
    Assert-True ((Hash-File $primary) -eq $primaryHash -and (Hash-File $individual) -eq $firstHash) 'Second client changed existing receipt bytes'
    Assert-True ((Read-Json $record.receipt_path).process_id -eq 202) 'Second client has no independent lifetime receipt'
    $secondHash = Hash-File $record.receipt_path
    $repeat = Write-LaunchRecord -RuntimeRoot $case -Receipt $second
    Assert-True ((Hash-File $repeat.receipt_path) -eq $secondHash -and (Hash-File $primary) -eq $primaryHash) 'Identical receipt retry rewrote history or primary'

    foreach ($field in @('source_revision', 'window', 'executable', 'loaded_dll_sha256')) {
        $changed = $second | ConvertTo-Json | ConvertFrom-Json
        if ($field -eq 'window') { $changed.$field = 999999 } else { $changed.$field = 'different' }
        Assert-Rejected { Write-LaunchRecord -RuntimeRoot $case -Receipt $changed } ('Conflicting lifetime receipt accepted: ' + $field)
        Assert-True ((Hash-File $repeat.receipt_path) -eq $secondHash -and (Hash-File $primary) -eq $primaryHash) 'Rejected conflict mutated receipts'
    }

    $legacyCase = New-Case 'legacy-live-migration'
    $legacyPath = Join-Path $legacyCase 'launch-receipt.json'
    # Deliberate whitespace/newline spelling detects reserialization of the live primary.
    [IO.File]::WriteAllText($legacyPath, ('  ' + ($first | ConvertTo-Json -Compress) + "`r`n`r`n"), [Text.UTF8Encoding]::new($false))
    $legacyHash = Hash-File $legacyPath
    $migrated = Write-LaunchRecord -RuntimeRoot $legacyCase -Receipt $second
    $oldIndividual = Join-Path $legacyCase ('launches/' + $firstKey + '/launch-receipt.json')
    Assert-True ($migrated.primary_preserved -and (Hash-File $legacyPath) -eq $legacyHash) 'Legacy live primary bytes changed'
    Assert-True ((Read-Json $oldIndividual).creation_filetime -eq $first.creation_filetime -and (Read-Json $oldIndividual).utc -eq $first.utc) 'Legacy migration lost lifetime or original timestamp'
    Assert-True ((Read-Json $migrated.receipt_path).process_id -eq 202) 'Migration lost second client record'

    $script:live.Clear()
    $staleCase = New-Case 'stale-primary'
    $stalePath = Join-Path $staleCase 'launch-receipt.json'
    [IO.File]::WriteAllText($stalePath, ($first | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    $advanced = Write-LaunchRecord -RuntimeRoot $staleCase -Receipt $second
    Assert-True (-not $advanced.primary_preserved -and (Read-Json $stalePath).process_id -eq 202) 'Stale primary did not advance'
    $oldStale = Join-Path $staleCase ('launches/' + $firstKey + '/launch-receipt.json')
    Assert-True ((Read-Json $oldStale).process_id -eq 101) 'Advancing stale primary discarded original history'

    $conflictCase = New-Case 'legacy-conflict'
    [void](Write-LaunchRecord -RuntimeRoot $conflictCase -Receipt $first)
    $conflictPrimary = Join-Path $conflictCase 'launch-receipt.json'
    $badPrimary = $first | ConvertTo-Json | ConvertFrom-Json
    $badPrimary.loaded_dll_sha256 = ('c' * 64)
    [IO.File]::WriteAllText($conflictPrimary, ($badPrimary | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    $beforeConflict = Hash-File $conflictPrimary
    Assert-Rejected { Write-LaunchRecord -RuntimeRoot $conflictCase -Receipt $second } 'Conflicting legacy migration was overwritten'
    Assert-True ((Hash-File $conflictPrimary) -eq $beforeConflict -and -not (Test-Path -LiteralPath (Join-Path $conflictCase ('launches/' + $secondKey)))) 'Rejected migration mutated primary or created another client record'

    $refreshCase = New-Case 'window-refreshed'
    [void](Write-LaunchRecord -RuntimeRoot $refreshCase -Receipt $first)
    $refreshPrimary = Join-Path $refreshCase 'launch-receipt.json'
    $refreshIndividual = Join-Path $refreshCase ('launches/' + $firstKey + '/launch-receipt.json')
    $originalHash = Hash-File $refreshIndividual
    $refreshed = $first | ConvertTo-Json | ConvertFrom-Json
    $refreshed.window = 654321
    [IO.File]::WriteAllText($refreshPrimary, ($refreshed | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    $refreshedHash = Hash-File $refreshPrimary
    $script:live[$firstKey] = $true
    $next = Write-LaunchRecord -RuntimeRoot $refreshCase -Receipt $second
    Assert-True $next.primary_preserved 'Refreshed primary was not retained'
    Assert-True ((Hash-File $refreshPrimary) -eq $refreshedHash -and (Hash-File $refreshIndividual) -eq $originalHash) 'Window refresh rewrote original or current observation'

    # Exercise the real liveness discriminator against a mocked Windows process census.
    Set-Item -Path Function:Get-LiveLaunchProcess -Value $realLiveProcess
    $script:observed = $null
    function Get-Process {
        [CmdletBinding()]
        param([int]$Id)
        if ($Id -ne 101) { throw 'Unexpected process request' }
        return $script:observed
    }
    Assert-True ($null -eq (Get-LiveLaunchProcess -Receipt $first)) 'Exited PID was accepted'
    $script:observed = [pscustomobject]@{ Id = 101; StartTime = [DateTime]::FromFileTimeUtc($first.creation_filetime); Path = $first.executable.ToUpperInvariant() }
    Assert-True ($null -ne (Get-LiveLaunchProcess -Receipt $first)) 'Exact lifetime/path with case-insensitive Windows spelling rejected'
    $script:observed.StartTime = [DateTime]::FromFileTimeUtc($first.creation_filetime + 1)
    Assert-True ($null -eq (Get-LiveLaunchProcess -Receipt $first)) 'Reused PID with new creation time accepted'
    $script:observed.StartTime = [DateTime]::FromFileTimeUtc($first.creation_filetime)
    $script:observed.Path = 'C:\Different Client\sb.exe'
    Assert-Rejected { Get-LiveLaunchProcess -Receipt $first } 'Same PID/time at foreign executable accepted'
    $script:observed.Path = $null
    Assert-Rejected { Get-LiveLaunchProcess -Receipt $first } 'Unreadable process identity accepted'
    Assert-True (@(Get-ChildItem -LiteralPath $script:testRoot -Recurse -Filter '*.tmp').Count -eq 0) 'Atomic-write temporary files remain'
    Write-Output ("Reviewed client launch receipt tests: {0} assertions passed; no client launched" -f $script:checks)
} finally {
    $resolved = (Resolve-Path -LiteralPath $script:testRoot).ProviderPath
    $tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if ($resolved -cne $script:testRoot -or -not $resolved.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Test cleanup path differs from owned temporary root'
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
