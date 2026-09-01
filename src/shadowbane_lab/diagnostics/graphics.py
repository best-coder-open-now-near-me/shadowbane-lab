"""Exact static and runtime evidence for the client frame-present path."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shadowbane_lab.client_extension.bootstrap_inspection import inspect_pe_imports
from shadowbane_lab.integrity import load_strict_json, validate_finite_json, validate_sha256

from .model import DiagnosticError
from .process import ProcessIdentity

GRAPHICS_PRESENT_EVIDENCE_SCHEMA_VERSION = 1
GRAPHICS_RUNTIME_STATUS_SCHEMA_VERSION = 2
_RUNTIME_PROFILES = frozenset({"diagnostics-only", "full-renderer"})

_PRESENT_ENTRY_POINTS = {
    ("gdi32.dll", "SwapBuffers"): "gdi32-swap-buffers",
    ("opengl32.dll", "wglSwapLayerBuffers"): "opengl32-wgl-swap-layer-buffers",
}


@dataclass(frozen=True, slots=True)
class GraphicsPresentCollection:
    report: dict[str, object]
    complete: bool
    failure: str | None = None
    warnings: tuple[str, ...] = ()


def collect_graphics_present_evidence(
    executable_path: Path,
    process_identity: ProcessIdentity,
    *,
    runtime_status_path: Path | None = None,
) -> GraphicsPresentCollection:
    """Collect exact PE imports and, when requested, identity-bound runtime status."""

    try:
        executable = executable_path.read_bytes()
    except OSError as exc:
        raise DiagnosticError(
            f"could not read the live executable for graphics evidence: {executable_path}"
        ) from exc
    imports = inspect_pe_imports(executable)
    image = _mapping(imports.get("executable"), "PE executable evidence")
    executable_sha256 = validate_sha256(image.get("sha256"), "live executable sha256")
    candidates = tuple(
        sorted(
            (
                {
                    "candidate_id": candidate_id,
                    "iat_rva": item["iat_rva"],
                    "library": item["library"],
                    "ordinal": item["ordinal"],
                    "symbol": item["symbol"],
                }
                for item in imports["imports"]
                if (
                    candidate_id := _PRESENT_ENTRY_POINTS.get(
                        (str(item["library"]).casefold(), item["symbol"])
                    )
                )
            ),
            key=lambda item: (str(item["candidate_id"]), int(item["iat_rva"])),
        )
    )
    runtime, runtime_complete, runtime_failure, runtime_warnings = _runtime_evidence(
        runtime_status_path,
        process_identity,
        executable_sha256,
        candidates,
    )
    active_route = runtime.get("active_present_entry")
    active_route_authority = (
        "runtime-observed-exact-process"
        if runtime.get("state") == "accepted" and active_route is not None
        else "unresolved"
    )
    graphics_context = runtime.get("graphics_context")
    scene_color_capture = runtime.get("scene_color_capture")
    draw_classification = runtime.get("draw_classification")
    depth_edge_ready = bool(
        active_route_authority == "runtime-observed-exact-process"
        and isinstance(graphics_context, dict)
        and graphics_context.get("context_observed") is True
        and isinstance(graphics_context.get("depth_bits"), int)
        and graphics_context["depth_bits"] > 0
        and graphics_context.get("depth_texture_supported") is True
        and _bounded_text(graphics_context.get("glsl_version"), 256)
    )
    scene_color_ready = bool(
        runtime.get("state") == "accepted"
        and isinstance(scene_color_capture, dict)
        and scene_color_capture.get("state") == "active"
        and isinstance(scene_color_capture.get("capture_count"), int)
        and scene_color_capture["capture_count"] > 0
    )
    world_ui_separation_observed = bool(
        runtime.get("state") == "accepted"
        and isinstance(draw_classification, dict)
        and draw_classification.get("state") == "active"
        and isinstance(draw_classification.get("classified_frame_count"), int)
        and draw_classification["classified_frame_count"] > 0
        and isinstance(draw_classification.get("latest"), dict)
        and draw_classification["latest"].get("boundary_count") == 1
        and draw_classification["latest"].get("late_world_draw_count") == 0
    )
    fixed_function_refresh_bounded = bool(
        world_ui_separation_observed
        and isinstance(draw_classification.get("latest"), dict)
        and draw_classification["latest"].get("fixed_function_refresh_count")
        in {0, 1}
    )
    report: dict[str, object] = {
        "schema_version": GRAPHICS_PRESENT_EVIDENCE_SCHEMA_VERSION,
        "authorization": "evidence_only_no_hook_or_patch_authority",
        "process_identity": process_identity.as_dict(),
        "executable": {
            "path": str(executable_path),
            "sha256": executable_sha256,
            "size_bytes": image["length"],
            "machine": image["machine"],
            "pointer_size": image["pointer_size"],
        },
        "searched_entry_points": [
            {"library": library, "symbol": symbol}
            for library, symbol in sorted(_PRESENT_ENTRY_POINTS)
        ],
        "pe_import_count": len(imports["imports"]),
        "present_candidates": list(candidates),
        "runtime_status": runtime,
        "assessment": {
            "static_import_authority": "exact-live-executable-bytes",
            "candidate_count": len(candidates),
            "candidate_status": (
                "none" if not candidates else "single" if len(candidates) == 1 else "multiple"
            ),
            "active_route_authority": active_route_authority,
            "depth_edge_prerequisites_observed": depth_edge_ready,
            "scene_color_capture_observed": scene_color_ready,
            "world_ui_separation_observed": world_ui_separation_observed,
            "fixed_function_refresh_bounded": fixed_function_refresh_bounded,
            "unresolved_mapping_blocks_dependent_renderer_work": not depth_edge_ready,
        },
    }
    validate_finite_json(report)
    return GraphicsPresentCollection(
        report,
        complete=runtime_complete,
        failure=runtime_failure,
        warnings=runtime_warnings,
    )


def _runtime_evidence(
    path: Path | None,
    identity: ProcessIdentity,
    executable_sha256: str,
    candidates: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], bool, str | None, tuple[str, ...]]:
    if path is None:
        return (
            {
                "state": "not-requested",
                "active_present_entry": None,
                "graphics_context": None,
            },
            True,
            None,
            ("active frame-present route remains unresolved without runtime status",),
        )
    if not path.is_file():
        failure = f"runtime graphics status source not found: {path}"
        return _rejected_runtime(path, failure), False, failure, ()
    try:
        payload = load_graphics_runtime_status(path, identity, executable_sha256, candidates)
    except (OSError, TypeError, ValueError) as exc:
        failure = f"runtime graphics status rejected: {exc}"
        return _rejected_runtime(path, failure), False, failure, ()
    return (
        {
            "state": "accepted",
            "source_path": str(path),
            "producer_id": payload["producer_id"],
            "runtime_profile": payload["runtime_profile"],
            "frame_timing": payload["frame_timing"],
            "extension_version": payload["extension_version"],
            "active_present_entry": payload["active_present_entry"],
            "present_entries": payload["present_entries"],
            "graphics_context": payload["graphics_context"],
            "depth_edge_pass": payload["depth_edge_pass"],
            "scene_color_capture": payload.get("scene_color_capture"),
            "draw_classification": payload.get("draw_classification"),
        },
        True,
        None,
        (),
    )


def _validate_runtime_status(
    payload: dict[str, Any],
    identity: ProcessIdentity,
    executable_sha256: str,
    candidates: tuple[dict[str, object], ...],
) -> None:
    validate_finite_json(payload)
    if payload.get("schema_version") != GRAPHICS_RUNTIME_STATUS_SCHEMA_VERSION:
        raise ValueError("unsupported runtime graphics status schema version")
    if payload.get("producer_id") != "wonderbane-extension.graphics":
        raise ValueError("unexpected runtime graphics status producer")
    if not _bounded_text(payload.get("extension_version"), 128):
        raise ValueError("runtime extension_version must be bounded non-empty text")
    if payload.get("runtime_profile") not in _RUNTIME_PROFILES:
        raise ValueError("runtime_profile is not a recognized bounded instrumentation profile")
    observed_identity = _mapping(payload.get("process_identity"), "runtime process_identity")
    if observed_identity.get("process_id") != identity.process_id:
        raise ValueError("runtime status process ID does not match the captured process")
    if (
        observed_identity.get("process_creation_filetime_utc")
        != identity.process_creation_filetime_utc
    ):
        raise ValueError("runtime status process creation identity does not match")
    if _normalized_path(observed_identity.get("executable_path")) != _normalized_path(
        identity.executable_path
    ):
        raise ValueError("runtime status executable path does not match")
    if validate_sha256(payload.get("executable_sha256"), "runtime executable sha256") != (
        executable_sha256
    ):
        raise ValueError("runtime status executable hash does not match")
    entries = payload.get("present_entries")
    if not isinstance(entries, list) or len(entries) > 32:
        raise ValueError("runtime present_entries must be a bounded list")
    candidate_keys = {
        (str(item["library"]).casefold(), item["symbol"], item["iat_rva"]) for item in candidates
    }
    observed_counts: dict[tuple[str, object, object], int] = {}
    for value in entries:
        entry = _mapping(value, "runtime present entry")
        key = _present_key(entry)
        if key not in candidate_keys:
            raise ValueError("runtime present entry is absent from the exact PE import table")
        count = entry.get("call_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("runtime present call_count must be a non-negative integer")
        if key in observed_counts:
            raise ValueError("runtime present_entries contains a duplicate entry")
        observed_counts[key] = count
    active = payload.get("active_present_entry")
    if active is not None:
        active_key = _present_key(_mapping(active, "active_present_entry"))
        if observed_counts.get(active_key, 0) <= 0:
            raise ValueError("active present entry requires an observed positive call count")
    context = _mapping(payload.get("graphics_context"), "graphics_context")
    if not isinstance(context.get("context_observed"), bool):
        raise ValueError("graphics_context.context_observed must be boolean")
    depth_bits = context.get("depth_bits")
    if depth_bits is not None and (
        isinstance(depth_bits, bool)
        or not isinstance(depth_bits, int)
        or not 0 <= depth_bits <= 128
    ):
        raise ValueError("graphics_context.depth_bits must be null or a bounded integer")
    for name in ("depth_texture_supported", "framebuffer_object_supported"):
        value = context.get(name)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"graphics_context.{name} must be null or boolean")
    for name in ("gl_version", "glsl_version"):
        value = context.get(name)
        if value is not None and not _bounded_text(value, 256):
            raise ValueError(f"graphics_context.{name} must be null or bounded text")
    viewport = context.get("viewport")
    if viewport is not None and (
        not isinstance(viewport, list)
        or len(viewport) != 4
        or any(isinstance(item, bool) or not isinstance(item, int) for item in viewport)
        or viewport[2] <= 0
        or viewport[3] <= 0
    ):
        raise ValueError("graphics_context.viewport must be null or x,y,width,height")
    _mapping(payload.get("depth_edge_pass"), "depth_edge_pass")
    scene_color = payload.get("scene_color_capture")
    if scene_color is not None:
        _validate_scene_color_capture(scene_color)
    classification = payload.get("draw_classification")
    if classification is not None:
        _validate_draw_classification(classification)

    _validate_frame_timing(payload.get("frame_timing"), observed_counts)


def _validate_scene_color_capture(value: object) -> None:
    capture = _mapping(value, "scene_color_capture")
    if capture.get("schema_version") != 1:
        raise ValueError("scene_color_capture schema is unsupported")
    state = capture.get("state")
    if state not in {"armed", "active", "fallback"}:
        raise ValueError("scene_color_capture state is unsupported")
    if not _bounded_text(capture.get("reason"), 128):
        raise ValueError("scene_color_capture reason must be bounded text")
    count = _non_negative_counter(capture.get("capture_count"), "capture_count")
    if capture.get("copy_boundary") != "before-ui":
        raise ValueError("scene_color_capture boundary is unsupported")
    if capture.get("copy_frequency") != "once-per-frame":
        raise ValueError("scene_color_capture frequency is unsupported")
    if capture.get("transport") != "gpu-to-gpu":
        raise ValueError("scene_color_capture transport is unsupported")
    if capture.get("cpu_readback") is not False:
        raise ValueError("scene_color_capture must not use CPU readback")
    if state == "active" and count == 0:
        raise ValueError("scene_color_capture active state requires a capture")
    if state == "armed" and count != 0:
        raise ValueError("scene_color_capture armed state requires zero captures")


_DRAW_LAYER_NAMES = (
    "unknown",
    "world_opaque",
    "world_alpha_tested",
    "world_translucent",
    "world_overlay",
    "ui_overlay",
)
_DRAW_REASON_NAMES = (
    "projection_unavailable",
    "orthographic_projection",
    "planar_overlay_state",
    "depth_writing_opaque",
    "depth_writing_alpha_tested",
    "blended_perspective",
    "depthless_perspective",
)


def _validate_draw_classification(value: object) -> None:
    classification = _mapping(value, "draw_classification")
    if classification.get("schema_version") != 1:
        raise ValueError("draw_classification schema is unsupported")
    state = classification.get("state")
    if state not in {"armed", "active"}:
        raise ValueError("draw_classification state is unsupported")
    frame_count = _non_negative_counter(
        classification.get("classified_frame_count"),
        "classified_frame_count",
    )
    if (state == "active") != (frame_count > 0):
        raise ValueError("draw_classification state disagrees with frame count")
    latest = _mapping(classification.get("latest"), "draw_classification.latest")
    if latest.get("phase") not in {"awaiting-world", "world", "ui"}:
        raise ValueError("draw_classification latest phase is unsupported")
    _validate_classification_counts(latest, "draw_classification.latest")
    totals = _mapping(classification.get("totals"), "draw_classification.totals")
    _validate_classification_counts(totals, "draw_classification.totals")
    policy = _mapping(classification.get("policy"), "draw_classification.policy")
    if policy.get("single_world_to_ui_boundary") is not True:
        raise ValueError("draw_classification boundary policy is unsupported")
    if policy.get("late_world_after_ui") not in {
        "excluded-and-counted",
        "effect-eligible-and-counted",
    }:
        raise ValueError("draw_classification late-world policy is unsupported")
    planar_overlay_policy = policy.get("planar_overlay")
    if planar_overlay_policy not in {None, "excluded-without-sealing-scene"}:
        raise ValueError("draw_classification planar-overlay policy is unsupported")
    if policy.get("fixed_function_state") != "cached-with-transition-hooks":
        raise ValueError("draw_classification fixed-function policy is unsupported")
    if policy.get("maximum_ordinary_frame_refreshes") != 1:
        raise ValueError("draw_classification refresh budget is unsupported")
    if latest.get("fixed_function_refresh_count") > 1:
        raise ValueError("draw_classification exceeded its per-frame refresh budget")


def _validate_classification_counts(value: dict[str, Any], field_name: str) -> None:
    layers = _mapping(value.get("layers"), f"{field_name}.layers")
    reasons = _mapping(value.get("reasons"), f"{field_name}.reasons")
    if set(layers) != set(_DRAW_LAYER_NAMES):
        raise ValueError(f"{field_name}.layers has an unsupported shape")
    if set(reasons) != set(_DRAW_REASON_NAMES):
        raise ValueError(f"{field_name}.reasons has an unsupported shape")
    for name in _DRAW_LAYER_NAMES:
        _non_negative_counter(layers.get(name), f"{field_name}.layers.{name}")
    for name in _DRAW_REASON_NAMES:
        _non_negative_counter(reasons.get(name), f"{field_name}.reasons.{name}")
    _non_negative_counter(value.get("boundary_count"), f"{field_name}.boundary_count")
    _non_negative_counter(
        value.get("late_world_draw_count"),
        f"{field_name}.late_world_draw_count",
    )
    _non_negative_counter(
        value.get("fixed_function_refresh_count"),
        f"{field_name}.fixed_function_refresh_count",
    )


def _non_negative_counter(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**64:
        raise ValueError(f"{field_name} must be a bounded non-negative integer")
    return value


def load_graphics_runtime_status(
    path: Path,
    identity: ProcessIdentity,
    executable_sha256: str,
    candidates: tuple[dict[str, object], ...],
) -> dict[str, Any]:
    """Load one exact-process graphics status snapshot and reject any identity drift."""

    payload = _mapping(load_strict_json(path), "runtime graphics status")
    _validate_runtime_status(payload, identity, executable_sha256, candidates)
    return payload


def _validate_frame_timing(
    value: object,
    observed_counts: dict[tuple[str, object, object], int],
) -> None:
    timing = _mapping(value, "frame_timing")
    if timing.get("clock") != "windows-query-performance-counter":
        raise ValueError("frame_timing clock is unsupported")
    frequency = timing.get("counter_frequency_hz")
    if (
        isinstance(frequency, bool)
        or not isinstance(frequency, int)
        or not 1 <= frequency <= 1_000_000_000_000
    ):
        raise ValueError("frame_timing counter frequency must be a bounded positive integer")
    for name in (
        "snapshot_counter",
        "snapshot_filetime_utc",
        "latest_present_sequence",
        "oldest_available_sequence",
        "sample_capacity",
        "sample_count",
        "timing_query_failure_count",
    ):
        item = timing.get(name)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ValueError(f"frame_timing {name} must be a non-negative integer")
    if timing["snapshot_counter"] <= 0 or timing["snapshot_filetime_utc"] <= 0:
        raise ValueError("frame_timing snapshot clock anchors must be positive")
    capacity = timing["sample_capacity"]
    if not 1 <= capacity <= 1_000_000:
        raise ValueError("frame_timing sample capacity is outside the bounded range")
    latest = timing["latest_present_sequence"]
    if latest != max(observed_counts.values(), default=0):
        raise ValueError("frame_timing latest sequence does not match present call count")
    samples = timing.get("samples")
    if not isinstance(samples, list) or len(samples) > capacity:
        raise ValueError("frame_timing samples must be a capacity-bounded list")
    if timing["sample_count"] != len(samples):
        raise ValueError("frame_timing sample_count does not match samples")
    previous_sequence = 0
    oldest = timing["oldest_available_sequence"]
    for item in samples:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or any(isinstance(part, bool) or not isinstance(part, int) for part in item)
        ):
            raise ValueError("frame_timing samples must be [sequence,counter] integer pairs")
        sequence, counter = item
        if sequence <= previous_sequence or counter <= 0:
            raise ValueError("frame_timing sample sequences and counters must increase")
        if sequence > latest:
            raise ValueError("frame_timing sample sequence exceeds latest present")
        previous_sequence = sequence
    if samples:
        if oldest != samples[0][0]:
            raise ValueError("frame_timing oldest sequence does not match samples")
    elif oldest != 0:
        raise ValueError("frame_timing oldest sequence must be zero without samples")


def _rejected_runtime(path: Path, failure: str) -> dict[str, object]:
    return {
        "state": "rejected",
        "source_path": str(path),
        "failure": failure,
        "active_present_entry": None,
        "graphics_context": None,
    }


def _present_key(entry: dict[str, Any]) -> tuple[str, object, object]:
    library = entry.get("library")
    symbol = entry.get("symbol")
    iat_rva = entry.get("iat_rva")
    if not _bounded_text(library, 260) or not _bounded_text(symbol, 260):
        raise ValueError("present entry library and symbol must be bounded text")
    if isinstance(iat_rva, bool) or not isinstance(iat_rva, int) or iat_rva < 0:
        raise ValueError("present entry iat_rva must be a non-negative integer")
    return str(library).casefold(), symbol, iat_rva


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} must be an object")
    return value


def _bounded_text(value: object, maximum: int) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value and len(value) <= maximum


def _normalized_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("runtime executable path must be bounded non-empty text")
    return os.path.normcase(str(Path(value).resolve(strict=False)))


__all__ = [
    "GRAPHICS_PRESENT_EVIDENCE_SCHEMA_VERSION",
    "GRAPHICS_RUNTIME_STATUS_SCHEMA_VERSION",
    "GraphicsPresentCollection",
    "collect_graphics_present_evidence",
    "load_graphics_runtime_status",
]
