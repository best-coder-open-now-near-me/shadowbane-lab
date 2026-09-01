[CmdletBinding()]
param(
    [string]$LocalEvidenceRoot = "$env:LOCALAPPDATA\ShadowbaneLab\translocation-hangs",
    [string]$PublishEvidenceRoot = "\\VBOXSVR\codexdiag\translocation-hangs",
    [string]$ToolRoot = "$env:LOCALAPPDATA\ShadowbaneLab\tools\procdump",
    [ValidateRange(1, 3)]
    [int]$DumpCount = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$procDumpDownloadUri = "https://download.sysinternals.com/files/Procdump.zip"
$utf8NoBom = [Text.UTF8Encoding]::new($false)

function Write-JsonCreateNew {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [object]$Value
    )

    $json = $Value | ConvertTo-Json -Depth 8
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try {
        $writer = [IO.StreamWriter]::new($stream, $utf8NoBom)
        try {
            $writer.Write($json)
            $writer.Write("`n")
            $writer.Flush()
        }
        finally {
            $writer.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Assert-MicrosoftAuthenticodeSignature {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne [Management.Automation.SignatureStatus]::Valid) {
        throw "ProcDump signature is not valid: $($signature.Status)"
    }
    if ($null -eq $signature.SignerCertificate) {
        throw "ProcDump has no signing certificate."
    }
    if ($signature.SignerCertificate.Subject -notmatch "(?:^|, )O=Microsoft Corporation(?:,|$)") {
        throw "ProcDump is not signed by Microsoft Corporation: $($signature.SignerCertificate.Subject)"
    }
    return $signature
}

function Get-VerifiedProcDump {
    param(
        [Parameter(Mandatory)]
        [string]$DestinationRoot
    )

    $toolPath = Join-Path $DestinationRoot "procdump64.exe"
    if (Test-Path -LiteralPath $toolPath -PathType Leaf) {
        $null = Assert-MicrosoftAuthenticodeSignature -Path $toolPath
        return $toolPath
    }

    New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    $stagingRoot = Join-Path $DestinationRoot ("install-" + [Guid]::NewGuid().ToString("N"))
    $archivePath = Join-Path $stagingRoot "Procdump.zip"
    $extractRoot = Join-Path $stagingRoot "expanded"
    New-Item -ItemType Directory -Path $stagingRoot | Out-Null
    try {
        Write-Host "Downloading Microsoft Sysinternals ProcDump from $procDumpDownloadUri"
        Invoke-WebRequest -UseBasicParsing -Uri $procDumpDownloadUri -OutFile $archivePath
        Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot
        $candidate = Join-Path $extractRoot "procdump64.exe"
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "The Microsoft ProcDump archive did not contain procdump64.exe."
        }
        $null = Assert-MicrosoftAuthenticodeSignature -Path $candidate
        [IO.File]::Move($candidate, $toolPath)
    }
    finally {
        if (Test-Path -LiteralPath $stagingRoot) {
            Remove-Item -LiteralPath $stagingRoot -Recurse -Force
        }
    }
    $null = Assert-MicrosoftAuthenticodeSignature -Path $toolPath
    return $toolPath
}

function Publish-EvidenceDirectory {
    param(
        [Parameter(Mandatory)]
        [string]$Source,
        [Parameter(Mandatory)]
        [string]$DestinationRoot,
        [Parameter(Mandatory)]
        [string]$RunId
    )

    if ([string]::IsNullOrWhiteSpace($DestinationRoot)) {
        return $null
    }
    New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    $destination = Join-Path $DestinationRoot $RunId
    if (Test-Path -LiteralPath $destination) {
        throw "Published evidence destination already exists: $destination"
    }
    $staging = "$destination.staging-$([Guid]::NewGuid().ToString('N'))"
    try {
        Copy-Item -LiteralPath $Source -Destination $staging -Recurse
        $sourceFiles = @(Get-ChildItem -LiteralPath $Source -File | Sort-Object Name)
        $publishedFiles = @(Get-ChildItem -LiteralPath $staging -File | Sort-Object Name)
        if (($sourceFiles.Name -join "`n") -ne ($publishedFiles.Name -join "`n")) {
            throw "Published evidence inventory does not match the local capture."
        }
        foreach ($sourceFile in $sourceFiles) {
            $publishedFile = Join-Path $staging $sourceFile.Name
            if ((Get-FileHash -Algorithm SHA256 -LiteralPath $sourceFile.FullName).Hash -ne
                (Get-FileHash -Algorithm SHA256 -LiteralPath $publishedFile).Hash) {
                throw "Published evidence hash mismatch: $($sourceFile.Name)"
            }
        }
        [IO.Directory]::Move($staging, $destination)
    }
    finally {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
    }
    return $destination
}

$processes = @(Get-Process -Name "sb" -ErrorAction SilentlyContinue)
if ($processes.Count -ne 1) {
    throw "Expected exactly one running sb.exe process, found $($processes.Count)."
}
$game = $processes[0]
if ([string]::IsNullOrWhiteSpace($game.Path) -or -not (Test-Path -LiteralPath $game.Path -PathType Leaf)) {
    throw "Could not resolve the running sb.exe path."
}

$procDump = Get-VerifiedProcDump -DestinationRoot $ToolRoot
$procDumpSignature = Assert-MicrosoftAuthenticodeSignature -Path $procDump
$runId = "shadowbane-translocation-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))"
$localRunDirectory = Join-Path $LocalEvidenceRoot $runId
if (Test-Path -LiteralPath $localRunDirectory) {
    throw "Local evidence destination already exists: $localRunDirectory"
}
New-Item -ItemType Directory -Path $localRunDirectory -Force | Out-Null

$request = [ordered]@{
    schema_version = 1
    run_id = $runId
    status = "waiting_for_hung_window"
    started_at_utc = [DateTime]::UtcNow.ToString("o")
    trigger = [ordered]@{
        kind = "windows_hung_window"
        minimum_unresponsive_seconds = 5
        dump_type = "full"
        dump_count = $DumpCount
    }
    game = [ordered]@{
        process_id = $game.Id
        process_started_at_utc = $game.StartTime.ToUniversalTime().ToString("o")
        executable_path = $game.Path
        executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $game.Path).Hash.ToLowerInvariant()
        main_window_handle = $game.MainWindowHandle.ToInt64()
        responding_at_start = $game.Responding
    }
    collector = [ordered]@{
        path = $procDump
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $procDump).Hash.ToLowerInvariant()
        signer_subject = $procDumpSignature.SignerCertificate.Subject
        download_uri = $procDumpDownloadUri
    }
    local_evidence_directory = $localRunDirectory
    publish_evidence_root = $PublishEvidenceRoot
}
Write-JsonCreateNew -Path (Join-Path $localRunDirectory "capture-request.json") -Value $request

