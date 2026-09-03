"""Fail-closed, repeatable attribution of a captured terrain draw trace."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from shadowbane_lab.graphics_lab.control import GraphicsControlTarget

from .terrain_trace import TRACE_VERSIONS, assess_trace, read_local_trace

PROFILE_ID = "wonderbane-55fbad5f-custom-textured-terrain-v1"
PROFILE_EXECUTABLE_SHA256 = (
    "a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8"
)
PROFILE_SUBMISSION = 4  # glDrawElements
PROFILE_MODE = 4  # GL_TRIANGLES
PROFILE_CALLER_RVA = 0x1A0765
PROFILE_CALL_SITES = (
    {
        "role": "base_terrain",
        "return_rva": 0x4F1772,
        "expected_blend_enabled": 0,
        "expected_mask_unit_enabled": 0,
    },
    {
        "role": "masked_terrain_layer",
        "return_rva": 0x4F1864,
        "expected_blend_enabled": 1,
        "expected_mask_unit_enabled": 1,
    },
)
_MAX_GROUPS = 32
_CLAMP_TO_EDGE = 0x812F
_LINEAR = 0x2601


class TerrainTraceAnalysisError(ValueError):
    """Raised when trace attribution cannot fail closed."""


def _integer(value: object, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TerrainTraceAnalysisError(f"{field} must be an integer >= {minimum}")
    return value


def _integers(value: object, field: str, length: int) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise TerrainTraceAnalysisError(f"{field} must contain {length} integers")
    return tuple(_integer(item, f"{field}[]") for item in value)


def _integer_list(value: object, field: str, maximum: int = 24) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise TerrainTraceAnalysisError(f"{field} must be a bounded integer list")
    return tuple(_integer(item, f"{field}[]") for item in value)


def _numbers(value: object, field: str, length: int) -> tuple[int | float, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise TerrainTraceAnalysisError(f"{field} must contain {length} numbers")
    result: list[int | float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise TerrainTraceAnalysisError(f"{field} contains a nonfinite or nonnumeric value")
        result.append(item)
    return tuple(result)


def _trace_assessment(payload: dict[str, Any]) -> dict[str, Any]:
    process_id = _integer(payload.get("process_id"), "process_id", 1)
    creation = _integer(
        payload.get("process_creation_filetime_utc"),
        "process_creation_filetime_utc",
        1,
    )
    digest = payload.get("executable_sha256")
    if not isinstance(digest, str):
        raise TerrainTraceAnalysisError("executable_sha256 must be text")
    requested = _integer(payload.get("requested_qpc"), "requested_qpc", 1)
    target = GraphicsControlTarget(
        process_id,
        creation,
        Path("unopened-sb.exe"),
        digest,
        "unused",
        Path("unopened-graphics-status.json"),
    )
    return assess_trace(payload, target, requested)


def _groups(counter: Counter[tuple[Any, ...]], names: tuple[str, ...]) -> dict[str, Any]:
    ordered = sorted(counter.items(), key=lambda item: (-item[1], repr(item[0])))
    return {
        "distinct_count": len(ordered),
        "truncated": len(ordered) > _MAX_GROUPS,
        "groups": [
            {"count": count, **dict(zip(names, key, strict=True))}
            for key, count in ordered[:_MAX_GROUPS]
        ],
    }


def _texture_key(texture: object, field: str) -> tuple[Any, ...]:
    if not isinstance(texture, dict):
        raise TerrainTraceAnalysisError(f"{field} must be an object")
    combine = texture.get("combine")
    if combine is not None:
        combine = _integers(combine, f"{field}.combine", 16)
    return (
        _integer(texture.get("unit"), f"{field}.unit"),
        _integer(texture.get("enabled"), f"{field}.enabled"),
        _integer(texture.get("binding"), f"{field}.binding"),
        _integers(texture.get("level"), f"{field}.level", 4),
        _integers(texture.get("sampler"), f"{field}.sampler", 4),
        _integer(texture.get("env_mode"), f"{field}.env_mode"),
        combine,
    )


def _summarize_site(site: dict[str, Any], draws: list[dict[str, Any]]) -> dict[str, Any]:
    states: Counter[tuple[Any, ...]] = Counter()
    counts: Counter[tuple[Any, ...]] = Counter()
    textures: Counter[tuple[Any, ...]] = Counter()
    matrices: Counter[tuple[Any, ...]] = Counter()
    conflicts: list[str] = []
    for draw in draws:
        ordinal = _integer(draw.get("ordinal"), "draw.ordinal", 1)
        state = _numbers(draw.get("state"), f"draw[{ordinal}].state", 11)
        states[(state,)] += 1
        if draw.get("active_unit_restored") is not True:
            conflicts.append(f"draw {ordinal} texture-unit restoration was not confirmed")
        counts[(_integer(draw.get("count"), f"draw[{ordinal}].count"),)] += 1
        draw_textures = draw.get("textures")
        if not isinstance(draw_textures, list) or len(draw_textures) < 2:
            raise TerrainTraceAnalysisError("terrain analysis requires captured units zero and one")
        for unit, texture in enumerate(draw_textures):
            textures[_texture_key(texture, f"draw[{ordinal}].textures[{unit}]")] += 1
            if not isinstance(texture, dict):
                raise TerrainTraceAnalysisError("texture entry must be an object")
            matrix = _numbers(texture.get("matrix"), f"draw[{ordinal}].texture_matrix", 16)
            matrices[(unit, matrix)] += 1
        if state[5] != site["expected_blend_enabled"]:
            conflicts.append(f"draw {ordinal} blend state contradicts the reviewed role")
        mask = draw_textures[1]
        if not isinstance(mask, dict) or mask.get("enabled") != site["expected_mask_unit_enabled"]:
            conflicts.append(f"draw {ordinal} mask-unit state contradicts the reviewed role")
    return {
        "role": site["role"],
        "return_rva": site["return_rva"],
        "draw_count": len(draws),
        "ordinal_min": min((draw["ordinal"] for draw in draws), default=None),
        "ordinal_max": max((draw["ordinal"] for draw in draws), default=None),
        "index_counts": _groups(counts, ("index_count",)),
        "render_states": _groups(states, ("state",)),
        "texture_states": _groups(
            textures,
            ("unit", "enabled", "binding", "level", "sampler", "env_mode", "combine"),
        ),
        "texture_matrices": _groups(matrices, ("unit", "matrix")),
        "conflict_count": len(conflicts),
        "conflicts": conflicts[:20],
    }


def analyze_terrain_trace(payload: object) -> dict[str, Any]:
    """Attribute terrain draws using one exact reviewed build/call-site profile."""

    if not isinstance(payload, dict):
        raise TerrainTraceAnalysisError("trace must be an object")
    assessment = _trace_assessment(payload)
    if payload.get("executable_sha256") != PROFILE_EXECUTABLE_SHA256:
        raise TerrainTraceAnalysisError("no exact reviewed terrain profile for this executable")
    if payload.get("extension_version") not in TRACE_VERSIONS:
        raise TerrainTraceAnalysisError(
            "trace extension does not match the reviewed terrain profile"
        )
    draws = payload.get("draws")
    if not isinstance(draws, list):
        raise TerrainTraceAnalysisError("trace draws must be a list")

    by_rva = {site["return_rva"]: (site, []) for site in PROFILE_CALL_SITES}
    conflicts: list[str] = []
    if not assessment["reviewed_interval_complete"]:
        conflicts.append("reviewed terrain interval was incomplete")
    matched_ordinals: set[int] = set()
    for draw in draws:
        if not isinstance(draw, dict):
            raise TerrainTraceAnalysisError("every draw must be an object")
        ordinal = _integer(draw.get("ordinal"), "draw.ordinal", 1)
        stack = _integer_list(draw.get("client_stack_rvas"), f"draw[{ordinal}].client_stack_rvas")
        matched = [rva for rva in by_rva if rva in stack]
        if len(matched) > 1:
            conflicts.append(f"draw {ordinal} matched multiple terrain return sites")
            continue
        if not matched:
            continue
        matched_ordinals.add(ordinal)
        _, site_draws = by_rva[matched[0]]
        site_draws.append(draw)
        observed = (
            _integer(draw.get("submission"), f"draw[{ordinal}].submission"),
            _integer(draw.get("caller_rva"), f"draw[{ordinal}].caller_rva"),
            _integer(draw.get("mode"), f"draw[{ordinal}].mode"),
        )
        if observed != (PROFILE_SUBMISSION, PROFILE_CALLER_RVA, PROFILE_MODE):
            conflicts.append(f"draw {ordinal} contradicts the reviewed submission signature")

    site_reports = [_summarize_site(site, site_draws) for site, site_draws in by_rva.values()]
    site_conflict_count = sum(report["conflict_count"] for report in site_reports)
    submission_conflict_count = len(conflicts)
    conflicts.extend(conflict for report in site_reports for conflict in report["conflicts"])
    missing_roles = [report["role"] for report in site_reports if report["draw_count"] == 0]
    if missing_roles:
        conflicts.append("missing reviewed terrain roles: " + ", ".join(missing_roles))

    layer_draws = by_rva[0x4F1864][1]
    layer_masks = [draw["textures"][1] for draw in layer_draws]
    masks_clamp = bool(layer_masks) and all(
        mask["enabled"] == 1
        and mask["sampler"][2] == _CLAMP_TO_EDGE
        and mask["sampler"][3] == _CLAMP_TO_EDGE
        for mask in layer_masks
    )
    masks_linear = bool(layer_masks) and all(mask["sampler"][1] == _LINEAR for mask in layer_masks)
    return {
        "schema_version": 1,
        "status": "profile_conflict" if conflicts else "terrain_draws_attributed",
        "profile_id": PROFILE_ID,
        "source_identity": {
            "executable_sha256": payload["executable_sha256"],
            "extension_version": payload["extension_version"],
            "process_id": payload["process_id"],
            "process_creation_filetime_utc": payload["process_creation_filetime_utc"],
        },
        "trace_sequence": payload["sequence"],
        "trace_assessment": assessment,
        "terrain_draw_count": len(matched_ordinals),
        "unmatched_draw_count": len(draws) - len(matched_ordinals),
        "call_sites": site_reports,
        "layer_mask_findings": {
            "draw_count": len(layer_draws),
            "all_enabled_masks_clamp_to_edge": masks_clamp,
            "all_enabled_masks_use_linear_magnification": masks_linear,
        },
        "conflict_count": submission_conflict_count + site_conflict_count + bool(missing_roles),
        "conflicts": conflicts[:20],
        "repair_authorized": False,
        "remaining_boundary": (
            "Context-local GL bindings are not cache/archive IDs. Correlate attributed terrain "
            "bindings to reviewed cache records and inspect neighboring mask data before repair."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    options = parser.parse_args(argv)
    try:
        result = analyze_terrain_trace(read_local_trace(options.trace))
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "not_analyzed", "error": str(error)}))
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "terrain_draws_attributed" else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["TerrainTraceAnalysisError", "analyze_terrain_trace"]
