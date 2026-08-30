"""Live, transactional expansion of immutable manager application topologies."""

from __future__ import annotations

import json
import os
import threading
import time
from os import PathLike
from pathlib import Path
from typing import Protocol, runtime_checkable

from .dashboard import DashboardError
from .manifest import (
    MAX_MANAGER_CLIENT_SLOTS,
    ManagerManifest,
    ManagerManifestError,
    expand_manager_slots,
    load_manager_manifest,
)


@runtime_checkable
class ManagedDashboardApplication(Protocol):
    """Immutable application graph owned by the live configuration facade."""

    def status(self) -> dict[str, object]: ...

    def execute(
        self,
        action: str,
        *,
        client_id: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, object]: ...

    def reconcile_instances(self) -> dict[str, object]: ...

    def revoke_all_workers(self, *, reason: str) -> None: ...


@runtime_checkable
class ManagerApplicationFactory(Protocol):
    def __call__(self, manifest: ManagerManifest) -> ManagedDashboardApplication: ...


def _manifest_display_bounds(manifest: ManagerManifest) -> tuple[int, int, int, int]:
    tiles = tuple(client.window_tile for client in manifest.clients)
    if any(tile is None for tile in tiles):
        raise ManagerManifestError(
            "every current client slot needs a window_tile before slots can be added live"
        )
    concrete = tuple(tile for tile in tiles if tile is not None)
    left = min(tile.left for tile in concrete)
    top = min(tile.top for tile in concrete)
    right = max(tile.left + tile.width for tile in concrete)
    bottom = max(tile.top + tile.height for tile in concrete)
    return left, top, right - left, bottom - top


