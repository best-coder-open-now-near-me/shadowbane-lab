"""Bounded startup wait for one exact-process graphics runtime status."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Protocol

from shadowbane_lab.integrity import (
    is_reparse_point,
    load_strict_json,
    validate_finite_json,
    validate_sha256,
)

GRAPHICS_RUNTIME_STATUS_SCHEMA_VERSION = 2
_GRAPHICS_RUNTIME_STATUS_PRODUCER = "wonderbane-extension.graphics"
_RUNTIME_PROFILES = frozenset({"diagnostics-only", "full-renderer"})


class GraphicsRuntimeStatusWaitError(RuntimeError):
    """Raised when exact-process renderer startup cannot be proven in time."""


class _ProcessLifetime(Protocol):
    process_id: int
    process_started_at_100ns: int


class ProcessLifetimeInspector(Protocol):
    def inspect(self, process_id: int) -> _ProcessLifetime | None: ...


@dataclass(frozen=True, slots=True)
class GraphicsRuntimeStatusExpectation:
    status_directory: Path
    process_id: int
    process_creation_filetime_utc: int
    executable_path: Path
    executable_sha256: str
    runtime_profile: str

    def __post_init__(self) -> None:
        for value, field_name, maximum in (
            (self.process_id, "process_id", 0xFFFFFFFF),
            (
                self.process_creation_filetime_utc,
                "process_creation_filetime_utc",
                0xFFFFFFFFFFFFFFFF,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 < value <= maximum
            ):
                raise ValueError(f"{field_name} must be a bounded positive integer")
        if not isinstance(self.status_directory, Path):
            raise ValueError("status_directory must be Path")
        if not isinstance(self.executable_path, Path):
            raise ValueError("executable_path must be Path")
        validate_sha256(self.executable_sha256, "executable_sha256")
        if self.runtime_profile not in _RUNTIME_PROFILES:
            raise ValueError("runtime_profile is not recognized")

    @property
    def status_path(self) -> Path:
        return self.status_directory.resolve(strict=False) / (
            f"graphics-status-{self.process_id}-"
            f"{self.process_creation_filetime_utc}.json"
        )


def wait_for_graphics_runtime_status(
    expectation: GraphicsRuntimeStatusExpectation,
    *,
    timeout_seconds: float = 20.0,
    poll_seconds: float = 0.1,
    process_inspector: ProcessLifetimeInspector | None = None,
    clock: Callable[[], float] = monotonic,
    sleeper: Callable[[float], object] = sleep,
) -> dict[str, Any]:
    """Wait for a valid status while the same process lifetime remains live."""

    if not isinstance(expectation, GraphicsRuntimeStatusExpectation):
        raise ValueError("expectation must be GraphicsRuntimeStatusExpectation")
    _bounded_duration(timeout_seconds, "timeout_seconds", minimum=0.01, maximum=300.0)
    _bounded_duration(poll_seconds, "poll_seconds", minimum=0.001, maximum=1.0)
    inspector = process_inspector
    if inspector is None:
        from shadowbane_lab.manager.supervisor import Win32ProcessLifetimeInspector

        inspector = Win32ProcessLifetimeInspector()

    deadline = clock() + timeout_seconds
    last_invalid: str | None = None
    while True:
        lifetime = inspector.inspect(expectation.process_id)
        if lifetime is None:
            raise GraphicsRuntimeStatusWaitError(
                "client exited before publishing graphics runtime status"
            )
        if lifetime.process_started_at_100ns != expectation.process_creation_filetime_utc:
            raise GraphicsRuntimeStatusWaitError(
                "client PID was reused before graphics runtime status was accepted"
            )
        try:
            return _load_expected_status(expectation)
        except FileNotFoundError:
            last_invalid = None
        except (OSError, TypeError, ValueError) as exc:
            last_invalid = str(exc)

        now = clock()
        if now >= deadline:
            detail = ""
            if last_invalid:
                detail = f"; last status was invalid: {last_invalid}"
            raise GraphicsRuntimeStatusWaitError(
                "client did not publish a valid identity-bound graphics runtime status in time"
                + detail
            )
        sleeper(min(poll_seconds, deadline - now))


def _load_expected_status(
    expectation: GraphicsRuntimeStatusExpectation,
) -> dict[str, Any]:
    path = expectation.status_path
    try:
        path.lstat()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ValueError(f"could not inspect graphics runtime status: {exc}") from exc
    if is_reparse_point(path) or not path.is_file():
        raise ValueError("graphics runtime status must be a regular file")
    payload = load_strict_json(path)
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise ValueError("graphics runtime status must be an object")
    validate_finite_json(payload)
    if payload.get("schema_version") != GRAPHICS_RUNTIME_STATUS_SCHEMA_VERSION:
        raise ValueError("unsupported graphics runtime status schema version")
    if payload.get("producer_id") != _GRAPHICS_RUNTIME_STATUS_PRODUCER:
        raise ValueError("unexpected graphics runtime status producer")
    if payload.get("runtime_profile") != expectation.runtime_profile:
        raise ValueError("graphics runtime status profile does not match the launch")
    identity = _mapping(payload.get("process_identity"), "process_identity")
    if identity.get("process_id") != expectation.process_id:
        raise ValueError("graphics runtime status process ID does not match")
    if (
        identity.get("process_creation_filetime_utc")
        != expectation.process_creation_filetime_utc
    ):
        raise ValueError("graphics runtime status process creation identity does not match")
    if _normalized_path(identity.get("executable_path")) != _normalized_path(
        str(expectation.executable_path)
    ):
        raise ValueError("graphics runtime status executable path does not match")
    if validate_sha256(payload.get("executable_sha256"), "status executable_sha256") != (
        expectation.executable_sha256
    ):
        raise ValueError("graphics runtime status executable hash does not match")
    return payload


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} must be an object")
    return value


def _normalized_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("executable path must be non-empty text")
    return os.path.normcase(str(Path(value).resolve(strict=False)))


def _bounded_duration(
    value: float,
    field_name: str,
    *,
    minimum: float,
    maximum: float,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{field_name} must be finite and in {minimum}-{maximum}")


__all__ = [
    "GRAPHICS_RUNTIME_STATUS_SCHEMA_VERSION",
    "GraphicsRuntimeStatusExpectation",
    "GraphicsRuntimeStatusWaitError",
    "ProcessLifetimeInspector",
    "wait_for_graphics_runtime_status",
]
