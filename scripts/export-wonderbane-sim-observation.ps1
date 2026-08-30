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
        $progressionText = & $python -m shadowbane_lab.cli client observe-native-progression --json
        if ($LASTEXITCODE -ne 0) {
            throw "Native progression observation failed with exit code $LASTEXITCODE"
        }
        $trainingText = & $python -m shadowbane_lab.cli client observe-native-training --json
        if ($LASTEXITCODE -ne 0) {
            throw "Native training observation failed with exit code $LASTEXITCODE"
        }
        $vitalsText = & $python -m shadowbane_lab.cli client observe-native-player --json
        if ($LASTEXITCODE -ne 0) {
            throw "Native vitals observation failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    $payload = [ordered]@{
        schema_version = 1
        captured_at_utc = [DateTime]::UtcNow.ToString("o")
        progression = $progressionText | ConvertFrom-Json
        training = $trainingText | ConvertFrom-Json
        vitals = $vitalsText | ConvertFrom-Json
    }
    $payload | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    Write-Host "WonderBane simulator observation saved to $OutputPath"
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
