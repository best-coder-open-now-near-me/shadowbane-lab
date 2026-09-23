param(
    [string]$OutputPath = "\\VBOXSVR\codexdiag\wonderbane-sim-observation.json"
)

$ErrorActionPreference = "Stop"
$repo = "\\VBOXSVR\codexrepo"
$python = Join-Path $env:USERPROFILE "shadowbane-lab\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Shadowbane lab Python runtime was not found at $python"
}
if (-not (Test-Path -LiteralPath $repo -PathType Container)) {
    throw "Shared repository was not found at $repo"
}

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repo "src"
    Push-Location $repo
    try {
        $snapshotText = & $python -m shadowbane_lab.cli client observe-native-snapshot --json
        if ($LASTEXITCODE -ne 0) {
            throw "Native player snapshot failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    $payload = $snapshotText | ConvertFrom-Json
    if (-not $payload.ok -or -not $payload.snapshot_token -or -not $payload.process_identity) {
        throw "Native player snapshot did not contain exact identity and token evidence"
    }

    $payload | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    Write-Host "WonderBane simulator observation saved to $OutputPath"
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
