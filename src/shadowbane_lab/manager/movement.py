"""One exact native movement grant for one worker operation."""

from __future__ import annotations

import threading
import uuid

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeActionChannelTimeout,
)
from shadowbane_lab.client_extension.movement_dispatcher import NativeMovementTravelDispatcher
from shadowbane_lab.client_extension.movement_session import (
    NativeMovementError,
    NativeMovementSession,
)
from shadowbane_lab.client_extension.movement_wire import Outcome
from shadowbane_lab.client_input import StopSignal

from .operation import WorkerOperation


class OperationMovement:
    """Own acquisition, maintenance and terminal cleanup; never reacquire after revocation.

    The worker reserves this object before any IPC. The maintenance thread never
    waits for acquisition/cleanup, and no lock is shared with another client.
    Closing the producer lease also retires an ambiguously acknowledged command;
    its UUID is retained in the operation receipt for diagnosis.
    """

    def __init__(
        self, operation: WorkerOperation, session: NativeMovementSession, stop_signal: StopSignal
    ):
        self.operation = operation
        self.session = session
        self.parent = stop_signal
        self.request_key = str(uuid.uuid4())
        self.stop_key = str(uuid.uuid5(uuid.UUID(self.request_key), "terminal-stop"))
        self.dispatcher: NativeMovementTravelDispatcher | None = None
        self.reason: str | None = None
        self._interrupted = threading.Event()
        self._lock = threading.RLock()
        self._closed = False

    def interrupt(self, reason: str) -> None:
        with self._lock:
            if not self._interrupted.is_set():
                self.reason = reason
                self._interrupted.set()

    def is_set(self) -> bool:
        if self._interrupted.is_set():
            return True
        if self.parent.is_set():
            self.interrupt("worker dispatch permission revoked")
        dispatcher = self.dispatcher
        try:
            if dispatcher is not None and dispatcher.is_set():
                self.interrupt(dispatcher.interruption_reason or "native movement revoked")
        except (NativeActionChannelError, OSError, ValueError) as exc:
            self.interrupt(f"native movement status failed: {type(exc).__name__}")
        return self._interrupted.is_set()

    def acquire(self) -> bool:
        with self._lock:
            if self._closed or self.is_set():
                return False
            expected = self.session.snapshot()
            # Retry only the exact ambiguous request against the original snapshot.
            for attempt in range(2):
                if self.is_set():
                    return False
                try:
                    grant = self.session.acquire(
                        expected,
                        self.operation.worker_id,
                        self.operation.operation_id,
                        self.request_key,
                    )
                    self.dispatcher = NativeMovementTravelDispatcher(self.session, grant)
                    return not self.is_set()
                except NativeActionChannelTimeout:
                    if attempt:
                        raise
            return False

    def maintain(self) -> None:
        if not self._lock.acquire(blocking=False):
            return
        try:
            if self._closed or self.dispatcher is None or self.is_set():
                return
            try:
                self.session.renew(self.dispatcher.grant)
            except (NativeActionChannelError, OSError, ValueError) as exc:
                self.interrupt(f"native movement renewal failed: {type(exc).__name__}")
        finally:
            self._lock.release()

    def finish(self) -> str | None:
        """Stop only our immutable grant, even when the strategy's gate is closed."""
        with self._lock:
            if self._closed:
                return None
            self._closed = True
            self.interrupt("operation movement closed")
            problem = None
            try:
                if self.dispatcher is not None:
                    for attempt in range(2):
                        try:
                            self.session.stop(self.dispatcher.grant, self.stop_key)
                            break
                        except NativeActionChannelTimeout:
                            if attempt:
                                raise
            except NativeMovementError as exc:
                # A stale owner has already lost authority; never stop its replacement.
                if exc.outcome != Outcome.STALE:
                    problem = f"native stop unresolved ({exc}); request={self.stop_key}"
            except (NativeActionChannelError, OSError, ValueError) as exc:
                problem = f"native stop unresolved ({type(exc).__name__}); request={self.stop_key}"
            finally:
                try:
                    self.session.close()
                except (NativeActionChannelError, OSError, ValueError) as exc:
                    problem = f"native lease closure unresolved ({type(exc).__name__})"
            return problem
