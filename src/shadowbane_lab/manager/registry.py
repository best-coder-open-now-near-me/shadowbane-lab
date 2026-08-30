"""Read-only discovery of independently identifiable Shadowbane clients."""

from __future__ import annotations

import hashlib
import ntpath
from collections.abc import Iterable
from os import PathLike, fspath
from typing import TypeGuard

from shadowbane_lab.client_input import VisibleWindowInspector, WindowSnapshot

from .model import (
    ClientInstanceSnapshot,
    ClientRegistrySnapshot,
    RejectedWindowSnapshot,
    WindowRejectionReason,
)

_INSTANCE_ID_DOMAIN = "shadowbane-lab/client-instance/v1"


class ClientRegistryError(RuntimeError):
    """Base class for registry inspection failures."""


class DuplicateClientIdentityError(ClientRegistryError):
    """Raised when visible windows do not map one-to-one to client identities."""


def _normalize_windows_path(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(ntpath.abspath(path))).casefold()


def derive_client_instance_id(
    node_id: str,
    process_id: int,
    process_started_at_100ns: int,
    window_handle: int,
) -> str:
    """Derive a globally unique deterministic ID for one process/window lifetime."""

    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError("node_id must be a non-empty string")
    if node_id != node_id.strip() or "\0" in node_id:
        raise ValueError("node_id must be canonical and must not contain NUL characters")
    for value, field_name in (
        (process_id, "process_id"),
        (process_started_at_100ns, "process_started_at_100ns"),
        (window_handle, "window_handle"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{field_name} must be a positive integer")
    identity = (
        f"{_INSTANCE_ID_DOMAIN}\0{node_id}\0{process_id}\0"
        f"{process_started_at_100ns}\0{window_handle}"
    )
    return f"client-{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


def _identity_reasons(snapshot: WindowSnapshot) -> tuple[WindowRejectionReason, ...]:
    reasons: list[WindowRejectionReason] = []
    for value, missing_reason, invalid_reason in (
        (
            snapshot.process_id,
            WindowRejectionReason.MISSING_PROCESS_ID,
            WindowRejectionReason.INVALID_PROCESS_ID,
        ),
        (
            getattr(snapshot, "window_handle", None),
            WindowRejectionReason.MISSING_WINDOW_HANDLE,
            WindowRejectionReason.INVALID_WINDOW_HANDLE,
        ),
        (
            getattr(snapshot, "process_started_at_100ns", None),
            WindowRejectionReason.MISSING_PROCESS_START_TIME,
            WindowRejectionReason.INVALID_PROCESS_START_TIME,
        ),
    ):
        if value is None:
            reasons.append(missing_reason)
        elif isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            reasons.append(invalid_reason)
    return tuple(sorted(reasons, key=str))


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


class ClientWindowRegistry:
    """Enumerate visible clients without activating windows or sending input."""

    def __init__(
        self,
        inspector: VisibleWindowInspector,
        *,
        node_id: str,
        executable_names: Iterable[str] = (),
        process_directory: str | PathLike[str] | None = None,
    ) -> None:
        if not isinstance(inspector, VisibleWindowInspector):
            raise ValueError("inspector must implement VisibleWindowInspector")
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        if node_id != node_id.strip() or "\0" in node_id:
            raise ValueError("node_id must be canonical and must not contain NUL characters")
        if isinstance(executable_names, str):
            raise ValueError("executable_names must be an iterable of names, not a string")
        names = tuple(executable_names)
        if any(
            not isinstance(name, str)
            or not name.strip()
            or name != name.strip()
            or ntpath.basename(name) != name
            for name in names
        ):
            raise ValueError("executable_names must contain canonical file names")
        normalized_names = tuple(name.casefold() for name in names)
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("executable_names must be unique ignoring case")
        if process_directory is not None:
            try:
                directory_text = fspath(process_directory)
            except TypeError as exc:
                raise ValueError("process_directory must be path-like or None") from exc
            if not isinstance(directory_text, str) or not directory_text.strip():
                raise ValueError("process_directory must be non-empty or None")
            normalized_directory = _normalize_windows_path(directory_text)
        else:
            normalized_directory = None
        if not normalized_names and normalized_directory is None:
            raise ValueError("at least one executable name or process directory is required")
        self._inspector = inspector
        self._node_id = node_id
        self._executable_names = frozenset(normalized_names)
        self._process_directory = normalized_directory

    def inspect(self) -> ClientRegistrySnapshot:
        snapshots = self._inspector.inspect_all()
        if not isinstance(snapshots, tuple) or any(
            not isinstance(snapshot, WindowSnapshot) for snapshot in snapshots
        ):
            raise ClientRegistryError(
                "visible-window inspector must return a tuple of WindowSnapshot values"
            )

        matches = [snapshot for snapshot in snapshots if self._matches(snapshot)]
        self._reject_duplicate_identities(matches)

        clients: list[ClientInstanceSnapshot] = []
        rejected: list[RejectedWindowSnapshot] = []
        for snapshot in matches:
            reasons = _identity_reasons(snapshot)
            if reasons:
                rejected.append(self._rejected_snapshot(snapshot, reasons))
            else:
                clients.append(self._client_snapshot(snapshot))

        return ClientRegistrySnapshot(
            node_id=self._node_id,
            clients=tuple(sorted(clients, key=_client_sort_key)),
            rejected=tuple(sorted(rejected, key=_rejected_sort_key)),
        )

    def _matches(self, snapshot: WindowSnapshot) -> bool:
        if (
            self._executable_names
            and snapshot.executable_name.casefold() not in self._executable_names
        ):
            return False
        if self._process_directory is None:
            return True
        if snapshot.executable_path is None:
            return False
        executable_directory = ntpath.dirname(snapshot.executable_path)
        return _normalize_windows_path(executable_directory) == self._process_directory

    def _client_snapshot(self, snapshot: WindowSnapshot) -> ClientInstanceSnapshot:
        process_id = snapshot.process_id
        window_handle = getattr(snapshot, "window_handle", None)
        started_at = getattr(snapshot, "process_started_at_100ns", None)
        assert isinstance(process_id, int) and not isinstance(process_id, bool)
        assert isinstance(window_handle, int) and not isinstance(window_handle, bool)
        assert isinstance(started_at, int) and not isinstance(started_at, bool)
        return ClientInstanceSnapshot(
            node_id=self._node_id,
            instance_id=derive_client_instance_id(
                self._node_id,
                process_id,
                started_at,
                window_handle,
            ),
            process_id=process_id,
            process_started_at_100ns=started_at,
            window_handle=window_handle,
            executable_name=snapshot.executable_name,
            executable_path=snapshot.executable_path,
            title=snapshot.title,
            client_bounds=snapshot.client_bounds,
            dpi_scale=snapshot.dpi_scale,
            is_foreground=snapshot.is_foreground,
            is_visible=snapshot.is_visible,
        )

    def _rejected_snapshot(
        self,
        snapshot: WindowSnapshot,
        reasons: tuple[WindowRejectionReason, ...],
    ) -> RejectedWindowSnapshot:
        process_id = snapshot.process_id
        window_handle = getattr(snapshot, "window_handle", None)
        started_at = getattr(snapshot, "process_started_at_100ns", None)
        return RejectedWindowSnapshot(
            node_id=self._node_id,
            executable_name=snapshot.executable_name,
            executable_path=snapshot.executable_path,
            title=snapshot.title,
            client_bounds=snapshot.client_bounds,
            dpi_scale=snapshot.dpi_scale,
            is_foreground=snapshot.is_foreground,
            is_visible=snapshot.is_visible,
            process_id=process_id if _is_positive_integer(process_id) else None,
            window_handle=window_handle if _is_positive_integer(window_handle) else None,
            process_started_at_100ns=started_at if _is_positive_integer(started_at) else None,
            reasons=reasons,
        )

    @staticmethod
    def _reject_duplicate_identities(snapshots: list[WindowSnapshot]) -> None:
        seen_processes: dict[int, int | None] = {}
        seen_windows: dict[int, int | None] = {}
        for snapshot in snapshots:
            process_id = snapshot.process_id
            window_handle = getattr(snapshot, "window_handle", None)

            if _is_positive_integer(process_id) and process_id in seen_processes:
                previous_window = seen_processes[process_id]
                raise DuplicateClientIdentityError(
                    "multiple matching windows reported process ID "
                    f"{process_id}: handles {previous_window} and {window_handle}"
                )
            if _is_positive_integer(process_id):
                seen_processes[process_id] = (
                    window_handle if _is_positive_integer(window_handle) else None
                )

            if _is_positive_integer(window_handle) and window_handle in seen_windows:
                previous_process = seen_windows[window_handle]
                raise DuplicateClientIdentityError(
                    "multiple matching processes reported window handle "
                    f"{window_handle}: PIDs {previous_process} and {process_id}"
                )
            if _is_positive_integer(window_handle):
                seen_windows[window_handle] = (
                    process_id if _is_positive_integer(process_id) else None
                )


def _is_positive_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


__all__ = [
    "ClientRegistryError",
    "ClientWindowRegistry",
    "DuplicateClientIdentityError",
    "derive_client_instance_id",
]
