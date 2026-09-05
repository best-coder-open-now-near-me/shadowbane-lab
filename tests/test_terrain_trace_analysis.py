from __future__ import annotations

import copy
import json

import pytest

from shadowbane_lab.diagnostics import terrain_trace_analysis as analysis


def _texture(unit: int, *, enabled: int, binding: int, size: int) -> dict:
    return {
        "unit": unit,
        "enabled": enabled,
        "binding": binding,
        "level": [size, size, 32828 if unit == 1 else 6407, 0],
        "sampler": [9987, 9729, 33071, 33071],
        "env_mode": 34160,
        "combine": [7681] * 16,
        "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    }


def _draw(ordinal: int, return_rva: int | None, *, blend: int, mask: int) -> dict:
    state = [1, 1, 515, 1, 518, blend, 770, 771, 1, 1, 1]
    return {
        "ordinal": ordinal,
        "qpc": 110 + ordinal,
        "submission": 4,
        "caller_rva": 0x1A0765,
        "mode": 4,
        "first": 0,
        "count": 24,
        "index_type": 5123,
        "list": 0,
        "list_source_stable": True,
        "client_stack_rvas": [] if return_rva is None else [return_rva],
        "state": state,
        "alpha_ref": [0.5],
        "color": [1, 1, 1, 1],
        "model_view": [1] * 16,
        "projection": [1] * 16,
        "viewport": [0, 0, 1920, 955],
        "active_unit": 33984,
        "active_unit_restored": True,
        "textures": [
            _texture(0, enabled=1, binding=1243, size=256),
            _texture(1, enabled=mask, binding=1284 if mask else 0, size=64 if mask else 0),
        ],
    }


def _payload() -> dict:
    draws = [
        _draw(1, 0x4F1772, blend=0, mask=0),
        _draw(2, 0x4F1864, blend=1, mask=1),
        _draw(3, None, blend=1, mask=1),
    ]
    return {
        "schema_version": 1,
        "extension_version": "1.6.12",
        "process_id": 123,
        "process_creation_filetime_utc": 456,
        "executable_sha256": analysis.PROFILE_EXECUTABLE_SHA256,
        "sequence": 1,
        "qpc_frequency": 1000,
        "requested_qpc": 100,
        "start_qpc": 105,
        "end_qpc": 150,
        "query_ticks": 20,
        "unit_count": 2,
        "omitted_units": 0,
        "helpers_available": True,
        "retained_submissions": 3,
        "observed_submissions": 3,
        "capacity_skipped": 0,
        "unsafe_query_skipped": 0,
        "query_budget_skipped": 0,
        "reviewed_interval_complete": True,
        "main_clear_seen": True,
        "done3d_seen": True,
        "extra_depth_clear": False,
        "context_or_thread_mismatch": False,
        "scope": {"pixels_read": False, "texture_bytes_read": False},
        "draws": draws,
    }


@pytest.mark.parametrize("version", ["1.6.12", "1.6.13"])
def test_analyzer_attributes_reviewed_terrain_roles_without_claiming_asset_ids(version):
    payload = _payload()
    payload["extension_version"] = version
    result = analysis.analyze_terrain_trace(payload)
    assert result["status"] == "terrain_draws_attributed"
    assert result["terrain_draw_count"] == 2
    assert result["unmatched_draw_count"] == 1
    assert result["layer_mask_findings"] == {
        "draw_count": 1,
        "all_enabled_masks_clamp_to_edge": True,
        "all_enabled_masks_use_linear_magnification": True,
    }
    assert [site["role"] for site in result["call_sites"]] == [
        "base_terrain",
        "masked_terrain_layer",
    ]
    assert result["repair_authorized"] is False
    assert "not cache/archive IDs" in result["remaining_boundary"]
    assert result["call_sites"][0]["render_states"]["groups"][0]["state"] == tuple(
        _payload()["draws"][0]["state"]
    )


def test_analyzer_fails_closed_for_unknown_executable():
    payload = _payload()
    payload["executable_sha256"] = "0" * 64
    with pytest.raises(
        analysis.TerrainTraceAnalysisError, match="no exact reviewed terrain profile"
    ):
        analysis.analyze_terrain_trace(payload)


def test_analyzer_reports_call_site_state_conflicts():
    payload = _payload()
    payload["draws"][1]["state"][5] = 0
    result = analysis.analyze_terrain_trace(payload)
    assert result["status"] == "profile_conflict"
    assert result["conflict_count"] == 1
    assert "blend state" in result["conflicts"][0]


@pytest.mark.parametrize("field,value", [("submission", 3), ("caller_rva", 0), ("mode", 5)])
def test_analyzer_rejects_contradictory_submission_signatures(field, value):
    payload = _payload()
    payload["draws"][1][field] = value
    result = analysis.analyze_terrain_trace(payload)
    assert result["status"] == "profile_conflict"
    assert "submission signature" in result["conflicts"][0]


def test_analyzer_requires_both_reviewed_roles():
    payload = _payload()
    payload["draws"][1]["client_stack_rvas"] = []
    result = analysis.analyze_terrain_trace(payload)
    assert result["status"] == "profile_conflict"
    assert "missing reviewed terrain roles" in result["conflicts"][0]


def test_analyzer_rejects_ambiguous_call_stack():
    payload = _payload()
    payload["draws"][2]["client_stack_rvas"] = [0x4F1772, 0x4F1864]
    result = analysis.analyze_terrain_trace(payload)
    assert result["status"] == "profile_conflict"
    assert "multiple terrain return sites" in result["conflicts"][0]


def test_analyzer_reports_sampler_evidence_without_authorizing_a_repair():
    payload = _payload()
    payload["draws"][1]["textures"][1]["sampler"][2] = 10497
    result = analysis.analyze_terrain_trace(payload)
    assert result["status"] == "terrain_draws_attributed"
    assert result["layer_mask_findings"]["all_enabled_masks_clamp_to_edge"] is False
    assert result["repair_authorized"] is False


def test_analyzer_rejects_incomplete_interval():
    payload = _payload()
    payload["done3d_seen"] = False
    result = analysis.analyze_terrain_trace(payload)
    assert result["status"] == "profile_conflict"
    assert result["trace_assessment"]["reviewed_interval_complete"] is False


def test_analyzer_rejects_unconfirmed_terrain_state_restoration():
    payload = _payload()
    payload["draws"][1]["active_unit_restored"] = False
    result = analysis.analyze_terrain_trace(payload)
    assert result["status"] == "profile_conflict"
    assert "restoration was not confirmed" in result["conflicts"][0]


def test_analyzer_keeps_exact_conflict_counts_when_details_are_bounded():
    payload = _payload()
    payload["draws"] = [_draw(1, 0x4F1772, blend=0, mask=0)] + [
        _draw(ordinal, 0x4F1864, blend=0, mask=1) for ordinal in range(2, 32)
    ]
    payload["retained_submissions"] = payload["observed_submissions"] = 31
    result = analysis.analyze_terrain_trace(payload)
    assert result["conflict_count"] == 30
    assert len(result["conflicts"]) == 20


def test_analyzer_rejects_nonfinite_texture_matrix():
    payload = _payload()
    payload["draws"][1]["textures"][1]["matrix"][0] = None
    with pytest.raises(analysis.TerrainTraceAnalysisError, match="nonnumeric"):
        analysis.analyze_terrain_trace(payload)


def test_analyzer_does_not_modify_trace():
    payload = _payload()
    original = copy.deepcopy(payload)
    analysis.analyze_terrain_trace(payload)
    assert payload == original


def test_analyzer_cli_reads_existing_trace_without_rewriting_it(tmp_path, capsys):
    path = tmp_path / "terrain-trace.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    before = path.read_bytes()
    assert analysis.main([str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["terrain_draw_count"] == 2
    assert path.read_bytes() == before


def test_analyzer_cli_reports_unknown_profile_without_rewriting_trace(tmp_path, capsys):
    payload = _payload()
    payload["executable_sha256"] = "0" * 64
    path = tmp_path / "unknown-build.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()
    assert analysis.main([str(path)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "not_analyzed"
    assert path.read_bytes() == before


@pytest.mark.parametrize("enriched", [False, True])
def test_existing_consumer_accepts_additive_transmission_state(enriched):
    payload = _payload()
    original = copy.deepcopy(payload)
    if enriched:
        for draw in payload["draws"]:
            draw["transmission_state"] = {
                "unavailable": -1,
                "program": -1,
                "framebuffer": 0,
                "blend_rgb_alpha_factors_equations": [770, 771, 1, 0, 32774, 32774],
                "stencil_enable_front_back": [0, 519, 255, 0, 255, 7680, 7680, 7680]
                + [-1] * 7,
                "color_write_rgba": [1, 1, 1, 0],
            }
    assert analysis.analyze_terrain_trace(payload) == analysis.analyze_terrain_trace(original)
    assert [row["state"] for row in payload["draws"]] == [
        row["state"] for row in original["draws"]
    ]
