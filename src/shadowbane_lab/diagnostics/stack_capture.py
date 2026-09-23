"""Fail-closed planning gate for an optional stationary CPU-stack capture."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from shadowbane_lab.evidence import (
    ArtifactStore,
    ManifestTerminalState,
    VerificationStatus,
    load_manifest,
    verify_manifest,
)
from shadowbane_lab.integrity import is_reparse_point, load_strict_json, strict_json_loads

from .process import ProcessIdentity
from .timeline import DIAGNOSTIC_TIMELINE_SCHEMA_VERSION

STACK_CAPTURE_PLAN_SCHEMA_VERSION = 1
_TIMELINE_FIELDS = {
    "schema_version",
    "run_id",
    "process_identity",
    "capture_window",
    "policy",
    "markers",
    "player_samples",
    "camera_samples",
    "frames",
    "summary",
    "health",
    "complete",
}


def plan_stationary_cpu_stack_capture(capture_directory: Path) -> dict[str, object]:
    """Verify sealed evidence and return an exact target only when stacks are recommended."""

    if not isinstance(capture_directory, Path):
        raise ValueError("capture_directory must be Path")
    capture = capture_directory.resolve(strict=True)
    if not capture.is_dir() or is_reparse_point(capture):
        raise ValueError("capture directory must be a non-reparse directory")
    timeline_paths = tuple(sorted(capture.glob("*.timeline.json")))
    if len(timeline_paths) != 1:
        raise ValueError("capture must contain exactly one diagnostic timeline")
    manifest_paths = tuple(sorted((capture / "manifests").glob("*.manifest.json")))
    if len(manifest_paths) != 1:
        raise ValueError("capture must contain exactly one evidence manifest")

    store = ArtifactStore(capture / "store")
    manifest = load_manifest(manifest_paths[0])
    if manifest.terminal_state is not ManifestTerminalState.COMPLETE:
        raise ValueError("diagnostic manifest is not complete")
    verification = verify_manifest(store, manifest)
    if verification.status is not VerificationStatus.PASS:
        raise ValueError("diagnostic evidence verification failed")
    descriptors = [
        item
        for item in manifest.artifacts
        if dict(item.metadata).get("channel_id") == "diagnostic-timeline"
    ]
    if len(descriptors) != 1 or descriptors[0].artifact_id is None:
        raise ValueError("manifest must seal exactly one diagnostic timeline")

    timeline = _mapping(load_strict_json(timeline_paths[0]), "diagnostic timeline")
    with store.open_artifact(descriptors[0].artifact_id) as stream:
        sealed_timeline = _mapping(
            strict_json_loads(stream.read()),
            "sealed diagnostic timeline",
        )
    if timeline != sealed_timeline:
        raise ValueError("convenience timeline differs from its sealed artifact")
    if set(timeline) != _TIMELINE_FIELDS:
        raise ValueError("diagnostic timeline fields are unsupported")
    if timeline.get("schema_version") != DIAGNOSTIC_TIMELINE_SCHEMA_VERSION:
        raise ValueError("diagnostic timeline schema is unsupported")
    if timeline.get("complete") is not True:
        raise ValueError("diagnostic timeline is incomplete")

    summary = _mapping(timeline.get("summary"), "timeline summary")
    if summary.get("phase_protocol_complete") is not True:
        raise ValueError("hotspot phase protocol is incomplete")
    if summary.get("cpu_stack_capture_recommended") is not True:
        raise ValueError("stationary CPU-stack capture is not recommended by the timeline")
    slow_count = _positive_integer(
        summary.get("stationary_resident_unexplained_slow_frame_count"),
        "stationary unexplained slow-frame count",
    )
    identity_value = _mapping(timeline.get("process_identity"), "process identity")
    if set(identity_value) != {
        "executable_name",
        "executable_path",
        "process_creation_filetime_utc",
        "process_id",
    }:
        raise ValueError("timeline process identity fields are unsupported")
    identity = ProcessIdentity(
        _positive_integer(identity_value.get("process_id"), "process ID"),
        _positive_integer(
            identity_value.get("process_creation_filetime_utc"),
            "process creation FILETIME",
        ),
        _text(identity_value.get("executable_path"), "executable path"),
    )
    if identity_value.get("executable_name") != Path(identity.executable_path).name:
        raise ValueError("timeline executable name does not match its path")
    timeline_sha256 = hashlib.sha256(timeline_paths[0].read_bytes()).hexdigest()
    return {
        "schema_version": STACK_CAPTURE_PLAN_SCHEMA_VERSION,
        "status": "recommended",
        "capture_directory": str(capture),
        "timeline_path": str(timeline_paths[0]),
        "timeline_sha256": timeline_sha256,
        "timeline_artifact_id": descriptors[0].artifact_id,
        "manifest_path": str(manifest_paths[0]),
        "manifest_id": manifest.manifest_id,
        "verification_receipt_id": verification.receipt_id,
        "process_identity": identity.as_dict(),
        "stationary_resident_unexplained_slow_frame_count": slow_count,
        "collection_scope": "system-wide-cpu-sampling-targeted-during-analysis",
        "target_authority": "exact-pid-creation-time-executable-path",
    }


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError(f"{name} must be non-empty text")
    return value


__all__ = [
    "STACK_CAPTURE_PLAN_SCHEMA_VERSION",
    "plan_stationary_cpu_stack_capture",
]
