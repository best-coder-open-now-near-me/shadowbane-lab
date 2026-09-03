from __future__ import annotations

import json
from pathlib import Path

import pytest

from shadowbane_lab.diagnostics import ProcessIdentity, collect_graphics_present_evidence
from tests.test_diagnostics_graphics import _present_pe, _status


def reviewed_status(tmp_path: Path):
    executable = tmp_path / "sb.exe"
    executable.write_bytes(_present_pe())
    identity = ProcessIdentity(42, 123456, str(executable))
    payload = _status(executable, identity)
    classification = payload["draw_classification"]
    classification["policy"].update(
        boundary_ownership="reviewed-client-done3d",
        candidate_retry="never-from-draw-state",
        planar_overlay="excluded-without-sealing-scene",
        late_world_after_ui="excluded-and-counted",
    )
    classification["latest"].update(
        boundary_mapping_verified=True,
        main_scene_start_count=1,
        main_scene_world_draw_count=60,
        main_scene_invalidated=False,
        composite_succeeded=True,
    )
    return executable, identity, payload


def assess(tmp_path, executable, identity, payload):
    status = tmp_path / "graphics-status.json"
    status.write_text(json.dumps(payload), encoding="utf-8")
    return collect_graphics_present_evidence(executable, identity, runtime_status_path=status)


@pytest.mark.parametrize("success", [False, True])
def test_current_frame_not_lifetime_success_controls_separation(tmp_path, success):
    executable, identity, payload = reviewed_status(tmp_path)
    payload["draw_classification"]["latest"]["composite_succeeded"] = success
    result = assess(tmp_path, executable, identity, payload)
    assert result.complete, result.failure
    assert result.report["assessment"]["world_ui_separation_observed"] is success


@pytest.mark.parametrize("field,value", [
    ("boundary_mapping_verified", False),
    ("boundary_mapping_verified", 1),
    ("main_scene_start_count", 0),
    ("main_scene_world_draw_count", 999),
    ("composite_succeeded", "true"),
])
def test_inconsistent_reviewed_boundary_is_rejected(tmp_path, field, value):
    executable, identity, payload = reviewed_status(tmp_path)
    payload["draw_classification"]["latest"][field] = value
    assert not assess(tmp_path, executable, identity, payload).complete


def test_invalidation_after_success_is_reported_without_claiming_separation(tmp_path):
    executable, identity, payload = reviewed_status(tmp_path)
    payload["draw_classification"]["latest"]["main_scene_invalidated"] = True
    result = assess(tmp_path, executable, identity, payload)
    assert result.complete, result.failure
    assert not result.report["assessment"]["world_ui_separation_observed"]


def test_first_draw_after_verified_boundary_can_be_late_world(tmp_path):
    executable, identity, payload = reviewed_status(tmp_path)
    latest = payload["draw_classification"]["latest"]
    latest["layers"]["world_opaque"] += 1
    latest["reasons"]["depth_writing_opaque"] += 1
    latest["draw_count"] += 1
    latest["world_draw_count"] += 1
    latest["late_world_draw_count"] = 1
    latest["first_late_world_draw_ordinal"] = latest["accepted_boundary_draw_ordinal"]
    latest["last_world_draw_ordinal"] = latest["accepted_boundary_draw_ordinal"]
    result = assess(tmp_path, executable, identity, payload)
    assert result.complete, result.failure
    assert not result.report["assessment"]["world_ui_separation_observed"]


def test_hidden_ui_boundary_can_follow_the_final_draw(tmp_path):
    executable, identity, payload = reviewed_status(tmp_path)
    latest = payload["draw_classification"]["latest"]
    latest["accepted_boundary_draw_ordinal"] = latest["draw_count"] + 1
    result = assess(tmp_path, executable, identity, payload)
    assert result.complete, result.failure


def test_draw_state_cannot_be_reintroduced_as_authority(tmp_path):
    executable, identity, payload = reviewed_status(tmp_path)
    payload["draw_classification"]["policy"]["candidate_retry"] = "until-depth-pass-accepts"
    assert not assess(tmp_path, executable, identity, payload).complete
