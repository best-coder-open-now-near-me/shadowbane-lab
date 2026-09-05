"""Persistent per-node coordination over manifest slots and exact client bindings.

``ManagerSession`` is deliberately operational.  It remembers which immutable
process/window lifetime owns each local manifest slot, but contains no account,
character, chat, or tactical-role state.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from math import isfinite
from typing import Protocol

from .manifest import ManagedClientConfig, ManagerManifest
from .supervisor import (
    ClientInstanceSelector,
    LaunchProvenance,
    ManagedClientSnapshot,
    ManagedClientState,
    ReviewedLaunchCommand,
    launch_command_from_config,
    selector_from_config,
    window_rectangle_from_config,
)
from .window_control import WindowRectangle

MANAGER_SESSION_SCHEMA_VERSION = 1


class ManagerSessionError(RuntimeError):
    """Base class for manager-session failures."""


class UnknownSessionClientError(ManagerSessionError):
    """Raised when a logical manifest client ID is unknown."""


class SessionSlotBoundError(ManagerSessionError):
    """Raised when an action would silently replace an exact slot binding."""


class SessionSlotUnboundError(ManagerSessionError):
    """Raised when an action requires a slot's exact instance binding."""


class SessionActionError(ManagerSessionError):
    """Raised after an operation failure has been recorded on its slot."""


class SupervisorSessionContractError(ManagerSessionError):
    """Raised when an injected lifecycle supervisor violates its contract."""


class ManagerSlotState(StrEnum):
    CONFIGURED = "configured"
    ATTACHED = "attached"
    PAUSED = "paused"
    CLOSE_REQUESTED = "close_requested"
    STALE = "stale"
    DETACHED = "detached"
    CLOSED = "closed"


_BOUND_STATES = frozenset(
    {
        ManagerSlotState.ATTACHED,
        ManagerSlotState.PAUSED,
        ManagerSlotState.CLOSE_REQUESTED,
        ManagerSlotState.STALE,
    }
)


def _require_canonical_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or "\0" in value:
        raise ValueError(f"{field_name} must be canonical non-empty text without NUL")
    return value


