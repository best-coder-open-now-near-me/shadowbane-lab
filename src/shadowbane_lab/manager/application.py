"""Operational facade joining one manager session to the localhost dashboard."""

from __future__ import annotations

import ntpath
import threading
from math import isfinite
from typing import Protocol

from .dashboard import DashboardError
from .manifest import ManagedClientConfig, ManagerManifest
from .model import (
    ClientInstanceSnapshot,
    ClientRegistrySnapshot,
    RejectedWindowSnapshot,
)
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
            raise ValueError(
                "worker_controller must provide ensure_started() and request_stop()"
            )
        self._manifest = manifest
        self._session = session
        self._registry = registry
        self._worker_supervisor = worker_supervisor
        self._worker_controller = worker_controller
        self._launch_timeout_seconds = _require_positive_finite(
            launch_timeout_seconds,
            "launch_timeout_seconds",
        )
        self._poll_seconds = _require_positive_finite(poll_seconds, "poll_seconds")
        self._configs = {config.client_id: config for config in manifest.clients}
        self._lock = threading.RLock()

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
                "slots": slots,
            }

    def execute(
        self,
        action: str,
        *,
        client_id: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, object]:
        """Execute one route-validated action and preserve exact binding ownership."""

        with self._lock:
            try:
                self._execute(action, client_id=client_id, instance_id=instance_id)
            except DashboardError:
                raise
            except (ManagerSessionError, OSError, RuntimeError, ValueError) as exc:
                raise DashboardError("manager-action-failed", str(exc)) from exc
            return {"ok": True, "action": action}

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

        with self._lock:
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
        if self._worker_controller is None:
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
]
