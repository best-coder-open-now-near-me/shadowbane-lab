"""Standalone live operation: one exact-client grant, bounded renewal and cleanup."""

from __future__ import annotations

import threading
import uuid

from shadowbane_lab.client_input import ForegroundWindowGuard, StopSignal
from shadowbane_lab.protocol import DispatchResult
from shadowbane_lab.travel.model import TravelDecision

from .action_channel import (
    NativeActionChannelError,
    NativeActionChannelTimeout,
    NativeClientProcessIdentity,
)
from .movement_dispatcher import NativeMovementTravelDispatcher
from .movement_session import NativeMovementError, NativeMovementSession
from .movement_wire import Outcome


class NativeMovementOperation:
    """Own a standalone CLI operation; manager workers supply their own dispatcher.

    The maintenance thread only renews the producer lease and enqueues terminal
    stop. All gameplay mutations remain on the native owning client thread.
    A cancelled operation is never rearmed or reacquired.
    """

    def __init__(self, guard: ForegroundWindowGuard, parent: StopSignal):
        self.guard, self.parent = guard, parent
        self._wake = threading.Event()
        self._cancelled = threading.Event()
        self._thread = None
        self._session = None
        self._native = None
        self._entered = False
        self._reason = None
        self._stop_lock = threading.Lock()
        self._stopped = False
        self._cleanup_error = None
        self._operation = str(uuid.uuid4())
        self._stop_key = str(uuid.uuid5(uuid.UUID(self._operation), "terminal-stop"))

    @property
    def interruption_reason(self):
        return self._reason

    @property
    def dispatcher(self):
        return self

    def _interrupt(self, reason):
        if not self._cancelled.is_set():
            self._reason = reason
            self._cancelled.set()

    def _check_window(self):
        window = self.guard.require_target()
        if (
            window.process_id,
            window.process_started_at_100ns,
            window.window_handle,
        ) != self._binding:
            raise ValueError("native movement exact-client window changed")

    def __enter__(self):
        if self._entered:
            raise RuntimeError("native movement operation cannot be restarted")
        self._entered = True
        window = self.guard.require_target()
        self._binding = (window.process_id, window.process_started_at_100ns, window.window_handle)
        identity = NativeClientProcessIdentity(window.process_id, window.process_started_at_100ns)
        self._session = NativeMovementSession(identity, window.window_handle)
        try:
            if self.parent.is_set():
                raise NativeActionChannelError("native movement operation already cancelled")
            expected = self._session.snapshot()
            if not expected.flags & 2 or expected.flags & 8:
                raise NativeActionChannelError("native movement unavailable for this client")
            # A timeout may hide an accepted acquisition. Retry only the same
            # expected generation, host, operation and UUID, never a fresh owner.
            for attempt in range(2):
                try:
                    grant = self._session.acquire(
                        expected, "standalone-cli", self._operation, self._operation
                    )
                    break
                except NativeActionChannelTimeout:
                    if attempt:
                        raise
            self._native = NativeMovementTravelDispatcher(self._session, grant)
            if self.is_set():
                raise NativeActionChannelError(self.interruption_reason)
            self._thread = threading.Thread(
                target=self._maintain, name="native-movement-lease", daemon=True
            )
            self._thread.start()
            return self
        except BaseException:
            self.close()
            raise

    def is_set(self):
        if self._cancelled.is_set():
            return True
        try:
            if self.parent.is_set():
                self._interrupt("parent_operation_cancelled")
            else:
                self._check_window()
                if self._native is None or self._native.is_set():
                    self._interrupt("native_movement_owner_revoked")
        except (RuntimeError, ValueError, OSError) as exc:
            self._interrupt(f"native_movement_guard:{type(exc).__name__}")
        return self._cancelled.is_set()

    def _maintain(self):
        while not self._wake.wait(0.25):
            if self.is_set():
                self._terminal_stop()
                return
            try:
                self._session.renew(self._native.grant)
            except (RuntimeError, ValueError, OSError) as exc:
                self._interrupt(f"native_movement_renew:{type(exc).__name__}")
                self._terminal_stop()
                return

    def _terminal_stop(self):
        with self._stop_lock:
            if self._stopped or self._native is None:
                return
            self._stopped = True
            for attempt in range(2):
                try:
                    self._session.stop(self._native.grant, self._stop_key)
                    return
                except NativeActionChannelTimeout as exc:
                    if not attempt:
                        continue
                    self._cleanup_error = exc
                    self._interrupt("native_movement_stop_timeout")
                except (RuntimeError, ValueError, OSError) as exc:
                    # Immutable grant rejection is expected after manual takeover.
                    # Closing the lease also retires pending commands on failure.
                    if not isinstance(exc, NativeMovementError) or exc.outcome != Outcome.STALE:
                        self._cleanup_error = exc
                    self._interrupt(f"native_movement_stop:{type(exc).__name__}")
                return

    def dispatch(self, decision: TravelDecision):
        if self.is_set():
            return DispatchResult(
                "native_movement", f"travel:{decision.decision_id}:cancelled", False, self._reason
            )
        return self._native.dispatch(decision)

    def stop_movement(self, decision: TravelDecision):
        if self.is_set():
            return DispatchResult(
                "native_movement", f"travel:{decision.decision_id}:cancelled", False, self._reason
            )
        return self._native.stop_movement(decision)

    def close(self):
        self._interrupt("operation_closed")
        self._wake.set()
        if self._thread is not None:
            self._thread.join()  # Native session calls have bounded timeouts.
        try:
            self._terminal_stop()
        finally:
            if self._session is not None:
                self._session.close()

    def __exit__(self, exc_type, *_):
        self.close()
        if exc_type is None and self._cleanup_error is not None:
            raise NativeActionChannelError(
                "native movement terminal stop was not confirmed"
            ) from self._cleanup_error
