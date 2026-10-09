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
    NativeMovementCleanupPending,
    NativeMovementError,
    NativeMovementSession,
)
from shadowbane_lab.client_extension.movement_wire import (
    CLEANUP_PENDING,
    Outcome,
    Receipt,
    Snapshot,
)
from shadowbane_lab.client_input import StopSignal
from shadowbane_lab.client_input.stop import StopCause, observed_stop_cause

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
        self._cleanup_pause_done = False
        self._cleanup_pause_key = str(uuid.uuid5(uuid.UUID(self.request_key), "cleanup-pause"))
        self.dispatcher: NativeMovementTravelDispatcher | None = None
        self.reason: str | None = None
        self._stop_cause: StopCause | None = None
        self._interrupted = threading.Event()
        self._lock = threading.RLock()
        self._closed = False
        self._acquisition_attempted = False
        self._acquisition_refused = False
        self._cleanup_confirmed = False

    @property
    def stop_cause(self) -> StopCause | None:
        with self._lock:
            return self._stop_cause

    def interrupt(self, reason: str, *, cause: StopCause | None = None) -> None:
        with self._lock:
            if not self._interrupted.is_set():
                self.reason = reason
                self._stop_cause = cause or StopCause(reason, "interrupted")
                self._interrupted.set()

    def is_set(self) -> bool:
        if self._interrupted.is_set():
            return True
        if self.parent.is_set():
            if self.dispatcher is not None:
                self.session.cleanup.request_terminal(self.dispatcher.grant)
            cause = observed_stop_cause(self.parent)
            self.interrupt(cause.reason, cause=cause)
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
                    self._acquisition_attempted = True
                    grant = self.session.acquire(
                        expected,
                        self.operation.worker_id,
                        self.operation.operation_id,
                        self.request_key,
                    )
                    self.dispatcher = NativeMovementTravelDispatcher(self.session, grant)
                    return not self.is_set()
                except NativeMovementError as exc:
                    receipt = exc.receipt
                    # Session validates the exact producer/request reply. An
                    # unchanged monotonic grant proves no ownership was minted;
                    # refusal text or STALE alone does not prove that.
                    self._acquisition_refused = bool(
                        isinstance(receipt, Receipt)
                        and receipt.request_key == self.request_key
                        and receipt.window == expected.window
                        and receipt.outcome is exc.outcome
                        and exc.outcome in {Outcome.STALE, Outcome.UNAVAILABLE,
                                            Outcome.INHIBITED, Outcome.INVALID}
                        and receipt.grant == expected.grant
                        and not receipt.flags & CLEANUP_PENDING
                    )
                    raise
                except NativeActionChannelTimeout:
                    if attempt:
                        raise
            return False

    def maintain(self) -> None:
        if not self._lock.acquire(blocking=False):
            return
        try:
            if self._closed or self.dispatcher is None:
                return
            cancelled = self.is_set()
            grant = self.dispatcher.grant
            if cancelled and not self.session.cleanup.maintain(grant):
                return
            try:
                if cancelled:
                    # Worker safety/ownership remains authoritative after the parent
                    # stop; only the original pending cleanup receives renewal.
                    if self.dispatcher.is_set():
                        raise NativeActionChannelError("cleanup owner is no longer current")
                    if not self._cleanup_pause_done:
                        if not self.session.snapshot().flags & CLEANUP_PENDING:
                            try:
                                self.session.pause(grant, self._cleanup_pause_key)
                            except NativeMovementCleanupPending:
                                pass
                            except NativeActionChannelTimeout:
                                if self.session.cleanup.maintain(grant):
                                    self.session.renew(grant)
                                return
                        self._cleanup_pause_done = True
                    if not self.session.cleanup.maintain(grant):
                        return
                self.session.renew(grant)
            except (NativeActionChannelError, OSError, ValueError) as exc:
                self.session.cleanup.abort(grant)
                self.interrupt(f"native movement renewal failed: {type(exc).__name__}")
        finally:
            self._lock.release()

    @property
    def cleanup_confirmed(self) -> bool:
        """Positive exact native release, separate from a terminal host outcome."""
        with self._lock:
            return self._cleanup_confirmed

    def _retired_snapshot(self, grant) -> bool:
        from shadowbane_lab.client_extension.action_channel import _WindowsKernel
        try:
            snapshot = self.session.snapshot()
            now = _WindowsKernel().tick_count()
            return bool(
                isinstance(snapshot, Snapshot)
                and snapshot.process_id == grant.process_identity.process_id
                and snapshot.creation_filetime == grant.process_identity.creation_filetime_utc
                and snapshot.window == grant.window
                and 0 <= now - snapshot.tick <= 500
                and (snapshot.grant.generation > grant.ownership.generation
                     or snapshot.grant.scene > grant.ownership.scene)
                and snapshot.grant != grant.ownership
                and not snapshot.flags & CLEANUP_PENDING
                and not self.session.cleanup.has_pending(grant)
            )
        except (AttributeError, OSError, RuntimeError, ValueError):
            return False

    def finish(self) -> str | None:
        """Stop only our immutable grant, even when the strategy's gate is closed."""
        if self.dispatcher is not None:
            self.session.cleanup.request_terminal(self.dispatcher.grant)
            self.session.cleanup.wait_for_terminal(self.dispatcher.grant)
        with self._lock:
            if self._closed:
                return None
            self._closed = True
            self.interrupt("operation movement closed")
            problem = None
            self._cleanup_confirmed = (not self._acquisition_attempted
                                       or self._acquisition_refused)
            try:
                if self.dispatcher is not None:
                    for attempt in range(2):
                        try:
                            grant = self.dispatcher.grant
                            receipt = self.session.stop(grant, self.stop_key)
                            self._cleanup_confirmed = bool(
                                isinstance(receipt, Receipt)
                                and receipt.request_key == self.stop_key
                                and receipt.host == grant.host and receipt.window == grant.window
                                and receipt.outcome is Outcome.ACCEPTED
                                and not receipt.flags & CLEANUP_PENDING
                                and receipt.grant != grant.ownership
                                and receipt.grant.generation > grant.ownership.generation
                                and not self.session.cleanup.has_pending(grant))
                            break
                        except NativeActionChannelTimeout:
                            if attempt:
                                raise
            except NativeMovementError as exc:
                # A stale owner has already lost authority; never stop its replacement.
                if exc.outcome == Outcome.STALE and self.dispatcher is not None:
                    self._cleanup_confirmed = self._retired_snapshot(self.dispatcher.grant)
                if exc.outcome != Outcome.STALE:
                    problem = f"native stop unresolved ({exc}); request={self.stop_key}"
            except (NativeActionChannelError, OSError, ValueError) as exc:
                problem = f"native stop unresolved ({type(exc).__name__}); request={self.stop_key}"
            finally:
                try:
                    self.session.close()
                except (NativeActionChannelError, OSError, ValueError) as exc:
                    self._cleanup_confirmed = False
                    problem = f"native lease closure unresolved ({type(exc).__name__})"
            return problem
