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
