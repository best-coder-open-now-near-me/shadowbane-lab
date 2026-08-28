"""Durable final artifacts and append-only journals for live PvE runs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from math import isfinite
from pathlib import Path
from typing import TextIO

PVE_TRACE_SCHEMA_VERSION = 1
PVE_TRACE_JOURNAL_SCHEMA_VERSION = 1


class PvETraceEvidenceError(ValueError):
    """Raised when a PvE evidence artifact cannot be validated or persisted."""


class PvETraceJournal:
    """Append-only JSONL trace that survives interruption of a continuous run."""

    def __init__(
        self,
        path: str | Path,
        metadata: Mapping[str, object],
        *,
        sync_interval_steps: int = 10,
    ) -> None:
        if not isinstance(metadata, Mapping):
            raise PvETraceEvidenceError("PvE journal metadata must be an object")
        if (
            isinstance(sync_interval_steps, bool)
            or not isinstance(sync_interval_steps, int)
            or sync_interval_steps <= 0
        ):
            raise PvETraceEvidenceError("journal sync interval must be positive")
        self._path = Path(path)
        self._metadata = dict(metadata)
        self._sync_interval_steps = sync_interval_steps
        self._stream: TextIO | None = None
        self._steps = 0
        self._finished = False
        self._validate_record(self._metadata)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def steps(self) -> int:
        return self._steps

    def __enter__(self) -> PvETraceJournal:
        if self._stream is not None:
            raise PvETraceEvidenceError("PvE journal is already open")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = self._path.open("x", encoding="utf-8", newline="\n")
            self._write_record(
                {
                    "record_type": "pve_trace_header",
                    "journal_schema_version": PVE_TRACE_JOURNAL_SCHEMA_VERSION,
                    "trace_schema_version": PVE_TRACE_SCHEMA_VERSION,
                    "metadata": self._metadata,
                },
                sync=True,
            )
        except (OSError, TypeError, ValueError) as exc:
            self.close()
            raise PvETraceEvidenceError(f"could not open PvE trace journal: {exc}") from exc
        return self

    def append_step(self, step: Mapping[str, object]) -> None:
        if not isinstance(step, Mapping):
            raise PvETraceEvidenceError("PvE journal step must be an object")
        if self._finished:
            raise PvETraceEvidenceError("cannot append to a finished PvE journal")
        step_number = self._steps + 1
        self._write_record(
            {
                "record_type": "pve_trace_step",
                "step_number": step_number,
                "step": dict(step),
            },
            sync=step_number % self._sync_interval_steps == 0,
        )
        self._steps = step_number

    def finish(self, summary: Mapping[str, object]) -> None:
        if not isinstance(summary, Mapping):
            raise PvETraceEvidenceError("PvE journal summary must be an object")
        if self._finished:
            raise PvETraceEvidenceError("PvE journal is already finished")
        self._write_record(
            {
                "record_type": "pve_trace_footer",
                "steps": self._steps,
                "summary": dict(summary),
            },
            sync=True,
        )
        self._finished = True

    def close(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.flush()
            os.fsync(stream.fileno())
        except OSError:
            pass
        finally:
            stream.close()

    def __exit__(self, *_: object) -> None:
        self.close()

    def _write_record(self, record: Mapping[str, object], *, sync: bool) -> None:
        if self._stream is None:
            raise PvETraceEvidenceError("PvE journal is not open")
        self._validate_record(record)
        try:
            self._stream.write(
                json.dumps(record, allow_nan=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
            self._stream.flush()
            if sync:
                os.fsync(self._stream.fileno())
        except (OSError, TypeError, ValueError) as exc:
            raise PvETraceEvidenceError(f"could not write PvE trace journal: {exc}") from exc

    @staticmethod
    def _validate_record(record: Mapping[str, object]) -> None:
        try:
            json.dumps(record, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise PvETraceEvidenceError(f"PvE journal record is not finite JSON: {exc}") from exc


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
    total_steps = payload.get("total_steps", payload["steps"])
    if (
        isinstance(total_steps, bool)
        or not isinstance(total_steps, int)
        or total_steps < payload["steps"]
    ):
        raise PvETraceEvidenceError(
            "PvE evidence total_steps must be at least the retained step count"
        )
    trace_truncated = payload.get("trace_truncated", False)
    if not isinstance(trace_truncated, bool):
        raise PvETraceEvidenceError("PvE evidence trace_truncated must be a boolean")
    if trace_truncated != (total_steps > payload["steps"]):
        raise PvETraceEvidenceError(
            "PvE evidence trace_truncated does not match total_steps"
        )
    run_mode = payload.get("run_mode")
    if run_mode is not None and run_mode not in ("bounded", "continuous"):
        raise PvETraceEvidenceError(
            "PvE evidence run_mode must be bounded or continuous"
        )
    journal_path = payload.get("journal_path")
    if journal_path is not None and (
        not isinstance(journal_path, str) or not journal_path.strip()
    ):
        raise PvETraceEvidenceError(
            "PvE evidence journal_path must be a non-empty string when present"
        )
    camp_lease = payload.get("camp_lease")
    if camp_lease is not None:
        if not isinstance(camp_lease, dict):
            raise PvETraceEvidenceError("PvE evidence camp_lease must be an object")
        for field_name in ("anchor_lt", "anchor_lg"):
            value = camp_lease.get(field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise PvETraceEvidenceError(
                    f"PvE evidence camp_lease.{field_name} must be finite"
                )
        for field_name in ("radius", "return_radius"):
            _positive_number(camp_lease, field_name, prefix="camp_lease")
        if camp_lease["return_radius"] >= camp_lease["radius"]:
            raise PvETraceEvidenceError(
                "PvE evidence camp_lease.return_radius must be below radius"
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
    farm_limits = payload.get("farm_limits")
    if farm_limits is not None:
        if not isinstance(farm_limits, dict):
            raise PvETraceEvidenceError("PvE evidence farm_limits must be an object")
        maximum_kills = farm_limits.get("maximum_kills")
        if (
            isinstance(maximum_kills, bool)
            or not isinstance(maximum_kills, int)
            or maximum_kills <= 0
        ):
            raise PvETraceEvidenceError(
                "PvE evidence farm_limits.maximum_kills must be positive"
            )
        for field_name in (
            "maximum_session_seconds",
            "maximum_encounter_seconds",
            "recovery_timeout_seconds",
        ):
            _positive_number(farm_limits, field_name, prefix="farm_limits")
        for field_name in (
            "recovery_health_fraction",
            "recovery_mana_fraction",
            "recovery_stamina_fraction",
        ):
            value = farm_limits.get(field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise PvETraceEvidenceError(
                    f"PvE evidence farm_limits.{field_name} must be in [0, 1]"
                )
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


def _positive_number(
    payload: Mapping[str, object],
    field_name: str,
    *,
    prefix: str,
) -> float:
    value = payload.get(field_name)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
    ):
        raise PvETraceEvidenceError(
            f"PvE evidence {prefix}.{field_name} must be a positive number"
        )
    return float(value)
