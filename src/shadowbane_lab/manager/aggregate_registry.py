"""Manifest-wide, single-scan registry snapshots for guarded window actions."""

from __future__ import annotations

import ntpath

from shadowbane_lab.client_input import (
    StaticVisibleWindowInspector,
    VisibleWindowInspector,
    WindowSnapshot,
)

from .manifest import ManagerManifest
from .model import ClientInstanceSnapshot, ClientRegistrySnapshot, RejectedWindowSnapshot
from .registry import ClientRegistryError, ClientWindowRegistry
from .supervisor import ClientInstanceSelector, selector_from_config


class AggregateRegistryError(ClientRegistryError):
    """Raised when a manifest-wide registry snapshot cannot be built safely."""


class AggregateRegistryConflictError(AggregateRegistryError):
    """Raised when separately filtered windows conflict on immutable identity."""


def _normalized_windows_path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(ntpath.abspath(value))).casefold()


def _selector_key(selector: ClientInstanceSelector, executable_name: str) -> tuple[str, str]:
    return (
        _normalized_windows_path(selector.process_directory),
        executable_name.casefold(),
    )


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


class ManifestClientRegistryProvider:
    """Return a fresh union of only the client windows selected by one manifest.

    Each refresh enumerates visible windows exactly once.  The captured tuple is then
    classified through the existing strict registry for every unique exact
    directory/executable selector in the manifest.
    """

    def __init__(
        self,
        inspector: VisibleWindowInspector,
        manifest: ManagerManifest,
    ) -> None:
        if not isinstance(inspector, VisibleWindowInspector):
            raise ValueError("inspector must implement VisibleWindowInspector")
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        self._inspector = inspector
        self._manifest = manifest
        self._selectors = _exact_selectors(manifest)

    def inspect(self) -> ClientRegistrySnapshot:
        windows = self._inspector.inspect_all()
        if not isinstance(windows, tuple) or any(
            not isinstance(window, WindowSnapshot) for window in windows
        ):
            raise AggregateRegistryError(
                "visible-window inspector must return a tuple of WindowSnapshot values"
            )

        captured = StaticVisibleWindowInspector(windows)
        clients: list[ClientInstanceSnapshot] = []
        rejected: list[RejectedWindowSnapshot] = []
        for selector in self._selectors:
            snapshot = ClientWindowRegistry(
                captured,
                node_id=selector.node_id,
                executable_names=selector.executable_names,
                process_directory=selector.process_directory,
            ).inspect()
            self._require_consistent_node(snapshot)
            clients.extend(snapshot.clients)
            rejected.extend(snapshot.rejected)

        unique_clients = _deduplicate_and_validate(clients, rejected)
        return ClientRegistrySnapshot(
            node_id=self._manifest.node_id,
            clients=tuple(sorted(unique_clients, key=_client_sort_key)),
            rejected=tuple(sorted(rejected, key=_rejected_sort_key)),
        )

    def _require_consistent_node(self, snapshot: object) -> None:
        if not isinstance(snapshot, ClientRegistrySnapshot):
            raise AggregateRegistryError("filtered registry must return ClientRegistrySnapshot")
        if snapshot.node_id != self._manifest.node_id:
            raise AggregateRegistryError(
                f"filtered registry returned node {snapshot.node_id!r}, "
                f"expected {self._manifest.node_id!r}"
            )
        if any(client.node_id != self._manifest.node_id for client in snapshot.clients):
            raise AggregateRegistryError("filtered registry returned a client from another node")
        if any(window.node_id != self._manifest.node_id for window in snapshot.rejected):
            raise AggregateRegistryError(
                "filtered registry returned a rejected window from another node"
            )


def _exact_selectors(manifest: ManagerManifest) -> tuple[ClientInstanceSelector, ...]:
    """Expand manifest name sets into unique exact directory/name classifiers."""

    selectors: dict[tuple[str, str], ClientInstanceSelector] = {}
    for config in manifest.clients:
        configured = selector_from_config(manifest.node_id, config)
        for executable_name in configured.executable_names:
            key = _selector_key(configured, executable_name)
            selectors.setdefault(
                key,
                ClientInstanceSelector(
                    node_id=configured.node_id,
                    executable_names=(executable_name,),
                    process_directory=configured.process_directory,
                ),
            )
    return tuple(selectors[key] for key in sorted(selectors))


def _deduplicate_and_validate(
    clients: list[ClientInstanceSnapshot],
    rejected: list[RejectedWindowSnapshot],
) -> tuple[ClientInstanceSnapshot, ...]:
    by_instance: dict[str, ClientInstanceSnapshot] = {}
    process_owners: dict[int, object] = {}
    window_owners: dict[int, object] = {}

    for client in clients:
        previous = by_instance.get(client.instance_id)
        if previous is not None:
            if previous == client:
                continue
            raise AggregateRegistryConflictError(
                f"instance ID {client.instance_id} maps to conflicting windows"
            )
        _claim_identity(
            client,
            process_id=client.process_id,
            window_handle=client.window_handle,
            process_owners=process_owners,
            window_owners=window_owners,
        )
        by_instance[client.instance_id] = client

    for window in rejected:
        _claim_identity(
            window,
            process_id=window.process_id,
            window_handle=window.window_handle,
            process_owners=process_owners,
            window_owners=window_owners,
        )

    return tuple(by_instance.values())


def _claim_identity(
    owner: object,
    *,
    process_id: int | None,
    window_handle: int | None,
    process_owners: dict[int, object],
    window_owners: dict[int, object],
) -> None:
    if process_id is not None:
        previous = process_owners.get(process_id)
        if previous is not None and previous != owner:
            raise AggregateRegistryConflictError(
                f"process ID {process_id} maps to conflicting windows"
            )
        process_owners[process_id] = owner
    if window_handle is not None:
        previous = window_owners.get(window_handle)
        if previous is not None and previous != owner:
            raise AggregateRegistryConflictError(
                f"window handle {window_handle} maps to conflicting processes"
            )
        window_owners[window_handle] = owner


__all__ = [
    "AggregateRegistryConflictError",
    "AggregateRegistryError",
    "ManifestClientRegistryProvider",
]
