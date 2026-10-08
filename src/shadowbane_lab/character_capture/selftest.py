"""Offline package acceptance: widgets, disabled hooks, resources and sealed evidence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def run_self_test(destination):
    import tkinter as tk

    from shadowbane_lab.client_observation.native_snapshot import (
        load_bundled_native_player_snapshot_profiles,
    )
    from shadowbane_lab.evidence import verify_bundle
    from shadowbane_vanilla_diagnostics.windows import WindowsProcessProbe

    from .dashboard import Dashboard
    from .input import WindowsGameInput
    from .recording import Recording

    checks = []
    with tempfile.TemporaryDirectory(prefix="sb-recorder-test-") as temporary:
        root = tk.Tk()
        root.withdraw()
        Dashboard(root, Path(temporary))
        root.update_idletasks()
        root.destroy()
        checks.append("dashboard-widgets")
        identity = WindowsProcessProbe().sample(os.getpid()).identity
        hook = WindowsGameInput(identity.process_id, identity.process_creation_filetime_utc)
        try:
            hook.start()  # Disabled throughout: never collect a user's input.
        finally:
            hook.stop()
        if hook.error or not hook.events.empty():
            raise RuntimeError("Disabled input observer smoke test failed.")
        checks.append("disabled-windows-hooks-start-stop")
        if not load_bundled_native_player_snapshot_profiles():
            raise RuntimeError("Missing packaged native profiles.")
        checks.append("native-profile-resources")
        if not Path(__file__).with_name("dictation.ps1").is_file():
            raise RuntimeError("Missing packaged dictation helper.")
        checks.append("dictation-helper-resource")
        recording = Recording(temporary, {"fixture": True})
        incident = recording.mark("fixture")
        recording.annotate(incident, intent="test", expected="seal", actual="verified")
        recording.finish("self-test")
        verify_bundle(recording.path / "evidence.zip")
        checks.append("capture-records-and-evidence-bundle")
    Path(destination).write_text(
        json.dumps({"passed": True, "checks": checks}, indent=2) + "\n", encoding="utf-8"
    )
    return 0
