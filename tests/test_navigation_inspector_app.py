"""Panel tests exercise saved evidence without opening a visible window."""

import tkinter as tk
from pathlib import Path

import pytest
from test_navigation_inspector_snapshot import collector_with_route

from shadowbane_lab.navigation_inspector.app import InspectorApp
from shadowbane_lab.navigation_inspector.snapshot import Snapshot


@pytest.fixture
def panel():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    root.withdraw()
    app = InspectorApp(root, discover=lambda: ())
    try:
        yield app
    finally:
        app.close()


def test_saved_failure_controls_roundtrip_and_clear(panel, tmp_path):
    source = tmp_path / "failure.json"
    collector_with_route().snapshot().save(source)
    panel.load_path(source)
    assert panel.canvas.find_all()
    assert panel.events.get_children()
    assert "source_revision" in panel.details.get("1.0", "end")
    panel.radius.set("9")
    panel.apply_controls()
    assert panel.current_snapshot.clearance.character_radius == 9
    output = tmp_path / "reanalyzed.json"
    panel.save_to(output)
    assert Snapshot.load(output) == panel.current_snapshot
    with pytest.raises(FileExistsError):
        panel.save_to(output)
    panel.radius.set("nan")
    panel.apply_controls()
    assert "not applied" in panel.status.get()
    panel.return_live()
    assert panel.current_snapshot is None
    assert not panel.events.get_children()
    assert not panel.details.get("1.0", "end").strip()


def test_replay_does_not_publish_and_return_live_rebinds_controls(panel, tmp_path):
    class FakeChannel:
        target = type("Target", (), {"label": "fixture"})()
        settings = []

        def read_evidence(self):
            return collector_with_route().snapshot(), "producer lease expired"

        def set_controls(self, value):
            self.settings.append(value)

        def close(self):
            pass

    source = tmp_path / "failure.json"
    collector_with_route().snapshot().save(source)
    panel.channel = channel = FakeChannel()
    panel.load_path(Path(source))
    panel.radius.set("8")
    panel.apply_controls(1)
    assert not channel.settings
    panel.root.after_cancel(panel._poll_id)
    panel._poll()
    assert not channel.settings
    panel.return_live()
    assert channel.settings[-1].session_id == panel.current_snapshot.session_id
    assert panel.current_snapshot == panel._live


def test_exact_cli_lifetime_rejects_reused_pid_without_opening_channel():
    from types import SimpleNamespace
    from unittest.mock import Mock

    app = SimpleNamespace(
        targets=[SimpleNamespace(process_id=7, process_creation_filetime_utc=222)],
        status=Mock(),
        disconnect=Mock(),
    )
    InspectorApp.connect(app, 7, 111)
    app.disconnect.assert_not_called()
    app.status.set.assert_called_once_with("Choose the exact client to record.")


def test_launcher_cleanup_owns_runtime_and_pinned_process(tmp_path):
    import os
    import shutil
    import subprocess
    import sys

    if os.name != "nt":
        pytest.skip("Windows process handle regression")
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell unavailable")
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
        stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    script = tmp_path / "panel-ownership.ps1"
    script.write_text(
        r"""
param($Source, [int]$ChildId)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $Source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Parse failure' }
$ast.FindAll({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
}, $false) |
    ForEach-Object { Invoke-Expression $_.Extent.Text }
$child = Get-Process -Id $ChildId
$actualPath = $child.MainModule.FileName
$actualStart = $child.StartTime
$script:inspector = [pscustomobject]@{
    ProcessId = $ChildId; CreationDate = $actualStart; ExecutablePath = $actualPath
    CommandLine = '-m shadowbane_lab.navigation_inspector --pid 123456789'
}
function Get-CimInstance { param($ClassName, $Filter, $ErrorAction)
    if (-not $Filter) { $script:inspector }
}
$script:executable = 'C:\prepared-runtime\client\sb.exe'
$script:python = 'C:\unrelated-runtime\python.exe'
$script:pythonw = 'C:\unrelated-runtime\pythonw.exe'
Remove-StaleInspectorProcesses
$child.Refresh(); if ($child.HasExited) { throw 'Stopped another runtime' }
$script:python = $actualPath
$script:inspector.CreationDate = $actualStart.AddSeconds(-1)
Remove-StaleInspectorProcesses
$child.Refresh(); if ($child.HasExited) { throw 'Stopped a replacement lifetime' }
$script:inspector.CreationDate = $actualStart
Remove-StaleInspectorProcesses
if (-not $child.WaitForExit(5000)) { throw 'Did not stop owned stale panel' }
$child.Dispose()
""",
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-File",
                str(script),
                str(
                    Path(__file__).resolve().parents[1]
                    / "scripts/launch-wonderbane-navigation-inspector.ps1"
                ),
                str(child.pid),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        child.stdin.close()
        child.wait(10)
