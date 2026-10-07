"""Immutable client ownership across the chat listener's asynchronous queue."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

from shadowbane_lab.client_extension.client_guard import NativeClientTarget
from shadowbane_lab.client_input import WindowGuardError, WindowSnapshot
from shadowbane_lab.travel.chat import PhysicalPointerInteraction


@dataclass(frozen=True, slots=True)
class ListenerClientIdentity:
    process_id: int
    process_started_at_100ns: int
    window_handle: int

    @classmethod
    def capture(cls, snapshot: WindowSnapshot) -> ListenerClientIdentity:
        values = (snapshot.process_id, snapshot.process_started_at_100ns, snapshot.window_handle)
        if any(value is None for value in values):
            raise WindowGuardError(
                "listener requires exact process, creation time and window identity"
            )
        return cls(*values)

    def require_current(self, guard: NativeClientTarget) -> None:
        if self.capture(guard.require_target()) != self:
            raise WindowGuardError(
                "queued interaction belongs to a different client lifetime or window"
            )


@dataclass(frozen=True, slots=True)
class ListenerInteraction:
    client: ListenerClientIdentity
    # None is an internal cancellation request, never a client movement-stop command.
    command: str | PhysicalPointerInteraction | None
    observed_at: float


class ListenerCommandIngress:
    """Capture ownership at callback admission and coalesce cancellation per owner."""

    def __init__(self, guard: NativeClientTarget) -> None:
        self._guard = guard
        self._queue: queue.Queue[ListenerInteraction] = queue.Queue()
        self._pending_cancellations: set[ListenerClientIdentity] = set()
        self._lock = threading.Lock()

    def submit(self, command: str | PhysicalPointerInteraction | None) -> None:
        client = ListenerClientIdentity.capture(self._guard.require_target())
        interaction = ListenerInteraction(client, command, time.monotonic())
        with self._lock:
            if command is None:
                if client in self._pending_cancellations:
                    return
                self._pending_cancellations.add(client)
            self._queue.put(interaction)

    def get(self, *, timeout: float) -> ListenerInteraction:
        interaction = self._queue.get(timeout=timeout)
        if interaction.command is None:
            with self._lock:
                self._pending_cancellations.discard(interaction.client)
        return interaction


class ListenerOwnershipStop:
    """Permanently revoke a local operation when its captured client is no longer current."""

    def __init__(self, client: ListenerClientIdentity, guard: NativeClientTarget) -> None:
        self._client = client
        self._guard = guard
        self._revoked = threading.Event()

    def is_set(self) -> bool:
        if not self._revoked.is_set():
            try:
                self._client.require_current(self._guard)
            except (OSError, RuntimeError, ValueError):
                self._revoked.set()
        return self._revoked.is_set()
