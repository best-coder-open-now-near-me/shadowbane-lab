"""Create-only out-of-process observation markers for live captures."""

from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from shadowbane_lab.integrity import (
    canonical_timestamp,
    create_only_json,
    load_strict_json,
    validate_identifier,
)

from .process import ProcessIdentity

MARKER_CONTROL_SCHEMA_VERSION = 1
MARKER_RECORD_SCHEMA_VERSION = 1
_CONTROL_DIRECTORY = "control"
_ACTIVE_FILE = "active-marker-session.json"
_INBOX_DIRECTORY = "marker-inbox"
_MAX_LABEL_LENGTH = 256


class ObservationPhase(StrEnum):
    COLD_APPROACH = "cold-approach"
    STATIONARY = "stationary"
    WARM_RETURN = "warm-return"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class ObservationMarker:
    marker_id: str
    run_id: str
    monotonic_ns: int
    captured_at_utc: str
    label: str
    phase: ObservationPhase | None
    finish: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "marker_id": self.marker_id,
            "run_id": self.run_id,
            "monotonic_ns": self.monotonic_ns,
            "captured_at_utc": self.captured_at_utc,
            "label": self.label,
            "phase": self.phase.value if self.phase is not None else None,
            "finish": self.finish,
        }


class ObservationMarkerInbox:
    def __init__(
        self,
        output_directory: Path,
        run_id: str,
        identity: ProcessIdentity,
    ) -> None:
        self._output = output_directory
        self._run_id = run_id
        self._identity = identity
        self._token = secrets.token_hex(32)
        self._control = output_directory / _CONTROL_DIRECTORY
        self._inbox = self._control / _INBOX_DIRECTORY
        self._active = self._control / _ACTIVE_FILE
        self._seen: set[str] = set()
        self._closed = False
        self._inbox.mkdir(parents=True, exist_ok=False)
        create_only_json(
            self._active,
            {
                "schema_version": MARKER_CONTROL_SCHEMA_VERSION,
                "run_id": run_id,
                "token": self._token,
                "process_id": identity.process_id,
                "process_creation_filetime_utc": identity.process_creation_filetime_utc,
            },
        )

    @property
    def active_path(self) -> Path:
        return self._active

    def poll(self) -> tuple[ObservationMarker, ...]:
        markers: list[ObservationMarker] = []
        for path in sorted(self._inbox.glob("marker-*.json")):
            if path.name in self._seen:
                continue
            marker = _load_marker(path, expected_run_id=self._run_id, expected_token=self._token)
            if path.stem != marker.marker_id:
                raise ValueError("marker file name does not match marker ID")
            self._seen.add(path.name)
            markers.append(marker)
        markers.sort(key=lambda item: (item.monotonic_ns, item.marker_id))
        return tuple(markers)

    def close(self) -> None:
        if self._closed:
            return
        closed = self._control / f"{self._run_id}.marker-session-closed.json"
        self._active.replace(closed)
        self._closed = True


def submit_observation_marker(
    output_directory: Path,
    label: str,
    *,
    phase: ObservationPhase | None = None,
    finish: bool = False,
    monotonic_ns: int | None = None,
    captured_at_utc: str | None = None,
) -> ObservationMarker:
    if not isinstance(output_directory, Path):
        raise ValueError("output_directory must be Path")
    label = _label(label)
    if phase is not None and not isinstance(phase, ObservationPhase):
        raise ValueError("phase must be ObservationPhase")
    if not isinstance(finish, bool):
        raise ValueError("finish must be boolean")
    active = output_directory.resolve(strict=False) / _CONTROL_DIRECTORY / _ACTIVE_FILE
    control = _active_control(load_strict_json(active))
    marker_id = f"marker-{uuid.uuid4().hex}"
    marker_ns = time.monotonic_ns() if monotonic_ns is None else monotonic_ns
    if isinstance(marker_ns, bool) or not isinstance(marker_ns, int) or marker_ns <= 0:
        raise ValueError("monotonic_ns must be a positive integer")
    marker_utc = canonical_timestamp() if captured_at_utc is None else captured_at_utc
    if not _bounded_text(marker_utc, 64):
        raise ValueError("captured_at_utc must be bounded text")
    marker = ObservationMarker(
        marker_id=marker_id,
        run_id=control["run_id"],
        monotonic_ns=marker_ns,
        captured_at_utc=marker_utc,
        label=label,
        phase=phase,
        finish=finish,
    )
    payload = {
        "schema_version": MARKER_RECORD_SCHEMA_VERSION,
        "token": control["token"],
        **marker.as_dict(),
    }
    destination = active.parent / _INBOX_DIRECTORY / f"{marker_id}.json"
    create_only_json(destination, payload)
    return marker


