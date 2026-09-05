"""Operational facade joining one manager session to the localhost dashboard."""

from __future__ import annotations

import ntpath
import threading
from contextlib import ExitStack
from math import isfinite
from typing import Protocol

from shadowbane_lab.client_extension.runtime_status import (
    ExtensionRuntimeSnapshot,
    ExtensionRuntimeState,
    unconfigured_extension_status,
)

from .dashboard import DashboardError
from .manifest import ManagedClientConfig, ManagerManifest
from .model import (
    ClientInstanceSnapshot,
    ClientRegistrySnapshot,
    RejectedWindowSnapshot,
)
from .operation import WorkerOperationSnapshot, WorkerOperationState
from .session import (
    ManagerSessionError,
    ManagerSessionSnapshot,
    ManagerSlotSnapshot,
)
from .worker import WorkerHealthState, WorkerSlotHealthSnapshot


class SessionControl(Protocol):
    """Session operations used by the local dashboard application."""

    def snapshot(self) -> ManagerSessionSnapshot: ...

    def status(self, client_id: str) -> ManagerSlotSnapshot: ...

    def refresh(self) -> ManagerSessionSnapshot: ...

    def start(
        self,
        client_id: str,
        *,
        timeout_seconds: float,
        poll_seconds: float,
    ) -> ManagerSlotSnapshot: ...

    def start_all(
        self,
        *,
        timeout_seconds: float,
        poll_seconds: float,
    ) -> ManagerSessionSnapshot: ...

    def attach(self, client_id: str, *, instance_id: str) -> ManagerSlotSnapshot: ...

    def tile(self, client_id: str) -> ManagerSlotSnapshot: ...

    def tile_all(self) -> ManagerSessionSnapshot: ...

    def pause(self, client_id: str) -> ManagerSlotSnapshot: ...

    def resume(self, client_id: str) -> ManagerSlotSnapshot: ...

    def detach(self, client_id: str) -> ManagerSlotSnapshot: ...

    def request_close(self, client_id: str) -> ManagerSlotSnapshot: ...


class ManifestRegistryProvider(Protocol):
    """Fresh manifest-wide registry used only for local status and candidate selection."""

    def inspect(self) -> ClientRegistrySnapshot: ...


class WorkerStatusProvider(Protocol):
    """Fail-closed health evaluation for workers attached to exact local slots."""

    def inspect(
        self,
        client_id: str,
        *,
        instance_id: str | None,
        lifecycle_dispatch_enabled: bool,
        renew_permit: bool = True,
    ) -> WorkerSlotHealthSnapshot: ...

    def revoke(self, client_id: str, *, reason: str) -> object: ...


class WorkerLifecycleControl(Protocol):
    """Launch and stop exact per-client worker process lifetimes."""

    def ensure_started(
        self,
        client_id: str,
        client: ClientInstanceSnapshot,
    ) -> int | None: ...

    def request_stop(self, client_id: str, *, reason: str) -> int: ...


class WorkerOperationStatusProvider(Protocol):
    """Read-only operation status for one node-local manifest slot."""

    def inspect_slot(self, client_id: str) -> tuple[WorkerOperationSnapshot, ...]: ...


class ExtensionStatusProvider(Protocol):
    """Read the extension state for one exact game-process lifetime."""

    def inspect(
        self,
        process_id: int | None,
        process_creation_filetime_utc: int | None,
    ) -> ExtensionRuntimeSnapshot: ...


