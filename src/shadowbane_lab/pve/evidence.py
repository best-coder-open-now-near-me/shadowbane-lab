"""Durable, versioned evidence artifacts produced by bounded live PvE runs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

PVE_TRACE_SCHEMA_VERSION = 1


class PvETraceEvidenceError(ValueError):
    """Raised when a PvE evidence artifact cannot be validated or persisted."""


def load_pve_trace_evidence(path: str | Path) -> dict[str, object]:
    evidence_path = Path(path)
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PvETraceEvidenceError(f"could not read PvE evidence: {exc}") from exc
    return validate_pve_trace_evidence(payload)


def save_pve_trace_evidence(
    path: str | Path,
    payload: Mapping[str, object],
) -> None:
    evidence_path = Path(path)
    validated = validate_pve_trace_evidence(payload)
    temporary_path = evidence_path.with_name(
        f".{evidence_path.name}.{os.getpid()}.tmp"
    )
    try:
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(validated, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(evidence_path)
    except (OSError, TypeError, ValueError) as exc:
        raise PvETraceEvidenceError(f"could not save PvE evidence: {exc}") from exc
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def validate_pve_trace_evidence(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise PvETraceEvidenceError("PvE evidence must be a JSON object")
    if payload.get("trace_schema_version") != PVE_TRACE_SCHEMA_VERSION:
        raise PvETraceEvidenceError("unsupported PvE trace schema version")
    _required_string(payload, "final_phase")
    _required_string(payload, "terminal_reason")
    _required_string(payload, "policy")
    if not isinstance(payload.get("ok"), bool):
        raise PvETraceEvidenceError("PvE evidence ok must be a boolean")
    for field_name in ("kills", "steps"):
        value = payload.get(field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PvETraceEvidenceError(
                f"PvE evidence {field_name} must be a non-negative integer"
            )
    native = payload.get("native_observation")
    if not isinstance(native, dict):
        raise PvETraceEvidenceError("PvE evidence native_observation must be an object")
    process_id = native.get("process_id")
    if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
        raise PvETraceEvidenceError(
            "PvE evidence native_observation.process_id must be positive"
        )
    _required_string(native, "executable_sha256")
    trace = payload.get("trace")
    if not isinstance(trace, list):
        raise PvETraceEvidenceError("PvE evidence trace must be an array")
    if len(trace) != payload["steps"]:
        raise PvETraceEvidenceError("PvE evidence steps does not match trace length")
    for index, step in enumerate(trace):
        if not isinstance(step, dict):
            raise PvETraceEvidenceError(f"PvE evidence trace[{index}] must be an object")
        at_ms = step.get("at_ms")
        if isinstance(at_ms, bool) or not isinstance(at_ms, int) or at_ms < 0:
            raise PvETraceEvidenceError(
                f"PvE evidence trace[{index}].at_ms must be non-negative"
            )
        if not isinstance(step.get("combat_events"), list):
            raise PvETraceEvidenceError(
                f"PvE evidence trace[{index}].combat_events must be an array"
            )
    try:
        json.dumps(payload, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise PvETraceEvidenceError(f"PvE evidence is not finite JSON: {exc}") from exc
    return payload


def _required_string(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise PvETraceEvidenceError(
            f"PvE evidence {field_name} must be a non-empty string"
        )
    return value