def _active_control(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("active marker session must be an object")
    expected = {
        "schema_version",
        "run_id",
        "token",
        "process_id",
        "process_creation_filetime_utc",
    }
    if set(value) != expected or value.get("schema_version") != MARKER_CONTROL_SCHEMA_VERSION:
        raise ValueError("active marker session fields are unsupported")
    run_id = value.get("run_id")
    token = value.get("token")
    validate_identifier(run_id, "marker run ID")
    if not isinstance(token, str) or len(token) != 64:
        raise ValueError("active marker token is invalid")
    try:
        bytes.fromhex(token)
    except ValueError as exc:
        raise ValueError("active marker token is invalid") from exc
    for name in ("process_id", "process_creation_filetime_utc"):
        field = value.get(name)
        if isinstance(field, bool) or not isinstance(field, int) or field <= 0:
            raise ValueError(f"active marker {name} is invalid")
    return value


def _load_marker(
    path: Path,
    *,
    expected_run_id: str,
    expected_token: str,
) -> ObservationMarker:
    value = load_strict_json(path)
    if not isinstance(value, dict):
        raise ValueError("observation marker must be an object")
    expected = {
        "schema_version",
        "token",
        "marker_id",
        "run_id",
        "monotonic_ns",
        "captured_at_utc",
        "label",
        "phase",
        "finish",
    }
    if set(value) != expected or value.get("schema_version") != MARKER_RECORD_SCHEMA_VERSION:
        raise ValueError("observation marker fields are unsupported")
    marker_id = value.get("marker_id")
    run_id = value.get("run_id")
    token = value.get("token")
    validate_identifier(marker_id, "marker ID")
    validate_identifier(run_id, "marker run ID")
    if run_id != expected_run_id or not isinstance(token, str):
        raise ValueError("observation marker belongs to another session")
    if not secrets.compare_digest(token, expected_token):
        raise ValueError("observation marker token is invalid")
    marker_ns = value.get("monotonic_ns")
    if isinstance(marker_ns, bool) or not isinstance(marker_ns, int) or marker_ns <= 0:
        raise ValueError("observation marker monotonic_ns is invalid")
    marker_utc = value.get("captured_at_utc")
    if not _bounded_text(marker_utc, 64):
        raise ValueError("observation marker captured_at_utc is invalid")
    phase_value = value.get("phase")
    try:
        phase = None if phase_value is None else ObservationPhase(phase_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("observation marker phase is invalid") from exc
    finish = value.get("finish")
    if not isinstance(finish, bool):
        raise ValueError("observation marker finish is invalid")
    return ObservationMarker(
        marker_id=marker_id,
        run_id=run_id,
        monotonic_ns=marker_ns,
        captured_at_utc=marker_utc,
        label=_label(value.get("label")),
        phase=phase,
        finish=finish,
    )


def _label(value: object) -> str:
    if not _bounded_text(value, _MAX_LABEL_LENGTH):
        raise ValueError("marker label must be bounded non-empty text")
    if any(ord(character) < 32 for character in value):
        raise ValueError("marker label contains a control character")
    return value.strip()


def _bounded_text(value: object, maximum: int) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value and len(value) <= maximum


__all__ = [
    "MARKER_CONTROL_SCHEMA_VERSION",
    "MARKER_RECORD_SCHEMA_VERSION",
    "ObservationMarker",
    "ObservationMarkerInbox",
    "ObservationPhase",
    "submit_observation_marker",
]
