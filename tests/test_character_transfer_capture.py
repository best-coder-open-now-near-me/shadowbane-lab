from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from test_native_character_session import setup_session
from test_native_player_snapshot import _snapshot

from shadowbane_lab.character_capture import transfer as t
from shadowbane_lab.client_input.model import WindowBounds
from shadowbane_lab.client_input.window import WindowSnapshot
from shadowbane_lab.client_observation.native_character_config import ActiveCharacterError


def capture_setup(tmp_path):
    memory, session = setup_session(tmp_path)
    snapshot = replace(
        _snapshot(),
        process_id=memory.pid,
        process_creation_filetime_utc=memory.process_creation_filetime_utc,
        executable_path=memory.executable_path,
        executable_sha256=memory.executable_sha256,
        capture_started_at_filetime_utc=memory.process_creation_filetime_utc + 1,
        captured_at_filetime_utc=memory.process_creation_filetime_utc + 2,
    )
    reader = Mock()
    reader.observe.return_value = snapshot
    return memory, session, snapshot, reader


def window_for(session):
    return WindowSnapshot(
        executable_name="sb.exe",
        title="Shadowbane",
        client_bounds=WindowBounds(-100, 40, 80, 60),
        dpi_scale=1.5,
        is_foreground=True,
        is_visible=True,
        process_id=session.binding.process_id,
        window_handle=123,
        process_started_at_100ns=session.binding.process_creation_filetime_utc,
    )


def test_structured_capture_preserves_trained_values_and_marks_gaps(tmp_path):
    _, session, snapshot, reader = capture_setup(tmp_path)
    result = t.observe_character(session, reader)
    assert result["source"]["character_name"] == "testercle"
    assert result["native_snapshot"]["training"] == snapshot.as_dict()["training"]
    assert not result["database_import_ready"]
    assert "equipped_slots_templates_and_item_effects" in result["unresolved_structured_fields"]


@pytest.mark.parametrize("change", ["name", "server", "process", "training"])
def test_mixed_character_or_build_is_not_exported(tmp_path, change):
    memory, session, snapshot, reader = capture_setup(tmp_path)
    if change in ("name", "server"):

        def observe():
            memory.set_identity(
                "Other" if change == "name" else "testercle",
                "Other" if change == "server" else "Wonderbane",
            )
            return snapshot

        reader.observe.side_effect = observe
    elif change == "process":
        reader.observe.return_value = replace(snapshot, process_id=memory.pid + 1)
    else:
        reader.observe.side_effect = [
            snapshot,
            replace(snapshot, progression=replace(snapshot.progression, level=60)),
        ]
    with pytest.raises((ActiveCharacterError, t.CaptureError)):
        t.observe_character(session, reader)


def test_vital_regeneration_does_not_invalidate_build(tmp_path):
    _, session, snapshot, reader = capture_setup(tmp_path)
    reader.observe.side_effect = [
        snapshot,
        replace(snapshot, vitals=replace(snapshot.vitals, current_health=40)),
    ]
    assert t.observe_character(session, reader)["native_snapshot"]["vitals"]["current_health"] == 40


def test_bundle_keeps_original_evidence_and_valid_hashes(tmp_path):
    _, session, _, reader = capture_setup(tmp_path)
    character = t.observe_character(session, reader)
    bundle = t.CaptureBundle(tmp_path / "captures", character)
    original = (bundle.path / "character.json").read_bytes()
    with pytest.raises(FileExistsError):
        bundle.add_file("character.json", b"replacement")
    assert (bundle.path / "character.json").read_bytes() == original
    bundle.finish("review_required")
    manifest = json.loads((bundle.path / "manifest.json").read_text())
    assert manifest["database_import_ready"] is False
    assert manifest["capture_status"] == "review_required"
    assert manifest["files"][0]["sha256"] == hashlib.sha256(original).hexdigest()
    assert not (bundle.path / ".manifest.tmp").exists()
    second = t.CaptureBundle(tmp_path / "captures", character)
    assert second.path != bundle.path
    with pytest.raises(ValueError):
        bundle.add_file("../outside.json", b"bad")


def test_frame_is_cropped_to_bound_game_at_physical_coordinates(tmp_path):
    _, session, _, _ = capture_setup(tmp_path)
    window = window_for(session)
    inspector = Mock()
    inspector.inspect.return_value = window
    grab = Mock(return_value=Image.new("RGB", (80, 60), "blue"))
    png, dimensions = t.capture_frame(session, inspector, grab)
    grab.assert_called_once_with(bbox=(-100, 40, -20, 100), all_screens=True)
    assert png.startswith(b"\x89PNG")
    assert dimensions == {"width": 80, "height": 60}


@pytest.mark.parametrize("change", ["pid", "lifetime", "foreground", "missing"])
def test_wrong_window_is_rejected_before_screenshot(tmp_path, change):
    _, session, _, _ = capture_setup(tmp_path)
    window = window_for(session)
    changes = {
        "pid": {"process_id": 999},
        "lifetime": {"process_started_at_100ns": 1},
        "foreground": {"is_foreground": False},
    }
    inspector = Mock()
    inspector.inspect.return_value = (
        None if change == "missing" else replace(window, **changes[change])
    )
    grab = Mock()
    with pytest.raises(t.CaptureError, match="foreground"):
        t.capture_frame(session, inspector, grab)
    grab.assert_not_called()