def replace_manager_manifest(
    path: str | PathLike[str],
    *,
    expected: ManagerManifest,
    replacement: ManagerManifest,
) -> Path:
    """Compare, validate, back up, and atomically replace one manifest."""

    if not isinstance(expected, ManagerManifest):
        raise ValueError("expected must be ManagerManifest")
    if not isinstance(replacement, ManagerManifest):
        raise ValueError("replacement must be ManagerManifest")
    manifest_path = Path(path).resolve(strict=False)
    if not manifest_path.exists() or manifest_path.is_symlink() or not manifest_path.is_file():
        raise ManagerManifestError(
            f"manager manifest must be an existing regular file: {manifest_path}"
        )
    current = load_manager_manifest(manifest_path)
    if current != expected:
        raise ManagerManifestError(
            "manager manifest changed after it was loaded; refresh before configuring slots"
        )

    temporary_path = manifest_path.with_name(
        f".{manifest_path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    backup_path = manifest_path.with_name(
        f"{manifest_path.stem}.before-slots-{time.time_ns()}{manifest_path.suffix}"
    )
    payload = (
        json.dumps(replacement.to_dict(), indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    try:
        with temporary_path.open("xb") as destination:
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
        if load_manager_manifest(temporary_path) != replacement:
            raise RuntimeError("written manager manifest did not round-trip exactly")
        manifest_path.replace(backup_path)
        try:
            temporary_path.replace(manifest_path)
        except OSError:
            backup_path.replace(manifest_path)
            raise
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return backup_path


class LiveConfiguredManagerApplication:
    """Present live game instances while internal slot capacity grows as needed."""

    def __init__(
        self,
        manifest_path: str | PathLike[str],
        manifest: ManagerManifest,
        factory: ManagerApplicationFactory,
    ) -> None:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        if not isinstance(factory, ManagerApplicationFactory):
            raise ValueError("factory must implement ManagerApplicationFactory")
        self._manifest_path = Path(manifest_path).resolve(strict=False)
        self._factory = factory
        self._manifest = manifest
        self._application = factory(manifest)
        self._lock = threading.RLock()

    def status(self) -> dict[str, object]:
        with self._lock:
            reconciliation = self._ensure_capacity_for_current_instances()
            status = dict(self._application.status())
            slots = status.get("slots")
            all_slots = slots if isinstance(slots, list) else []
            active_slots = [
                slot
                for slot in all_slots
                if isinstance(slot, dict) and isinstance(slot.get("instance_id"), str)
            ]
            status["slots"] = active_slots
            status["open_count"] = len(active_slots)
            status["can_add_client"] = self._has_free_slot(all_slots) or (
                len(self._manifest.clients) < MAX_MANAGER_CLIENT_SLOTS
            )
            status["reconciliation"] = reconciliation
            return status

    def execute(
        self,
        action: str,
        *,
        client_id: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, object]:
        with self._lock:
            if action == "add-client":
                if client_id is not None or instance_id is not None:
                    raise DashboardError(
                        "invalid-action-fields",
                        "add-client does not accept client or instance identity fields.",
                    )
                return self._add_client()
            return self._application.execute(
                action,
                client_id=client_id,
                instance_id=instance_id,
            )

    def _add_client(self) -> dict[str, object]:
        self._ensure_capacity_for_current_instances()
        status = self._application.status()
        client_id = self._first_free_client_id(status)
        expanded = False
        if client_id is None:
            current_count = len(self._manifest.clients)
            if current_count >= MAX_MANAGER_CLIENT_SLOTS:
                raise DashboardError(
                    "client-limit-reached",
                    f"No more than {MAX_MANAGER_CLIENT_SLOTS} clients can be managed.",
                )
            self._expand_capacity(current_count + 1, status)
            client_id = self._manifest.clients[-1].client_id
            expanded = True
        self._application.execute("start", client_id=client_id)
        return {
            "ok": True,
            "action": "add-client",
            "client_id": client_id,
            "capacity_expanded": expanded,
        }

    def _ensure_capacity_for_current_instances(self) -> dict[str, object]:
        reconciliation = self._application.reconcile_instances()
        status = self._application.status()
        slots = status.get("slots")
        all_slots = slots if isinstance(slots, list) else []
        observed_instance_ids = {
            instance_id
            for slot in all_slots
            if isinstance(slot, dict)
            for instance_id in self._observed_instance_ids(slot)
        }
        if len(observed_instance_ids) > len(self._manifest.clients):
            self._expand_capacity(len(observed_instance_ids), status)
            reconciliation = self._application.reconcile_instances()
        return reconciliation

    def _expand_capacity(
        self,
        client_count: int,
        current_status: dict[str, object],
    ) -> None:
        if client_count > MAX_MANAGER_CLIENT_SLOTS:
            raise DashboardError(
                "client-limit-reached",
                f"No more than {MAX_MANAGER_CLIENT_SLOTS} clients can be managed.",
            )
        left, top, width, height = _manifest_display_bounds(self._manifest)
        configured = expand_manager_slots(
            self._manifest,
            client_count,
            display_left=left,
            display_top=top,
            display_width=width,
            display_height=height,
        )
        prior_bindings = self._bound_instances(current_status)
        candidate = self._factory(configured)
        candidate_status = candidate.status()
        candidate_bindings = self._bound_instances(candidate_status)
        claimed_instances = set(candidate_bindings.values())
        for client_id, instance_id in prior_bindings.items():
            recovered = candidate_bindings.get(client_id)
            if recovered == instance_id:
                continue
            if recovered is not None or instance_id in claimed_instances:
                raise DashboardError(
                    "binding-migration-conflict",
                    "Internal capacity could not grow without changing a live client identity.",
                )
            candidate.execute("attach", client_id=client_id, instance_id=instance_id)
            claimed_instances.add(instance_id)

        verified_bindings = self._bound_instances(candidate.status())
        if any(verified_bindings.get(key) != value for key, value in prior_bindings.items()):
            raise DashboardError(
                "binding-migration-failed",
                "Internal capacity grew, but a live client identity was not preserved.",
            )
        if load_manager_manifest(self._manifest_path) != self._manifest:
            raise DashboardError(
                "configuration-out-of-date",
                "The manager configuration changed on disk; retry the client action.",
            )
        replace_manager_manifest(
            self._manifest_path,
            expected=self._manifest,
            replacement=configured,
        )
        self._manifest = configured
        self._application = candidate

    @staticmethod
    def _observed_instance_ids(slot: dict[str, object]) -> tuple[str, ...]:
        values: list[str] = []
        instance_id = slot.get("instance_id")
        if isinstance(instance_id, str):
            values.append(instance_id)
        candidates = slot.get("candidates")
        if isinstance(candidates, list):
            values.extend(
                candidate_id
                for candidate in candidates
                if isinstance(candidate, dict)
                and isinstance((candidate_id := candidate.get("instance_id")), str)
            )
        return tuple(values)

    @staticmethod
    def _bound_instances(status: dict[str, object]) -> dict[str, str]:
        slots = status.get("slots")
        if not isinstance(slots, list):
            return {}
        return {
            client_id: instance_id
            for slot in slots
            if isinstance(slot, dict)
            and isinstance((client_id := slot.get("client_id")), str)
            and isinstance((instance_id := slot.get("instance_id")), str)
        }

    @staticmethod
    def _first_free_client_id(status: dict[str, object]) -> str | None:
        slots = status.get("slots")
        if not isinstance(slots, list):
            return None
        return next(
            (
                client_id
                for slot in slots
                if isinstance(slot, dict)
                and slot.get("instance_id") is None
                and isinstance((client_id := slot.get("client_id")), str)
            ),
            None,
        )

    @classmethod
    def _has_free_slot(cls, slots: list[object]) -> bool:
        return cls._first_free_client_id({"slots": slots}) is not None

    def revoke_all_workers(self, *, reason: str) -> None:
        with self._lock:
            self._application.revoke_all_workers(reason=reason)


__all__ = [
    "LiveConfiguredManagerApplication",
    "ManagedDashboardApplication",
    "ManagerApplicationFactory",
    "replace_manager_manifest",
]