def _require_positive_finite(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and positive")
    return float(value)


def _normalize_windows_path(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(ntpath.abspath(path))).casefold()


def _matches_config(client: ClientInstanceSnapshot, config: ManagedClientConfig) -> bool:
    if client.executable_path is None:
        return False
    allowed_names = {name.casefold() for name in config.expected_executable_names}
    return client.executable_name.casefold() in allowed_names and _normalize_windows_path(
        ntpath.dirname(client.executable_path)
    ) == _normalize_windows_path(str(config.expected_process_directory))


def _rejected_matches_config(
    window: RejectedWindowSnapshot,
    config: ManagedClientConfig,
) -> bool:
    if window.executable_path is None:
        return False
    allowed_names = {name.casefold() for name in config.expected_executable_names}
    return window.executable_name.casefold() in allowed_names and _normalize_windows_path(
        ntpath.dirname(window.executable_path)
    ) == _normalize_windows_path(str(config.expected_process_directory))


def _client_summary(client: ClientInstanceSnapshot) -> dict[str, object]:
    return {
        "instance_id": client.instance_id,
        "process_id": client.process_id,
        "process_started_at_100ns": client.process_started_at_100ns,
        "window_handle": client.window_handle,
        "executable_name": client.executable_name,
        "title": client.title,
        "is_foreground": client.is_foreground,
        "is_visible": client.is_visible,
        "client_bounds": {
            "left": client.client_bounds.left,
            "top": client.client_bounds.top,
            "width": client.client_bounds.width,
            "height": client.client_bounds.height,
        },
    }


def _rejected_summary(window: RejectedWindowSnapshot) -> dict[str, object]:
    return {
        "process_id": window.process_id,
        "process_started_at_100ns": window.process_started_at_100ns,
        "window_handle": window.window_handle,
        "executable_name": window.executable_name,
        "title": window.title,
        "reasons": [reason.value for reason in window.reasons],
    }


class ManagerDashboardApplication:
    """Expose reviewed local lifecycle actions without adding strategy or remote control."""

    def __init__(
        self,
        manifest: ManagerManifest,
        session: SessionControl,
        registry: ManifestRegistryProvider,
        worker_supervisor: WorkerStatusProvider,
        *,
        worker_controller: WorkerLifecycleControl | None = None,
        operation_status: WorkerOperationStatusProvider | None = None,
        extension_status: ExtensionStatusProvider | None = None,
        launch_timeout_seconds: float = 30.0,
        poll_seconds: float = 0.5,
    ) -> None:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        session_methods = (
            "snapshot",
            "status",
            "refresh",
            "start",
            "start_all",
            "attach",
            "tile",
            "tile_all",
            "pause",
            "resume",
            "detach",
            "request_close",
        )
        if any(not callable(getattr(session, method, None)) for method in session_methods):
            raise ValueError("session does not implement the dashboard session contract")
        if not callable(getattr(registry, "inspect", None)):
            raise ValueError("registry must provide inspect()")
        if any(
            not callable(getattr(worker_supervisor, method, None))
            for method in ("inspect", "revoke")
        ):
            raise ValueError("worker_supervisor must provide inspect() and revoke()")
        if worker_controller is not None and any(
            not callable(getattr(worker_controller, method, None))
            for method in ("ensure_started", "request_stop")
        ):
            raise ValueError("worker_controller must provide ensure_started() and request_stop()")
        if operation_status is not None and not callable(
            getattr(operation_status, "inspect_slot", None)
        ):
            raise ValueError("operation_status must provide inspect_slot()")
        if extension_status is not None and not callable(
            getattr(extension_status, "inspect", None)
        ):
            raise ValueError("extension_status must provide inspect()")
        self._manifest = manifest
        self._session = session
        self._registry = registry
        self._worker_supervisor = worker_supervisor
        self._worker_controller = worker_controller
        self._operation_status = operation_status
        self._extension_status = extension_status
        self._launch_timeout_seconds = _require_positive_finite(
            launch_timeout_seconds,
            "launch_timeout_seconds",
        )
        self._poll_seconds = _require_positive_finite(poll_seconds, "poll_seconds")
        self._configs = {config.client_id: config for config in manifest.clients}
        self._lock = threading.RLock()
        self._slot_locks = {key: threading.RLock() for key in self._configs}
        self._stopping = False
        self._renewal_lock = threading.RLock()

    def reconcile_instances(self) -> dict[str, object]:
        """Adopt safe open clients and archive bindings after an exact process exit."""

        with self._lock, ExitStack() as held:
            for lock in self._slot_locks.values():
                if not lock.acquire(blocking=False):
                    return {"adopted_client_ids": [], "archived_client_ids": [], "issues": []}
                held.callback(lock.release)
            before = self._session.snapshot()
            if not isinstance(before, ManagerSessionSnapshot) or (
                before.node_id != self._manifest.node_id
            ):
                raise RuntimeError("manager session returned an invalid snapshot")
            issues: list[dict[str, str]] = []
            try:
                self._session.refresh()
            except (ManagerSessionError, OSError, RuntimeError, ValueError) as exc:
                issues.append({"client_id": "manager", "detail": str(exc)})

            current = self._session.snapshot()
            if not isinstance(current, ManagerSessionSnapshot) or (
                current.node_id != self._manifest.node_id
            ):
                raise RuntimeError("manager session returned an invalid snapshot")
            current_by_id = {slot.client_id: slot for slot in current.slots}
            archived: list[str] = []
            for prior in before.slots:
                refreshed = current_by_id.get(prior.client_id)
                if (
                    prior.instance_id is None
                    or refreshed is None
                    or refreshed.instance_id is not None
                ):
                    continue
                archived.append(prior.client_id)
                reason = "exact game process exited; internal client ownership was archived"
                try:
                    self._worker_supervisor.revoke(prior.client_id, reason=reason)
                    if self._worker_controller is not None:
                        self._worker_controller.request_stop(prior.client_id, reason=reason)
                except (OSError, RuntimeError, ValueError) as exc:
                    issues.append({"client_id": prior.client_id, "detail": str(exc)})

            registry = self._registry.inspect()
            if not isinstance(registry, ClientRegistrySnapshot):
                raise RuntimeError("manifest registry returned an invalid snapshot")
            if registry.node_id != self._manifest.node_id:
                raise RuntimeError("manifest registry returned the wrong node")

            owned_instance_ids = {
                slot.instance_id for slot in current.slots if slot.instance_id is not None
            }
            free_client_ids = [slot.client_id for slot in current.slots if slot.instance_id is None]
            adopted: list[str] = []
            for client in registry.clients:
                if client.instance_id in owned_instance_ids:
                    continue
                client_id = next(
                    (
                        candidate_id
                        for candidate_id in free_client_ids
                        if _matches_config(client, self._configs[candidate_id])
                    ),
                    None,
                )
                if client_id is None:
                    continue
                try:
                    self._execute(
                        "attach",
                        client_id=client_id,
                        instance_id=client.instance_id,
                    )
                except (
                    DashboardError,
                    ManagerSessionError,
                    OSError,
                    RuntimeError,
                    ValueError,
                ) as exc:
                    issues.append({"client_id": client_id, "detail": str(exc)})
                    continue
                free_client_ids.remove(client_id)
                owned_instance_ids.add(client.instance_id)
                adopted.append(client_id)

            return {
                "adopted_client_ids": adopted,
                "archived_client_ids": archived,
                "issues": issues,
            }

    def status(self) -> dict[str, object]:
        """Return a fresh local inventory plus remembered exact slot bindings."""

        with self._lock:
            registry = self._registry.inspect()
            if not isinstance(registry, ClientRegistrySnapshot):
                raise RuntimeError("manifest registry returned an invalid snapshot")
            if registry.node_id != self._manifest.node_id:
                raise RuntimeError("manifest registry returned the wrong node")
            session = self._session.snapshot()
            if not isinstance(session, ManagerSessionSnapshot):
                raise RuntimeError("manager session returned an invalid snapshot")
            if session.node_id != self._manifest.node_id:
                raise RuntimeError("manager session returned the wrong node")

            clients_by_id = {client.instance_id: client for client in registry.clients}
            current_bound_ids: set[str] = set()
            current_bindings: dict[str, ClientInstanceSnapshot] = {}
            for slot in session.slots:
                config = self._configs.get(slot.client_id)
                if config is None:
                    raise RuntimeError("manager session returned an unknown manifest slot")
                if slot.instance_id is None:
                    continue
                current = clients_by_id.get(slot.instance_id)
                if current is not None and _matches_config(current, config):
                    current_bound_ids.add(slot.instance_id)
                    current_bindings[slot.client_id] = current
            slots: list[dict[str, object]] = []
            healthy_worker_count = 0
            dispatch_ready_count = 0
            extension_ready_count = 0
            for slot in session.slots:
                config = self._configs.get(slot.client_id)
                if config is None:
                    raise RuntimeError("manager session returned an unknown manifest slot")
                payload = slot.to_dict()
                binding = current_bindings.get(slot.client_id)
                if slot.instance_id is not None and binding is None:
                    payload["state"] = "stale"
                    payload["dispatch_enabled"] = False
                    payload["status_detail"] = (
                        "exact bound process/window identity is absent from current registry"
                    )
                lifecycle_dispatch_enabled = bool(payload["dispatch_enabled"])
                worker = self._worker_supervisor.inspect(
                    slot.client_id,
                    instance_id=None if binding is None else binding.instance_id,
                    lifecycle_dispatch_enabled=lifecycle_dispatch_enabled,
                    renew_permit=False,
                )
                if not isinstance(worker, WorkerSlotHealthSnapshot):
                    raise RuntimeError("worker supervisor returned an invalid snapshot")
                if worker.client_id != slot.client_id:
                    raise RuntimeError("worker supervisor returned the wrong manifest slot")
                if worker.state is WorkerHealthState.HEALTHY:
                    healthy_worker_count += 1
                if worker.dispatch_allowed:
                    dispatch_ready_count += 1
                payload["lifecycle_dispatch_enabled"] = lifecycle_dispatch_enabled
                payload["dispatch_enabled"] = worker.dispatch_allowed
                payload["worker"] = worker.to_dict()
                extension = self._extension_summary(binding)
                if extension.state is ExtensionRuntimeState.INITIALIZED:
                    extension_ready_count += 1
                payload["extension"] = extension.to_dict()
                payload["operation"] = self._operation_summary(
                    slot.client_id,
                    instance_id=None if binding is None else binding.instance_id,
                )
                payload["binding"] = None if binding is None else _client_summary(binding)
                payload["candidates"] = [
                    _client_summary(client)
                    for client in registry.clients
                    if client.instance_id not in current_bound_ids
                    and _matches_config(client, config)
                ]
                payload["rejected_windows"] = [
                    _rejected_summary(window)
                    for window in registry.rejected
                    if _rejected_matches_config(window, config)
                ]
                slots.append(payload)

            return {
                "ok": True,
                "schema_version": session.schema_version,
                "node_id": session.node_id,
                "configured_count": len(slots),
                "bound_count": len(current_bound_ids),
                "healthy_worker_count": healthy_worker_count,
                "dispatch_ready_count": dispatch_ready_count,
                "extension_ready_count": extension_ready_count,
                "slots": slots,
            }

    def _extension_summary(
        self,
        binding: ClientInstanceSnapshot | None,
    ) -> ExtensionRuntimeSnapshot:
        if self._extension_status is None:
            return unconfigured_extension_status()
        result = self._extension_status.inspect(
            None if binding is None else binding.process_id,
            None if binding is None else binding.process_started_at_100ns,
        )
        if not isinstance(result, ExtensionRuntimeSnapshot):
            raise RuntimeError("extension status provider returned an invalid snapshot")
        return result

    def _operation_summary(
        self,
        client_id: str,
        *,
        instance_id: str | None,
    ) -> dict[str, object]:
        if self._operation_status is None:
            return {"queued_count": 0, "active": None, "latest_result": None}
        snapshots = self._operation_status.inspect_slot(client_id)
        if not isinstance(snapshots, tuple) or any(
            not isinstance(item, WorkerOperationSnapshot) for item in snapshots
        ):
            raise RuntimeError("operation status provider returned an invalid snapshot")
        relevant = tuple(
            snapshot
            for snapshot in snapshots
            if instance_id is None or snapshot.operation.instance_id == instance_id
        )
        queued = tuple(snapshot for snapshot in relevant if snapshot.receipt is None)
        active = next(
            (
                snapshot
                for snapshot in reversed(relevant)
                if snapshot.receipt is not None
                and snapshot.receipt.state
                in {WorkerOperationState.ACCEPTED, WorkerOperationState.ACTIVE}
            ),
            None,
        )
        latest_result = next(
            (
                snapshot
                for snapshot in reversed(relevant)
                if snapshot.receipt is not None and snapshot.receipt.state.terminal
            ),
            None,
        )
        return {
            "queued_count": len(queued),
            "active": None if active is None else active.to_dict(),
            "latest_result": (None if latest_result is None else latest_result.to_dict()),
        }

    def execute(
        self,
        action: str,
        *,
        client_id: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, object]:
        """Execute one route-validated action and preserve exact binding ownership."""

        if action == "start-all":
            self._require_global(action, client_id, instance_id)
            for key in self._configs:
                if self._session.status(key).instance_id is None:
                    self.execute("start", client_id=key)
            return {"ok": True, "action": action}
        lock = self._slot_locks.get(client_id, self._lock)
        with lock:
            try:
                if self._stopping:
                    raise DashboardError("manager-stopping", "manager is stopping")
                self._execute(action, client_id=client_id, instance_id=instance_id)
            except DashboardError:
                raise
            except (ManagerSessionError, OSError, RuntimeError, ValueError) as exc:
                raise DashboardError("manager-action-failed", str(exc)) from exc
            return {"ok": True, "action": action}

    def supervise(self) -> None:
        """Renew permits independently of dashboard construction and launch polling."""
        with self._renewal_lock:
            registry = self._registry.inspect()
            clients = {client.instance_id: client for client in registry.clients}
            for client_id, lock in self._slot_locks.items():
                if not lock.acquire(blocking=False):
                    continue
                try:
                    slot = self._session.status(client_id)
                    self._worker_supervisor.inspect(
                        client_id,
                        instance_id=slot.instance_id,
                        lifecycle_dispatch_enabled=(
                            slot.dispatch_enabled
                            and not self._stopping
                            and slot.instance_id in clients
                            and _matches_config(clients[slot.instance_id], self._configs[client_id])
                        ),
                    )
                finally:
                    lock.release()

    def _execute(
        self,
        action: str,
        *,
        client_id: str | None,
        instance_id: str | None,
    ) -> None:
        if action == "start-all":
            self._require_global(action, client_id, instance_id)
            self._require_clear_launch_baseline()
            self._revoke_unbound_slots("group launch invalidated prior worker ownership")
            self._session.start_all(
                timeout_seconds=self._launch_timeout_seconds,
                poll_seconds=self._poll_seconds,
            )
            self._ensure_workers_for_bound_slots()
            return
        if action == "refresh":
            self._require_global(action, client_id, instance_id)
            self._session.refresh()
            return
        if action == "tile-all":
            self._require_global(action, client_id, instance_id)
            self._session.tile_all()
            return
        if client_id is None:
            raise DashboardError("invalid-action-fields", f"{action} requires client_id")
        if action == "start":
            if instance_id is not None:
                raise DashboardError("invalid-action-fields", "start does not accept instance_id")
            self._require_clear_launch_baseline(client_id=client_id)
            self._worker_supervisor.revoke(
                client_id,
                reason="client launch invalidated prior worker ownership",
            )
            if self._worker_controller is not None:
                self._worker_controller.request_stop(
                    client_id,
                    reason="client launch replaced prior worker ownership",
                )
            self._session.start(
                client_id,
                timeout_seconds=self._launch_timeout_seconds,
                poll_seconds=self._poll_seconds,
            )
            self._ensure_worker_for_slot(client_id)
            return
        if instance_id is None:
            raise DashboardError("invalid-action-fields", f"{action} requires instance_id")
        if action == "attach":
            self._worker_supervisor.revoke(
                client_id,
                reason="exact client attachment requires a new worker ownership lease",
            )
            if self._worker_controller is not None:
                self._worker_controller.request_stop(
                    client_id,
                    reason="exact client attachment replaced prior worker ownership",
                )
            self._session.attach(client_id, instance_id=instance_id)
            self._ensure_worker_for_slot(client_id)
            return
        self._require_exact_binding(client_id, instance_id)
        if action in {"pause", "detach", "close"}:
            self._worker_supervisor.revoke(
                client_id,
                reason=f"manager {action} action revoked worker dispatch",
            )
        if action in {"detach", "close"}:
            if self._worker_controller is not None:
                self._worker_controller.request_stop(
                    client_id,
                    reason=f"manager {action} action ended exact worker ownership",
                )
        actions = {
            "tile": self._session.tile,
            "pause": self._session.pause,
            "resume": self._session.resume,
            "detach": self._session.detach,
            "close": self._session.request_close,
        }
        operation = actions.get(action)
        if operation is None:
            raise DashboardError("unknown-action", "The manager action is not supported.")
        operation(client_id)
        if action == "resume":
            self._ensure_worker_for_slot(client_id)

    def revoke_all_workers(self, *, reason: str) -> None:
        """Fail closed synchronously before the manager process shuts down."""

        with self._renewal_lock:
            self._stopping = True
            for config in self._manifest.clients:
                self._worker_supervisor.revoke(config.client_id, reason=reason)

    def _revoke_unbound_slots(self, reason: str) -> None:
        session = self._session.snapshot()
        if not isinstance(session, ManagerSessionSnapshot) or (
            session.node_id != self._manifest.node_id
        ):
            raise RuntimeError("manager session returned an invalid snapshot")
        for slot in session.slots:
            if slot.instance_id is None:
                self._worker_supervisor.revoke(slot.client_id, reason=reason)
                if self._worker_controller is not None:
                    self._worker_controller.request_stop(slot.client_id, reason=reason)

    def _ensure_workers_for_bound_slots(self) -> None:
        if self._worker_controller is None:
            return
        session = self._session.snapshot()
        if not isinstance(session, ManagerSessionSnapshot):
            raise RuntimeError("manager session returned an invalid snapshot")
        for slot in session.slots:
            if slot.instance_id is not None:
                self._ensure_worker_for_slot(slot.client_id)

    def _ensure_worker_for_slot(self, client_id: str) -> None:
        if self._stopping or self._worker_controller is None:
            return
        slot = self._session.status(client_id)
        if not isinstance(slot, ManagerSlotSnapshot) or slot.instance_id is None:
            raise RuntimeError("manager slot has no exact binding for worker bootstrap")
        registry = self._registry.inspect()
        if not isinstance(registry, ClientRegistrySnapshot):
            raise RuntimeError("manifest registry returned an invalid worker baseline")
        config = self._configs.get(client_id)
        if config is None:
            raise RuntimeError("manager session returned an unknown manifest slot")
        matches = tuple(
            client
            for client in registry.clients
            if client.instance_id == slot.instance_id and _matches_config(client, config)
        )
        if len(matches) != 1:
            raise RuntimeError(
                "exact bound process/window identity is unavailable for worker bootstrap"
            )
        self._worker_controller.ensure_started(client_id, matches[0])

    def _require_clear_launch_baseline(self, *, client_id: str | None = None) -> None:
        registry = self._registry.inspect()
        session = self._session.snapshot()
        if not isinstance(registry, ClientRegistrySnapshot) or (
            registry.node_id != self._manifest.node_id
        ):
            raise RuntimeError("manifest registry returned an invalid launch baseline")
        if not isinstance(session, ManagerSessionSnapshot) or (
            session.node_id != self._manifest.node_id
        ):
            raise RuntimeError("manager session returned an invalid launch baseline")
        bound_ids = {slot.instance_id for slot in session.slots if slot.instance_id is not None}
        for slot in session.slots:
            if slot.instance_id is not None or (
                client_id is not None and slot.client_id != client_id
            ):
                continue
            config = self._configs.get(slot.client_id)
            if config is None:
                raise RuntimeError("manager session returned an unknown manifest slot")
            if any(
                window.instance_id not in bound_ids and _matches_config(window, config)
                for window in registry.clients
            ):
                raise DashboardError(
                    "attach-selection-required",
                    f"{slot.client_id} has an existing matching client; attach it explicitly "
                    "before launching another slot.",
                )
            if any(_rejected_matches_config(window, config) for window in registry.rejected):
                raise DashboardError(
                    "unsafe-client-identity",
                    f"{slot.client_id} has a matching window with incomplete identity.",
                )

    @staticmethod
    def _require_global(
        action: str,
        client_id: str | None,
        instance_id: str | None,
    ) -> None:
        if client_id is not None or instance_id is not None:
            raise DashboardError(
                "invalid-action-fields",
                f"{action} does not accept client_id or instance_id",
            )

    def _require_exact_binding(self, client_id: str, instance_id: str) -> None:
        slot = self._session.status(client_id)
        if not isinstance(slot, ManagerSlotSnapshot):
            raise RuntimeError("manager session returned an invalid slot snapshot")
        if slot.instance_id != instance_id:
            raise DashboardError(
                "stale-instance-selection",
                "The selected instance no longer owns this slot; refresh before retrying.",
            )


__all__ = [
    "ManagerDashboardApplication",
    "ManifestRegistryProvider",
    "SessionControl",
    "WorkerStatusProvider",
    "WorkerLifecycleControl",
    "WorkerOperationStatusProvider",
]