@pytest.mark.parametrize("change", ["window", "character", "black", "dimensions"])
def test_untrustworthy_frame_is_not_returned(tmp_path, change):
    memory, session, _, _ = capture_setup(tmp_path)
    window = window_for(session)
    inspector = Mock()
    inspector.inspect.side_effect = [
        window,
        replace(window, window_handle=321) if change == "window" else window,
    ]

    def grab(**_):
        if change == "character":
            memory.set_identity("Other", "Wonderbane")
        return Image.new(
            "RGB",
            (10, 10) if change == "dimensions" else (80, 60),
            "black" if change == "black" else "blue",
        )

    with pytest.raises((t.CaptureError, ActiveCharacterError)):
        t.capture_frame(session, inspector, grab)


def patch_run(tmp_path, monkeypatch, *, character="testercle", native_only=True):
    memory, _, _, reader = capture_setup(tmp_path)
    monkeypatch.setattr(t.WindowsReadOnlyProcessMemory, "open_unique", lambda _: memory)
    monkeypatch.setattr(t, "NativePlayerSnapshotReader", lambda *_: reader)
    args = SimpleNamespace(
        pid=None,
        character=character,
        server="Wonderbane",
        output_root=tmp_path / "captures",
        native_only=native_only, guided_only=True,
        delay=3,
    )
    return memory, args


def test_native_only_bundle_is_explicitly_incomplete(tmp_path, monkeypatch):
    memory, args = patch_run(tmp_path, monkeypatch)
    assert t.run_capture(args) == 0
    (manifest_path,) = args.output_root.glob("*/manifest.json")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["capture_status"] == "review_required"
    assert manifest["database_import_ready"] is False
    assert manifest["sections"] == {}
    assert {row["path"] for row in manifest["files"]} == {"character.json", "character-final.json"}
    assert memory.closed


def test_wrong_expected_character_does_not_create_bundle(tmp_path, monkeypatch):
    memory, args = patch_run(tmp_path, monkeypatch, character="different")
    with pytest.raises(t.CaptureError, match="Expected"):
        t.run_capture(args)
    assert not args.output_root.exists()
    assert memory.closed


def test_interruption_preserves_capture_without_claiming_completion(tmp_path, monkeypatch):
    memory, args = patch_run(tmp_path, monkeypatch, native_only=False)

    def interrupt(bundle, *_):
        bundle.add_file("001-equipment-item.png", b"synthetic test evidence", kind="screenshot")
        bundle.save()
        raise KeyboardInterrupt()

    monkeypatch.setattr(t, "guided_evidence", interrupt)
    with pytest.raises(KeyboardInterrupt):
        t.run_capture(args)
    (manifest_path,) = args.output_root.glob("*/manifest.json")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["capture_status"] == "interrupted"
    assert manifest["database_import_ready"] is False
    assert len(manifest["files"]) == 2
    assert memory.closed


@pytest.mark.parametrize(
    "args",
    [
        ["--character", "x", "--delay", "0"],
        ["--character", "x", "--pid", "-1"],
        ["--character", " "],
    ],
)
def test_invalid_cli_arguments_fail_before_process_open(args, monkeypatch):
    open_process = Mock()
    monkeypatch.setattr(t.WindowsReadOnlyProcessMemory, "open_unique", open_process)
    with pytest.raises(SystemExit):
        t.main(args)
    open_process.assert_not_called()


def test_guided_capture_retries_focus_and_records_section_coverage(tmp_path, monkeypatch):
    from contextlib import nullcontext

    _, session, _, reader = capture_setup(tmp_path)
    bundle = t.CaptureBundle(tmp_path / "captures", t.observe_character(session, reader))
    answers = iter(["first try", "stats tooltip", "/done", "/done", "/done", "/done"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(t.time, "sleep", lambda _: None)
    monkeypatch.setattr(t, "_physical_pixels", nullcontext)
    monkeypatch.setattr(t, "WindowsForegroundWindowInspector", Mock)
    frames = Mock(
        side_effect=[
            t.CaptureError("wrong foreground"),
            (b"synthetic PNG", {"width": 80, "height": 60}),
        ]
    )
    monkeypatch.setattr(t, "capture_frame", frames)
    t.guided_evidence(bundle, session, 3)
    manifest = json.loads((bundle.path / "manifest.json").read_text())
    assert len(manifest["files"]) == 2
    assert manifest["files"][1]["label"] == "stats tooltip"
    assert manifest["sections"]["character-sheet"]["images"] == 1
    assert manifest["sections"]["equipment-item"]["status"] == "not_captured"


def test_final_training_change_marks_saved_bundle_failed(tmp_path, monkeypatch):
    memory, args = patch_run(tmp_path, monkeypatch, native_only=False)

    def change_after_pictures(*_):
        # The real reader still supplies individually stable snapshots; the
        # capture must compare the final build against its initial observation.
        changed = replace(
            _snapshot(),
            process_id=memory.pid,
            process_creation_filetime_utc=memory.process_creation_filetime_utc,
            executable_path=memory.executable_path,
            executable_sha256=memory.executable_sha256,
            capture_started_at_filetime_utc=memory.process_creation_filetime_utc + 1,
            captured_at_filetime_utc=memory.process_creation_filetime_utc + 2,
            progression=replace(_snapshot().progression, unspent_training_points=0),
        )
        reader.observe.return_value = changed

    reader = t.NativePlayerSnapshotReader()
    monkeypatch.setattr(t, "guided_evidence", change_after_pictures)
    with pytest.raises(t.CaptureError, match="Build changed"):
        t.run_capture(args)
    (manifest_path,) = args.output_root.glob("*/manifest.json")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["capture_status"] == "failed"
    assert not manifest["database_import_ready"]
    assert memory.closed