def _require_optional_detail(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_canonical_text(value, field_name)


def _require_optional_time(value: float | None, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric or None")
    if not isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ManagerSlotSnapshot:
    """Serializable status for one logical client slot on this node."""

    client_id: str
    state: ManagerSlotState
    instance_id: str | None
    dispatch_enabled: bool
    launched_by_manager: bool
    launcher_process_id: int | None
    launcher_process_started_at_100ns: int | None
    launch_provenance: LaunchProvenance | None
    attached_at: float | None
    last_verified_at: float | None
    window_tile: tuple[int, int, int, int] | None
    status_detail: str | None = None
    failure_detail: str | None = None

    def __post_init__(self) -> None:
        _require_canonical_text(self.client_id, "client_id")
        if not isinstance(self.state, ManagerSlotState):
            raise ValueError("state must be ManagerSlotState")
        if self.instance_id is not None:
            _require_canonical_text(self.instance_id, "instance_id")
        if (self.instance_id is not None) != (self.state in _BOUND_STATES):
            raise ValueError("only bound slot states may carry an instance_id")
        if not isinstance(self.dispatch_enabled, bool):
            raise ValueError("dispatch_enabled must be a boolean")
        if self.dispatch_enabled != (self.state is ManagerSlotState.ATTACHED):
            raise ValueError("dispatch is enabled only for attached slots")
        if not isinstance(self.launched_by_manager, bool):
            raise ValueError("launched_by_manager must be a boolean")
        if self.launcher_process_id is not None and (
            isinstance(self.launcher_process_id, bool)
            or not isinstance(self.launcher_process_id, int)
            or self.launcher_process_id <= 0
        ):
            raise ValueError("launcher_process_id must be a positive integer or None")
        if self.launcher_process_started_at_100ns is not None and (
            isinstance(self.launcher_process_started_at_100ns, bool)
            or not isinstance(self.launcher_process_started_at_100ns, int)
            or self.launcher_process_started_at_100ns <= 0
        ):
            raise ValueError("launcher_process_started_at_100ns must be a positive integer or None")
        has_launch_provenance = (
            self.launcher_process_id is not None
            and self.launcher_process_started_at_100ns is not None
            and self.launch_provenance is not None
        )
        if self.launched_by_manager != has_launch_provenance:
            raise ValueError(
                "manager-launched slots require complete launcher identity and provenance"
            )
        if self.launch_provenance is not None and not isinstance(
            self.launch_provenance, LaunchProvenance
        ):
            raise ValueError("launch_provenance must be LaunchProvenance or None")
        if not self.launched_by_manager and (
            self.launcher_process_id is not None
            or self.launcher_process_started_at_100ns is not None
            or self.launch_provenance is not None
        ):
            raise ValueError("externally attached slots must not carry launch provenance")
        if self.instance_id is None and (
            self.launched_by_manager
            or self.attached_at is not None
            or self.last_verified_at is not None
        ):
            raise ValueError("unbound slots must not retain process-lifetime metadata")
        _require_optional_time(self.attached_at, "attached_at")
        _require_optional_time(self.last_verified_at, "last_verified_at")
        if (
            self.attached_at is not None
            and self.last_verified_at is not None
            and self.last_verified_at < self.attached_at
        ):
            raise ValueError("last_verified_at must not precede attached_at")
        if self.window_tile is not None:
            if (
                not isinstance(self.window_tile, tuple)
                or len(self.window_tile) != 4
                or any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in self.window_tile
                )
                or self.window_tile[2] <= 0
                or self.window_tile[3] <= 0
            ):
                raise ValueError("window_tile must be an immutable left/top/width/height tuple")
        _require_optional_detail(self.status_detail, "status_detail")
        _require_optional_detail(self.failure_detail, "failure_detail")

    def to_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "state": self.state.value,
            "instance_id": self.instance_id,
            "dispatch_enabled": self.dispatch_enabled,
            "launched_by_manager": self.launched_by_manager,
            "launcher_process_id": self.launcher_process_id,
            "launcher_process_started_at_100ns": self.launcher_process_started_at_100ns,
            "launch_provenance": (
                self.launch_provenance.value if self.launch_provenance is not None else None
            ),
            "attached_at": self.attached_at,
            "last_verified_at": self.last_verified_at,
            "window_tile": (
                None
                if self.window_tile is None
                else {
                    "left": self.window_tile[0],
                    "top": self.window_tile[1],
                    "width": self.window_tile[2],
                    "height": self.window_tile[3],
                }
            ),
            "status_detail": self.status_detail,
            "failure_detail": self.failure_detail,
        }


