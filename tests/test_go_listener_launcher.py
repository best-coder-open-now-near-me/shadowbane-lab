"""Execute launcher argument construction with all process controls intercepted."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "start-wonderbane-go-listener.ps1"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(not POWERSHELL, reason="Windows PowerShell required")


@pytest.mark.parametrize("radius", [None, 175.5])
@pytest.mark.parametrize("bounded", [False, True])
def test_launcher_preserves_named_default_and_explicit_radius(tmp_path, radius, bounded):
    result, captured = invoke(tmp_path, radius, bounded)
    assert result.returncode == 0, result.stderr
    args = captured["arguments"]
    assert args[:5] == ["-u", "-m", "shadowbane_lab.cli", "client", "listen-go"]
    assert "--live" in args and "--json" in args
    assert ("--pve-continuous" in args) is (not bounded)
    if radius is None:
        assert "--pve-camp-radius" not in args
    else:
        assert args.count("--pve-camp-radius") == 1
        assert float(args[args.index("--pve-camp-radius") + 1]) == radius
    assert args[args.index("--pve-max-kills") + 1] == "3"
    assert captured["window_style"] == "Hidden"
    assert captured["working_directory"] == str(tmp_path)


@pytest.mark.parametrize("radius", [19, 1001])
def test_invalid_manual_radius_rejected_before_launch(tmp_path, radius):
    result, captured = invoke(tmp_path, radius, False)
    assert result.returncode != 0
    assert captured is None
    assert "PveCampRadius" in result.stderr


def invoke(tmp_path, radius, bounded):
    dummy = tmp_path / "fixture-file"
    dummy.write_text("fixture", encoding="ascii")
    capture = tmp_path / "arguments.json"
    options = {"RepositoryRoot": str(tmp_path), "PythonPath": str(dummy),
        "ClientProfile": str(dummy), "DestinationState": str(dummy), "WorldDef": str(dummy),
        "NamedDestinationOverrides": str(dummy), "PveClientProfile": str(dummy),
        "NavigationCacheDirectory": str(tmp_path), "ManagerManifest": str(dummy),
        "WorkerStateDirectory": str(tmp_path), "LogDirectory": str(tmp_path),
        "BoundedPve": bounded}
    if radius is not None:
        options["PveCampRadius"] = radius
    config = tmp_path / "options.json"
    config.write_text(json.dumps(options), encoding="utf-8")
    harness = tmp_path / "capture.ps1"
    harness.write_text(r'''param([string]$Launcher,[string]$Options,[string]$Capture)
$ErrorActionPreference='Stop'
function Get-CimInstance { param($ClassName,$Filter) return @() }
function Stop-Process { throw 'Unexpected real process stop attempt' }
function Start-Sleep { param($Milliseconds) }
function Start-Process {
 param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle,
       $RedirectStandardOutput,$RedirectStandardError,[switch]$PassThru)
 [ordered]@{arguments=@($ArgumentList);window_style=$WindowStyle;
   working_directory=$WorkingDirectory}|ConvertTo-Json -Depth 4|
   Set-Content -LiteralPath $Capture -Encoding UTF8
 $process=[pscustomobject]@{Id=12345;HasExited=$false}
 $process|Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
 return $process
}
$bound=@{}
$config=Get-Content -LiteralPath $Options -Raw|ConvertFrom-Json
foreach($property in $config.PSObject.Properties){$bound[$property.Name]=$property.Value}
& $Launcher @bound
''', encoding="utf-8")
    result = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(harness), "-Launcher", str(SCRIPT), "-Options", str(config),
        "-Capture", str(capture)], capture_output=True, text=True, timeout=30, check=False)
    return result, json.loads(capture.read_text("utf-8-sig")) if capture.exists() else None