$collectorLog = Join-Path $localRunDirectory "procdump.log"
$arguments = @(
    "-accepteula",
    "-ma",
    "-h",
    "-n", $DumpCount.ToString(),
    $game.Id.ToString(),
    $localRunDirectory
)

Write-Host "Watching vanilla sb.exe PID $($game.Id) for a Windows hung-window event."
Write-Host "Leave this window open while reproducing the translocation bug."
Write-Host "Local evidence: $localRunDirectory"
& $procDump @arguments 2>&1 | Tee-Object -FilePath $collectorLog
$collectorExitCode = $LASTEXITCODE

$artifacts = @(
    Get-ChildItem -LiteralPath $localRunDirectory -File |
        Where-Object Name -ne "capture-result.json" |
        Sort-Object Name |
        ForEach-Object {
            [ordered]@{
                name = $_.Name
                length = $_.Length
                sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
            }
        }
)
$dumpCount = @($artifacts | Where-Object { $_.name -like "*.dmp" }).Count
$result = [ordered]@{
    schema_version = 1
    run_id = $runId
    status = if ($collectorExitCode -eq 0 -and $dumpCount -ge 1) { "captured" } else { "collector_failed" }
    completed_at_utc = [DateTime]::UtcNow.ToString("o")
    collector_exit_code = $collectorExitCode
    dump_count = $dumpCount
    artifacts = $artifacts
}
Write-JsonCreateNew -Path (Join-Path $localRunDirectory "capture-result.json") -Value $result

try {
    $publishedDirectory = Publish-EvidenceDirectory `
        -Source $localRunDirectory `
        -DestinationRoot $PublishEvidenceRoot `
        -RunId $runId
    if ($null -ne $publishedDirectory) {
        Write-Host "Published verified evidence: $publishedDirectory"
    }
}
catch {
    Write-Warning "The capture remains safe locally but could not be published: $($_.Exception.Message)"
}

if ($collectorExitCode -ne 0) {
    throw "ProcDump exited with code $collectorExitCode."
}
if ($dumpCount -lt 1) {
    throw "ProcDump exited without producing a dump."
}
Write-Host "Captured $dumpCount Shadowbane hang dump(s) without modifying the client."