@dataclass(frozen=True, slots=True)
class ManagerSessionSnapshot:
    """Immutable operator-facing status of the complete local manager session."""

    node_id: str
    slots: tuple[ManagerSlotSnapshot, ...]
    schema_version: int = field(default=MANAGER_SESSION_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_canonical_text(self.node_id, "node_id")
        if not isinstance(self.slots, tuple) or any(
            not isinstance(slot, ManagerSlotSnapshot) for slot in self.slots
        ):
            raise ValueError("slots must be an immutable tuple of ManagerSlotSnapshot values")
        client_ids = tuple(slot.client_id.casefold() for slot in self.slots)
        if len(client_ids) != len(set(client_ids)):
            raise ValueError("session slot client IDs must be unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "slots": [slot.to_dict() for slot in self.slots],
        }


class LifecycleSupervisor(Protocol):
    """Narrow injected boundary used by the persistent session."""

    def launch_and_attach(
        self,
        selector: ClientInstanceSelector,
        command: ReviewedLaunchCommand,
        *,
        timeout_seconds: float,
        poll_seconds: float = 0.5,
    ) -> ManagedClientSnapshot: ...

    def attach(
        self,
        selector: ClientInstanceSelector,
        *,
        instance_id: str | None = None,
    ) -> ManagedClientSnapshot: ...

    def refresh(self, instance_id: str) -> ManagedClientSnapshot: ...

    def status(self, instance_id: str) -> ManagedClientSnapshot: ...

    def pause(self, instance_id: str) -> ManagedClientSnapshot: ...

    def resume(self, instance_id: str) -> ManagedClientSnapshot: ...

    def detach(self, instance_id: str) -> ManagedClientSnapshot: ...

    def request_close(self, instance_id: str) -> ManagedClientSnapshot: ...

    def tile(
        self,
        instance_id: str,
        rectangle: WindowRectangle,
    ) -> ManagedClientSnapshot: ...


@dataclass(slots=True)
class _SessionSlot:
    config: ManagedClientConfig
    state: ManagerSlotState = ManagerSlotState.CONFIGURED
    instance_id: str | None = None
    managed: ManagedClientSnapshot | None = None
    status_detail: str | None = None
    failure_detail: str | None = None
    close_requested: bool = False

    def snapshot(self) -> ManagerSlotSnapshot:
        managed = self.managed
        tile = self.config.window_tile
        dispatch_enabled = bool(
            managed is not None
            and managed.dispatch_enabled
            and self.state is ManagerSlotState.ATTACHED
        )
        return ManagerSlotSnapshot(
            client_id=self.config.client_id,
            state=self.state,
            instance_id=self.instance_id,
            dispatch_enabled=dispatch_enabled,
            launched_by_manager=managed.launched_by_manager if managed is not None else False,
            launcher_process_id=(managed.launcher_process_id if managed is not None else None),
            launcher_process_started_at_100ns=(
                managed.launcher_process_started_at_100ns if managed is not None else None
            ),
            launch_provenance=(managed.launch_provenance if managed is not None else None),
            attached_at=managed.attached_at if managed is not None else None,
            last_verified_at=(managed.last_verified_at if managed is not None else None),
            window_tile=(tile.assignment if tile is not None else None),
            status_detail=self.status_detail,
            failure_detail=self.failure_detail,
        )


class ManagerSession:
    """Own manifest-slot bindings for one PC without owning game strategy or processes."""

    def __init__(self, manifest: ManagerManifest, supervisor: LifecycleSupervisor) -> None:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        required_methods = (
            "launch_and_attach",
            "attach",
            "refresh",
            "status",
            "pause",
            "resume",
            "detach",
            "request_close",
            "tile",
        )
        if any(not callable(getattr(supervisor, method, None)) for method in required_methods):
            raise ValueError("supervisor does not implement the lifecycle session contract")
        self._manifest = manifest
        self._supervisor = supervisor
        self._slots = {config.client_id: _SessionSlot(config=config) for config in manifest.clients}
        self._lock = threading.RLock()
        self._launching: set[str] = set()
        self._slot_locks = {client_id: threading.RLock() for client_id in self._slots}

    @property
    def node_id(self) -> str:
        return self._manifest.node_id

    def status(
        self,
        client_id: str | None = None,
    ) -> ManagerSessionSnapshot | ManagerSlotSnapshot:
        """Return remembered status without touching a process or window."""

        with self._lock:
            if client_id is None:
                return self._snapshot()
            return self._require_slot(client_id).snapshot()

    def snapshot(self) -> ManagerSessionSnapshot:
        with self._lock:
            return self._snapshot()

    def refresh(
        self,
        client_id: str | None = None,
    ) -> ManagerSessionSnapshot | ManagerSlotSnapshot:
        """Revalidate exact bindings; complete a close once its instance disappears."""

        if client_id is not None:
            with self._lock:
                if client_id in self._launching:
                    return self._require_slot(client_id).snapshot()
            with self._slot_operation(client_id) as slot:
                return self._refresh_slot(slot)
        for config in self._manifest.clients:
            self.refresh(config.client_id)
        return self.snapshot()

    def start(
        self,
        client_id: str,
        *,
        timeout_seconds: float = 30.0,
        poll_seconds: float = 0.5,
    ) -> ManagerSlotSnapshot:
        """Launch and bind only the one new immutable instance for a manifest slot."""

        with self._slot_operation(client_id, wait=False) as slot:
            with self._lock:
                self._require_unbound(slot, action="start")
                selector = selector_from_config(self.node_id, slot.config)
                command = launch_command_from_config(slot.config)
                self._launching.add(client_id)
            try:
                managed = self._supervisor.launch_and_attach(
                    selector,
                    command,
                    timeout_seconds=timeout_seconds,
                    poll_seconds=poll_seconds,
                )
                with self._lock:
                    # The reservation excludes attach/start while polling is unlocked.
                    if client_id not in self._launching or slot.instance_id is not None:
                        raise SessionSlotBoundError("launch reservation changed before attachment")
                    self._accept_binding(slot, managed, expected_instance_id=None)
                    return slot.snapshot()
            except Exception as exc:
                with self._lock:
                    self._raise_action_failure(slot, "start", exc)
            finally:
                with self._lock:
                    self._launching.discard(client_id)

    def start_all(
        self,
        *,
        timeout_seconds: float = 30.0,
        poll_seconds: float = 0.5,
    ) -> ManagerSessionSnapshot:
        """Start unbound slots sequentially, stopping immediately on the first failure."""

        for config in self._manifest.clients:
            with self._lock:
                should_start = self._slots[config.client_id].instance_id is None
            if should_start:
                self.start(
                    config.client_id, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds
                )
        return self.snapshot()

    def attach(self, client_id: str, *, instance_id: str) -> ManagerSlotSnapshot:
        """Bind a slot only to the explicitly selected existing instance."""

        with self._slot_operation(client_id) as slot:
            self._require_unbound(slot, action="attach")
            instance_id = _require_canonical_text(instance_id, "instance_id")
            owner = self._slot_owning_instance(instance_id, excluding=slot)
            if owner is not None:
                self._record_local_failure(
                    slot,
                    "attach",
                    f"instance {instance_id!r} is already bound to {owner.config.client_id!r}",
                )
                raise SessionSlotBoundError(slot.failure_detail)
            try:
                managed = self._supervisor.attach(
                    selector_from_config(self.node_id, slot.config),
                    instance_id=instance_id,
                )
                self._accept_binding(slot, managed, expected_instance_id=instance_id)
            except Exception as exc:
                self._raise_action_failure(slot, "attach", exc)
            return slot.snapshot()

    def tile(self, client_id: str) -> ManagerSlotSnapshot:
        """Apply the slot's configured rectangle without activating its window."""

        with self._slot_operation(client_id) as slot:
            instance_id = self._require_bound(slot, action="tile")
            rectangle = window_rectangle_from_config(slot.config)
            if rectangle is None:
                self._record_local_failure(slot, "tile", "no window_tile is configured")
                raise SessionActionError(slot.failure_detail)
            return self._bound_action(
                slot,
                "tile",
                lambda: self._supervisor.tile(instance_id, rectangle),
            )

    def tile_all(self) -> ManagerSessionSnapshot:
        """Tile bound slots with configured rectangles, stopping on the first failure."""

        for config in self._manifest.clients:
            with self._lock:
                slot = self._slots[config.client_id]
                should_tile = slot.instance_id is not None and slot.config.window_tile is not None
            if should_tile:
                self.tile(config.client_id)
        return self.snapshot()

    def pause(self, client_id: str) -> ManagerSlotSnapshot:
        with self._slot_operation(client_id) as slot:
            instance_id = self._require_bound(slot, action="pause")
            return self._bound_action(
                slot,
                "pause",
                lambda: self._supervisor.pause(instance_id),
            )

    def resume(self, client_id: str) -> ManagerSlotSnapshot:
        with self._slot_operation(client_id) as slot:
            instance_id = self._require_bound(slot, action="resume")
            return self._bound_action(
                slot,
                "resume",
                lambda: self._supervisor.resume(instance_id),
            )

    def detach(self, client_id: str) -> ManagerSlotSnapshot:
        """Forget one exact binding without any close, kill, or suspend request."""

        with self._slot_operation(client_id) as slot:
            instance_id = self._require_bound(slot, action="detach")
            try:
                detached = self._supervisor.detach(instance_id)
                self._require_managed_result(
                    slot,
                    detached,
                    expected_instance_id=instance_id,
                )
            except Exception as exc:
                self._raise_action_failure(slot, "detach", exc)
            self._clear_binding(
                slot,
                state=ManagerSlotState.DETACHED,
                detail="detached by manager without process action",
            )
            return slot.snapshot()

    def request_close(self, client_id: str) -> ManagerSlotSnapshot:
        """Disable dispatch and request graceful window close; never force-kill."""

        with self._slot_operation(client_id) as slot:
            instance_id = self._require_bound(slot, action="close")
            return self._bound_action(
                slot,
                "close",
                lambda: self._supervisor.request_close(instance_id),
            )

    def graceful_close(self, client_id: str) -> ManagerSlotSnapshot:
        return self.request_close(client_id)

    @contextmanager
    def _slot_operation(self, client_id: str, *, wait: bool = True) -> Iterator[_SessionSlot]:
        with self._lock:
            self._require_slot(client_id)
            operation_lock = self._slot_locks[client_id]
        if not operation_lock.acquire(blocking=wait):
            raise SessionSlotBoundError("slot already has a lifecycle action in progress")
        try:
            with self._lock:
                if client_id in self._launching:
                    raise SessionSlotBoundError("slot already has a launch in progress")
                original = self._require_slot(client_id)
                working = replace(original)
            try:
                yield working
            finally:
                # Blocking supervisor work mutates only a private slot copy.
                # Publish the complete transition after verifying ownership.
                with self._lock:
                    if self._slots[client_id] is not original:
                        raise SessionSlotBoundError(
                            "slot ownership changed during lifecycle action"
                        )
                    if working.instance_id is not None:
                        owner = self._slot_owning_instance(working.instance_id, excluding=original)
                        if owner is not None:
                            raise SessionSlotBoundError("lifecycle result is owned by another slot")
                    self._slots[client_id] = working
        finally:
            operation_lock.release()

    def _refresh_slot(self, slot: _SessionSlot) -> ManagerSlotSnapshot:
        instance_id = slot.instance_id
        if instance_id is None:
            return slot.snapshot()
        close_was_requested = slot.close_requested
        try:
            managed = self._supervisor.refresh(instance_id)
            self._require_managed_result(
                slot,
                managed,
                expected_instance_id=instance_id,
            )
            if managed.state is ManagedClientState.EXITED:
                detached = self._supervisor.detach(instance_id)
                self._require_managed_result(
                    slot,
                    detached,
                    expected_instance_id=instance_id,
                )
                self._clear_binding(
                    slot,
                    state=ManagerSlotState.CLOSED,
                    detail=(
                        "graceful close completed; exact process exit was verified"
                        if close_was_requested
                        else "exact process exit was verified; client binding was archived"
                    ),
                )
            else:
                self._apply_managed(slot, managed)
        except Exception as exc:
            self._raise_action_failure(slot, "refresh", exc)
        return slot.snapshot()

    def _bound_action(
        self,
        slot: _SessionSlot,
        action: str,
        operation: Callable[[], ManagedClientSnapshot],
    ) -> ManagerSlotSnapshot:
        instance_id = slot.instance_id
        assert instance_id is not None
        try:
            managed = operation()
            self._require_managed_result(
                slot,
                managed,
                expected_instance_id=instance_id,
            )
            self._apply_managed(slot, managed)
        except Exception as exc:
            self._raise_action_failure(slot, action, exc)
        return slot.snapshot()

    def _accept_binding(
        self,
        slot: _SessionSlot,
        managed: object,
        *,
        expected_instance_id: str | None,
    ) -> None:
        self._require_managed_result(
            slot,
            managed,
            expected_instance_id=expected_instance_id,
        )
        assert isinstance(managed, ManagedClientSnapshot)
        if managed.state is not ManagedClientState.ATTACHED:
            raise SupervisorSessionContractError(
                "a new session binding must begin in the attached lifecycle state"
            )
        owner = self._slot_owning_instance(managed.instance_id, excluding=slot)
        if owner is not None:
            raise SupervisorSessionContractError(
                f"supervisor returned instance {managed.instance_id!r} already bound to "
                f"{owner.config.client_id!r}"
            )
        if slot.instance_id is not None and slot.instance_id != managed.instance_id:
            raise SupervisorSessionContractError(
                f"slot {slot.config.client_id!r} cannot silently rebind from "
                f"{slot.instance_id!r} to {managed.instance_id!r}"
            )
        slot.instance_id = managed.instance_id
        self._apply_managed(slot, managed)

    def _require_managed_result(
        self,
        slot: _SessionSlot,
        managed: object,
        *,
        expected_instance_id: str | None,
    ) -> ManagedClientSnapshot:
        if not isinstance(managed, ManagedClientSnapshot):
            raise SupervisorSessionContractError(
                "lifecycle supervisor must return ManagedClientSnapshot"
            )
        if expected_instance_id is not None and managed.instance_id != expected_instance_id:
            raise SupervisorSessionContractError(
                f"supervisor returned {managed.instance_id!r} for exact instance "
                f"{expected_instance_id!r}"
            )
        expected_selector = selector_from_config(self.node_id, slot.config)
        if managed.selector != expected_selector:
            raise SupervisorSessionContractError(
                f"supervisor returned a binding outside slot {slot.config.client_id!r}'s selector"
            )
        return managed

    def _apply_managed(self, slot: _SessionSlot, managed: ManagedClientSnapshot) -> None:
        slot.managed = managed
        slot.state = _slot_state_from_managed(managed.state)
        if managed.state is ManagedClientState.CLOSE_REQUESTED:
            slot.close_requested = True
        slot.status_detail = managed.status_detail
        slot.failure_detail = None

    def _clear_binding(
        self,
        slot: _SessionSlot,
        *,
        state: ManagerSlotState,
        detail: str,
    ) -> None:
        slot.instance_id = None
        slot.managed = None
        slot.close_requested = False
        slot.state = state
        slot.status_detail = detail
        slot.failure_detail = None

    def _raise_action_failure(
        self,
        slot: _SessionSlot,
        action: str,
        error: Exception,
    ) -> None:
        self._record_failure(slot, action, error)
        raise SessionActionError(slot.failure_detail) from error

    def _record_failure(self, slot: _SessionSlot, action: str, error: Exception) -> None:
        description = str(error).strip() or error.__class__.__name__
        slot.failure_detail = f"{action} failed: {error.__class__.__name__}: {description}"
        instance_id = slot.instance_id
        if instance_id is None:
            return
        try:
            managed = self._supervisor.status(instance_id)
            self._require_managed_result(
                slot,
                managed,
                expected_instance_id=instance_id,
            )
            slot.managed = managed
            slot.state = _slot_state_from_managed(managed.state)
            if managed.state is ManagedClientState.CLOSE_REQUESTED:
                slot.close_requested = True
            slot.status_detail = managed.status_detail
        except Exception as reconciliation_error:
            slot.state = ManagerSlotState.STALE
            slot.status_detail = (
                "session could not reconcile the exact binding after failure: "
                f"{reconciliation_error}"
            )

    @staticmethod
    def _record_local_failure(slot: _SessionSlot, action: str, detail: str) -> None:
        slot.failure_detail = f"{action} failed: {detail}"

    def _require_unbound(self, slot: _SessionSlot, *, action: str) -> None:
        if slot.config.client_id in self._launching:
            raise SessionSlotBoundError("slot already has a launch in progress")
        if slot.instance_id is not None:
            self._record_local_failure(
                slot,
                action,
                f"slot is already bound to exact instance {slot.instance_id!r}; detach first",
            )
            raise SessionSlotBoundError(slot.failure_detail)

    def _require_bound(self, slot: _SessionSlot, *, action: str) -> str:
        if slot.instance_id is None:
            self._record_local_failure(slot, action, "slot is not bound to an instance")
            raise SessionSlotUnboundError(slot.failure_detail)
        return slot.instance_id

    def _slot_owning_instance(
        self,
        instance_id: str,
        *,
        excluding: _SessionSlot,
    ) -> _SessionSlot | None:
        return next(
            (
                slot
                for slot in self._slots.values()
                if slot is not excluding and slot.instance_id == instance_id
            ),
            None,
        )

    def _require_slot(self, client_id: str) -> _SessionSlot:
        client_id = _require_canonical_text(client_id, "client_id")
        try:
            return self._slots[client_id]
        except KeyError as exc:
            raise UnknownSessionClientError(
                f"client_id {client_id!r} is not present in the local manifest"
            ) from exc

    def _snapshot(self) -> ManagerSessionSnapshot:
        return ManagerSessionSnapshot(
            node_id=self.node_id,
            slots=tuple(
                self._slots[config.client_id].snapshot() for config in self._manifest.clients
            ),
        )


def _slot_state_from_managed(state: ManagedClientState) -> ManagerSlotState:
    try:
        return ManagerSlotState(state.value)
    except (AttributeError, ValueError) as exc:
        raise SupervisorSessionContractError(
            f"unsupported managed lifecycle state: {state!r}"
        ) from exc


__all__ = [
    "MANAGER_SESSION_SCHEMA_VERSION",
    "LifecycleSupervisor",
    "ManagerSession",
    "ManagerSessionError",
    "ManagerSessionSnapshot",
    "ManagerSlotSnapshot",
    "ManagerSlotState",
    "SessionActionError",
    "SessionSlotBoundError",
    "SessionSlotUnboundError",
    "SupervisorSessionContractError",
    "UnknownSessionClientError",
]
