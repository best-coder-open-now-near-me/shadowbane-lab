"""Exact-process extension health for the existing loopback manager API."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from shadowbane_lab.client_extension.heartbeat import (
    ExtensionHeartbeatError,
    load_extension_heartbeat,
)

EXTENSION_RUNTIME_STATUS_SCHEMA_VERSION = 1


class ExtensionRuntimeState(StrEnum):
    """Fail-closed extension state for one exact game-process lifetime."""

    NOT_CONFIGURED = "not_configured"
    UNBOUND = "unbound"
    MISSING = "missing"
    INVALID = "invalid"
    INITIALIZED = "initialized"


@dataclass(frozen=True, slots=True)
class ExtensionRuntimeSnapshot:
    """API-safe extension status without exposing private filesystem paths."""

    state: ExtensionRuntimeState
    ready: bool
    process_id: int | None = None
    process_creation_filetime_utc: int | None = None
    extension_version: str | None = None
    abi_version: int | None = None
    initialized_at_filetime_utc: int | None = None
    heartbeat_file_name: str | None = None
    detail: str | None = None
    schema_version: int = EXTENSION_RUNTIME_STATUS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXTENSION_RUNTIME_STATUS_SCHEMA_VERSION:
            raise ValueError("unsupported extension-runtime status schema version")
        if not isinstance(self.state, ExtensionRuntimeState):
            raise ValueError("state must be ExtensionRuntimeState")
        if not isinstance(self.ready, bool):
            raise ValueError("ready must be boolean")
        if self.ready != (self.state is ExtensionRuntimeState.INITIALIZED):
            raise ValueError("only initialized extension status can be ready")
        if (self.process_id is None) != (self.process_creation_filetime_utc is None):
            raise ValueError("extension process identity must be complete or absent")
        for value, field_name, maximum in (
            (self.process_id, "process_id", 0xFFFFFFFF),
            (
                self.process_creation_filetime_utc,
                "process_creation_filetime_utc",
                0xFFFFFFFFFFFFFFFF,
            ),
            (
                self.initialized_at_filetime_utc,
                "initialized_at_filetime_utc",
                0xFFFFFFFFFFFFFFFF,
            ),
            (self.abi_version, "abi_version", 0xFFFFFFFF),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum
            ):
                raise ValueError(f"{field_name} must be a bounded positive integer")
        if self.state is ExtensionRuntimeState.INITIALIZED and any(
            value is None
            for value in (
                self.process_id,
                self.process_creation_filetime_utc,
                self.extension_version,
                self.abi_version,
                self.initialized_at_filetime_utc,
                self.heartbeat_file_name,
            )
        ):
            raise ValueError("initialized extension status is incomplete")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "state": self.state.value,
            "ready": self.ready,
            "process_id": self.process_id,
            "process_creation_filetime_utc": self.process_creation_filetime_utc,
            "extension_version": self.extension_version,
            "abi_version": self.abi_version,
            "initialized_at_filetime_utc": self.initialized_at_filetime_utc,
            "heartbeat_file_name": self.heartbeat_file_name,
            "detail": self.detail,
        }


class ExtensionHeartbeatStatusProvider:
    """Resolve only the heartbeat bound to the requested PID/creation-time pair."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory).resolve(strict=False)

    def inspect(
        self,
        process_id: int | None,
        process_creation_filetime_utc: int | None,
    ) -> ExtensionRuntimeSnapshot:
        if process_id is None and process_creation_filetime_utc is None:
            return ExtensionRuntimeSnapshot(
                state=ExtensionRuntimeState.UNBOUND,
                ready=False,
                detail="no exact game-process lifetime is bound to this slot",
            )
        if process_id is None or process_creation_filetime_utc is None:
            raise ValueError("extension process identity must be complete")
        for value, field_name, maximum in (
            (process_id, "process_id", 0xFFFFFFFF),
            (
                process_creation_filetime_utc,
                "process_creation_filetime_utc",
                0xFFFFFFFFFFFFFFFF,
            ),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
                raise ValueError(f"{field_name} must be a bounded positive integer")
        file_name = f"heartbeat-{process_id}-{process_creation_filetime_utc}.json"
        path = self._directory / file_name
        try:
            path.lstat()
        except FileNotFoundError:
            return ExtensionRuntimeSnapshot(
                state=ExtensionRuntimeState.MISSING,
                ready=False,
                process_id=process_id,
                process_creation_filetime_utc=process_creation_filetime_utc,
                heartbeat_file_name=file_name,
                detail="the exact process has not published an extension heartbeat",
            )
        except OSError as exc:
            return ExtensionRuntimeSnapshot(
                state=ExtensionRuntimeState.INVALID,
                ready=False,
                process_id=process_id,
                process_creation_filetime_utc=process_creation_filetime_utc,
                heartbeat_file_name=file_name,
                detail=f"the exact extension heartbeat could not be inspected: {exc}",
            )
        try:
            heartbeat = load_extension_heartbeat(path)
        except ExtensionHeartbeatError as exc:
            return ExtensionRuntimeSnapshot(
                state=ExtensionRuntimeState.INVALID,
                ready=False,
                process_id=process_id,
                process_creation_filetime_utc=process_creation_filetime_utc,
                heartbeat_file_name=file_name,
                detail=f"the exact extension heartbeat is invalid: {exc}",
            )
        if heartbeat.process_identity != (process_id, process_creation_filetime_utc):
            return ExtensionRuntimeSnapshot(
                state=ExtensionRuntimeState.INVALID,
                ready=False,
                process_id=process_id,
                process_creation_filetime_utc=process_creation_filetime_utc,
                heartbeat_file_name=file_name,
                detail="the extension heartbeat belongs to another process lifetime",
            )
        return ExtensionRuntimeSnapshot(
            state=ExtensionRuntimeState.INITIALIZED,
            ready=True,
            process_id=heartbeat.process_id,
            process_creation_filetime_utc=heartbeat.process_creation_filetime_utc,
            extension_version=heartbeat.extension_version,
            abi_version=heartbeat.abi_version,
            initialized_at_filetime_utc=heartbeat.initialized_at_filetime_utc,
            heartbeat_file_name=file_name,
            detail="the exact game-process lifetime initialized the reviewed extension ABI",
        )


def unconfigured_extension_status() -> ExtensionRuntimeSnapshot:
    """Return an explicit state when a manager host has no heartbeat provider."""

    return ExtensionRuntimeSnapshot(
        state=ExtensionRuntimeState.NOT_CONFIGURED,
        ready=False,
        detail="extension heartbeat status is not configured on this manager host",
    )


__all__ = [
    "EXTENSION_RUNTIME_STATUS_SCHEMA_VERSION",
    "ExtensionHeartbeatStatusProvider",
    "ExtensionRuntimeSnapshot",
    "ExtensionRuntimeState",
    "unconfigured_extension_status",
]
