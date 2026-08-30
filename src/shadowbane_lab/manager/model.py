"""Immutable manager-facing snapshots for discovered client windows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

from shadowbane_lab.client_input import WindowBounds

MANAGER_SNAPSHOT_SCHEMA_VERSION = 1


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_node_id(value: str) -> None:
    _require_non_empty(value, "node_id")
    if value != value.strip() or "\0" in value:
        raise ValueError("node_id must be canonical and must not contain NUL characters")


def _require_optional_non_empty(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_non_empty(value, field_name)


def _require_positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_optional_positive_integer(value: int | None, field_name: str) -> None:
    if value is not None:
        _require_positive_integer(value, field_name)


def _window_payload(
    *,
    executable_name: str,
    executable_path: str | None,
    title: str,
    client_bounds: WindowBounds,
    dpi_scale: float,
    is_foreground: bool,
    is_visible: bool,
    process_id: int | None,
    window_handle: int | None,
    process_started_at_100ns: int | None,
) -> dict[str, object]:
    return {
        "executable_name": executable_name,
        "executable_path": executable_path,
        "title": title,
        "client_bounds": {
            "left": client_bounds.left,
            "top": client_bounds.top,
            "width": client_bounds.width,
            "height": client_bounds.height,
        },
        "dpi_scale": dpi_scale,
        "is_foreground": is_foreground,
        "is_visible": is_visible,
        "process_id": process_id,
        "window_handle": window_handle,
        "process_started_at_100ns": process_started_at_100ns,
    }


def _validate_window_fields(
    *,
    executable_name: str,
    executable_path: str | None,
    title: str,
    client_bounds: WindowBounds,
    dpi_scale: float,
    is_foreground: bool,
    is_visible: bool,
) -> None:
    _require_non_empty(executable_name, "executable_name")
    _require_optional_non_empty(executable_path, "executable_path")
    if not isinstance(title, str):
        raise ValueError("title must be a string")
    if not isinstance(client_bounds, WindowBounds):
        raise ValueError("client_bounds must be WindowBounds")
    if isinstance(dpi_scale, bool) or not isinstance(dpi_scale, (int, float)):
        raise ValueError("dpi_scale must be numeric")
    if not isfinite(dpi_scale) or dpi_scale <= 0:
        raise ValueError("dpi_scale must be positive")
    if not isinstance(is_foreground, bool) or not isinstance(is_visible, bool):
        raise ValueError("window state flags must be booleans")


class WindowRejectionReason(StrEnum):
    """Why a matching window was not exposed as an attachable client."""

    MISSING_PROCESS_ID = "missing_process_id"
    INVALID_PROCESS_ID = "invalid_process_id"
    MISSING_WINDOW_HANDLE = "missing_window_handle"
    INVALID_WINDOW_HANDLE = "invalid_window_handle"
    MISSING_PROCESS_START_TIME = "missing_process_started_at_100ns"
    INVALID_PROCESS_START_TIME = "invalid_process_started_at_100ns"


@dataclass(frozen=True, slots=True)
class ClientInstanceSnapshot:
    """One client process/window identity safe to attach manager state to."""

    node_id: str
    instance_id: str
    process_id: int
    process_started_at_100ns: int
    window_handle: int
    executable_name: str
    title: str
    client_bounds: WindowBounds
    dpi_scale: float
    is_foreground: bool
    is_visible: bool
    executable_path: str | None = None

    def __post_init__(self) -> None:
        _require_node_id(self.node_id)
        _require_non_empty(self.instance_id, "instance_id")
        _require_positive_integer(self.process_id, "process_id")
        _require_positive_integer(
            self.process_started_at_100ns,
            "process_started_at_100ns",
        )
        _require_positive_integer(self.window_handle, "window_handle")
        _validate_window_fields(
            executable_name=self.executable_name,
            executable_path=self.executable_path,
            title=self.title,
            client_bounds=self.client_bounds,
            dpi_scale=self.dpi_scale,
            is_foreground=self.is_foreground,
            is_visible=self.is_visible,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "instance_id": self.instance_id,
            **_window_payload(
                executable_name=self.executable_name,
                executable_path=self.executable_path,
                title=self.title,
                client_bounds=self.client_bounds,
                dpi_scale=self.dpi_scale,
                is_foreground=self.is_foreground,
                is_visible=self.is_visible,
                process_id=self.process_id,
                window_handle=self.window_handle,
                process_started_at_100ns=self.process_started_at_100ns,
            ),
        }

    def as_dict(self) -> dict[str, object]:
        """Alias for callers that use snapshot-style naming."""

        return self.to_dict()


@dataclass(frozen=True, slots=True)
class RejectedWindowSnapshot:
    """A matching visible window whose process lifetime cannot be identified safely."""

    node_id: str
    executable_name: str
    title: str
    client_bounds: WindowBounds
    dpi_scale: float
    is_foreground: bool
    is_visible: bool
    reasons: tuple[WindowRejectionReason, ...]
    executable_path: str | None = None
    process_id: int | None = None
    window_handle: int | None = None
    process_started_at_100ns: int | None = None

    def __post_init__(self) -> None:
        _require_node_id(self.node_id)
        _validate_window_fields(
            executable_name=self.executable_name,
            executable_path=self.executable_path,
            title=self.title,
            client_bounds=self.client_bounds,
            dpi_scale=self.dpi_scale,
            is_foreground=self.is_foreground,
            is_visible=self.is_visible,
        )
        _require_optional_positive_integer(self.process_id, "process_id")
        _require_optional_positive_integer(self.window_handle, "window_handle")
        _require_optional_positive_integer(
            self.process_started_at_100ns,
            "process_started_at_100ns",
        )
        if not isinstance(self.reasons, tuple) or not self.reasons:
            raise ValueError("reasons must be a non-empty tuple")
        if any(not isinstance(reason, WindowRejectionReason) for reason in self.reasons):
            raise ValueError("reasons must contain WindowRejectionReason values")
        canonical = tuple(sorted(set(self.reasons), key=str))
        if self.reasons != canonical:
            raise ValueError("reasons must be unique and canonically sorted")

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            **_window_payload(
                executable_name=self.executable_name,
                executable_path=self.executable_path,
                title=self.title,
                client_bounds=self.client_bounds,
                dpi_scale=self.dpi_scale,
                is_foreground=self.is_foreground,
                is_visible=self.is_visible,
                process_id=self.process_id,
                window_handle=self.window_handle,
                process_started_at_100ns=self.process_started_at_100ns,
            ),
            "reasons": [reason.value for reason in self.reasons],
        }

    def as_dict(self) -> dict[str, object]:
        return self.to_dict()


def _client_sort_key(client: ClientInstanceSnapshot) -> tuple[object, ...]:
    return (
        client.node_id,
        client.executable_name.casefold(),
        client.process_id,
        client.process_started_at_100ns,
        client.window_handle,
        client.instance_id,
    )


def _rejected_sort_key(window: RejectedWindowSnapshot) -> tuple[object, ...]:
    return (
        window.node_id,
        window.executable_name.casefold(),
        window.process_id or 0,
        window.process_started_at_100ns or 0,
        window.window_handle or 0,
        window.title.casefold(),
        window.client_bounds.left,
        window.client_bounds.top,
        tuple(reason.value for reason in window.reasons),
    )


@dataclass(frozen=True, slots=True)
class ClientRegistrySnapshot:
    """Canonical dashboard snapshot from one read-only registry inspection."""

    node_id: str
    clients: tuple[ClientInstanceSnapshot, ...]
    rejected: tuple[RejectedWindowSnapshot, ...] = ()
    schema_version: int = field(default=MANAGER_SNAPSHOT_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_node_id(self.node_id)
        if not isinstance(self.clients, tuple) or any(
            not isinstance(client, ClientInstanceSnapshot) for client in self.clients
        ):
            raise ValueError("clients must be a tuple of ClientInstanceSnapshot values")
        if not isinstance(self.rejected, tuple) or any(
            not isinstance(window, RejectedWindowSnapshot) for window in self.rejected
        ):
            raise ValueError("rejected must be a tuple of RejectedWindowSnapshot values")
        if self.clients != tuple(sorted(self.clients, key=_client_sort_key)):
            raise ValueError("clients must be canonically sorted")
        if self.rejected != tuple(sorted(self.rejected, key=_rejected_sort_key)):
            raise ValueError("rejected windows must be canonically sorted")
        if any(client.node_id != self.node_id for client in self.clients):
            raise ValueError("all clients must belong to the registry node")
        if any(window.node_id != self.node_id for window in self.rejected):
            raise ValueError("all rejected windows must belong to the registry node")
        instance_ids = tuple(client.instance_id for client in self.clients)
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("client instance IDs must be unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "clients": [client.to_dict() for client in self.clients],
            "rejected": [window.to_dict() for window in self.rejected],
        }

    def as_dict(self) -> dict[str, object]:
        return self.to_dict()


__all__ = [
    "MANAGER_SNAPSHOT_SCHEMA_VERSION",
    "ClientInstanceSnapshot",
    "ClientRegistrySnapshot",
    "RejectedWindowSnapshot",
    "WindowRejectionReason",
]
