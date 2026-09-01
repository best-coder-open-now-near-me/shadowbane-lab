"""Exact-client routing from extension events into durable worker operations."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from shadowbane_lab.client_extension import (
    ExtensionWorldMapDestinationEvent,
    open_windows_extension_event_consumer,
)

from .manifest import ManagerManifest
from .model import ClientInstanceSnapshot, ClientRegistrySnapshot
from .operation import WorkerOperationKind, WorkerTravelDestination
from .operation_ingress import ForegroundWorkerOperationIngress

_FILETIME_UNIX_EPOCH = 116_444_736_000_000_000
_FILETIME_TICKS_PER_SECOND = 10_000_000
_MAXIMUM_EVENT_AGE_SECONDS = 8.0
_MAXIMUM_FUTURE_SKEW_SECONDS = 1.0


class ExtensionEventRouterError(RuntimeError):
    """Raised when exact extension event ownership cannot be preserved."""


class ClientRegistryProvider(Protocol):
    def inspect(self) -> ClientRegistrySnapshot: ...


class ExactWorkerIngress(Protocol):
    def cancel_if_inflight(
        self,
        command: str,
        *,
        expected_process_id: int | None = None,
        expected_window_handle: int | None = None,
        require_foreground: bool = True,
        operation_id: str | None = None,
    ) -> object | None: ...

    def dispatch(
        self,
        kind: WorkerOperationKind,
        command: str,
        *,
        destination: WorkerTravelDestination | None = None,
        expected_process_id: int | None = None,
        expected_window_handle: int | None = None,
        require_foreground: bool = True,
        operation_id: str | None = None,
        deduplication_id: str | None = None,
    ) -> object: ...


class ExtensionEventConsumerSource(Protocol):
    @property
    def process_identity(self) -> tuple[int, int]: ...

    def pending(self) -> tuple[ExtensionWorldMapDestinationEvent, ...]: ...

    def acknowledge(self, event: ExtensionWorldMapDestinationEvent) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ExtensionEventRouterPoll:
    """Compact local diagnostics for one non-blocking router pass."""

    connected_clients: int
    dispatched_events: int
    rejected_events: int
    pending_events: int
    dispatched_process_ids: tuple[int, ...]
    issues: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.connected_clients, "connected_clients"),
            (self.dispatched_events, "dispatched_events"),
            (self.rejected_events, "rejected_events"),
            (self.pending_events, "pending_events"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.issues, tuple) or any(
            not isinstance(issue, str) or not issue for issue in self.issues
        ):
            raise ValueError("issues must contain non-empty strings")
        if (
            not isinstance(self.dispatched_process_ids, tuple)
            or any(
                isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0
                for process_id in self.dispatched_process_ids
            )
            or len(self.dispatched_process_ids) != self.dispatched_events
        ):
            raise ValueError("dispatched_process_ids must identify every dispatched event")


class ExactExtensionEventRouter:
    """Consume only current client lifetimes and submit deterministic operations."""

    def __init__(
        self,
        manifest: ManagerManifest,
        registry: ClientRegistryProvider,
        ingress: ExactWorkerIngress,
        *,
        consumer_factory: Callable[[int, int], ExtensionEventConsumerSource] = (
            open_windows_extension_event_consumer
        ),
        event_preparer: (
            Callable[[ClientInstanceSnapshot, ExtensionWorldMapDestinationEvent], None] | None
        ) = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        if not callable(getattr(registry, "inspect", None)):
            raise ValueError("registry must provide inspect()")
        if not isinstance(ingress, ForegroundWorkerOperationIngress) and (
            not callable(getattr(ingress, "dispatch", None))
            or not callable(getattr(ingress, "cancel_if_inflight", None))
        ):
            raise ValueError("ingress must provide dispatch() and cancel_if_inflight()")
        if not callable(consumer_factory) or not callable(clock):
            raise ValueError("consumer_factory and clock must be callable")
        if event_preparer is not None and not callable(event_preparer):
            raise ValueError("event_preparer must be callable or None")
        self._manifest = manifest
        self._registry = registry
        self._ingress = ingress
        self._consumer_factory = consumer_factory
        self._event_preparer = event_preparer
        self._clock = clock
        self._consumers: dict[tuple[int, int], ExtensionEventConsumerSource] = {}
        self._closed = False

    def poll_once(self) -> ExtensionEventRouterPoll:
        if self._closed:
            raise ExtensionEventRouterError("extension event router is closed")
        snapshot = self._registry.inspect()
        if not isinstance(snapshot, ClientRegistrySnapshot):
            raise ExtensionEventRouterError("client registry returned an invalid snapshot")
        if snapshot.node_id != self._manifest.node_id:
            raise ExtensionEventRouterError("client registry returned the wrong node")
        clients = {
            (client.process_id, client.process_started_at_100ns): client
            for client in snapshot.clients
            if client.is_visible
        }
        for identity in tuple(self._consumers):
            if identity not in clients:
                self._consumers.pop(identity).close()

        issues: list[str] = []
        dispatched = 0
        dispatched_process_ids: list[int] = []
        rejected = 0
        pending = 0
        for identity, client in clients.items():
            consumer = self._consumers.get(identity)
            if consumer is None:
                try:
                    consumer = self._consumer_factory(*identity)
                except (OSError, RuntimeError, ValueError) as exc:
                    issues.append(
                        f"{client.instance_id}: channel unavailable ({type(exc).__name__})"
                    )
                    continue
                if consumer.process_identity != identity:
                    consumer.close()
                    issues.append(f"{client.instance_id}: channel identity mismatch")
                    continue
                self._consumers[identity] = consumer
            try:
                events = consumer.pending()
            except (OSError, RuntimeError, ValueError) as exc:
                consumer.close()
                self._consumers.pop(identity, None)
                issues.append(f"{client.instance_id}: channel read failed ({type(exc).__name__})")
                continue
            pending += len(events)
            for event in events:
                outcome = self._route_event(client, event)
                if outcome == "retry":
                    issues.append(
                        f"{client.instance_id}: event preparation or worker dispatch unavailable"
                    )
                    break
                try:
                    consumer.acknowledge(event)
                except (OSError, RuntimeError, ValueError) as exc:
                    issues.append(
                        f"{client.instance_id}: acknowledgement failed ({type(exc).__name__})"
                    )
                    break
                if outcome == "dispatched":
                    dispatched += 1
                    dispatched_process_ids.append(client.process_id)
                else:
                    rejected += 1
        return ExtensionEventRouterPoll(
            connected_clients=len(self._consumers),
            dispatched_events=dispatched,
            rejected_events=rejected,
            pending_events=pending,
            dispatched_process_ids=tuple(dispatched_process_ids),
            issues=tuple(issues[:16]),
        )

    def close(self) -> None:
        if not self._closed:
            for consumer in self._consumers.values():
                consumer.close()
            self._consumers.clear()
            self._closed = True

    def __enter__(self) -> ExactExtensionEventRouter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _route_event(
        self,
        client: ClientInstanceSnapshot,
        event: ExtensionWorldMapDestinationEvent,
    ) -> str:
        if (
            event.process_identity
            != (
                client.process_id,
                client.process_started_at_100ns,
            )
            or event.window_handle != client.window_handle
        ):
            return "rejected"
        captured_at = (
            event.captured_at_filetime_utc - _FILETIME_UNIX_EPOCH
        ) / _FILETIME_TICKS_PER_SECOND
        age = self._clock() - captured_at
        if age > _MAXIMUM_EVENT_AGE_SECONDS or age < -_MAXIMUM_FUTURE_SKEW_SECONDS:
            return "rejected"
        destination = WorkerTravelDestination(event.lt, event.lg)
        common = {
            "expected_process_id": event.process_id,
            "expected_window_handle": event.window_handle,
            "require_foreground": False,
        }
        try:
            if self._event_preparer is not None:
                self._event_preparer(client, event)
            self._ingress.cancel_if_inflight(
                f"extension-map-cancel:{event.sequence}",
                operation_id=_operation_id(event, "cancel"),
                **common,
            )
            self._ingress.dispatch(
                WorkerOperationKind.TRAVEL,
                f"extension-map-{event.button.value}:{event.sequence}",
                destination=destination,
                operation_id=_operation_id(event, "travel"),
                **common,
            )
        except (OSError, RuntimeError, ValueError):
            return "retry"
        return "dispatched"


def _operation_id(event: ExtensionWorldMapDestinationEvent, operation: str) -> str:
    source = (
        f"{event.process_id}:{event.process_creation_filetime_utc}:{event.sequence}:{operation}"
    ).encode("ascii")
    return f"operation-{hashlib.sha256(source).hexdigest()[:32]}"


__all__ = [
    "ExactExtensionEventRouter",
    "ExtensionEventConsumerSource",
    "ExtensionEventRouterError",
    "ExtensionEventRouterPoll",
]
