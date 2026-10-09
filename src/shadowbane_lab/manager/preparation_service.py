"""One worker-owned preparation thread, serialized with finite operations.

Only this thread touches its native resources. Supervision changes intent and
reads cached state; it never waits in a native call or invents cleanup evidence.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from shadowbane_lab.pve.preparation_status import PreparationStatus


@dataclass(frozen=True, slots=True)
class PreparationServiceSnapshot:
    state: str
    control_revision: int
    preparation: PreparationStatus
    detail: str | None = None


class PersistentPreparationService:
    def __init__(self, *, owner_factory, intent, interval=0.1):
        self._factory = owner_factory
        self._intent = intent
        self._interval = interval
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = False
        self._supervision_allowed = True
        self._handoff = False
        self._blocked = False
        self._inflight = False
        self._owner = None
        self._closing = False
        self._fault_detail = None
        self._thread = None
        self._intent_problem = None
        self._snapshot = PreparationServiceSnapshot(
            "starting", 0, PreparationStatus.disabled())

    @property
    def snapshot(self):
        with self._lock:
            return self._snapshot

    def start(self):
        with self._lock:
            if self._thread is not None:
                raise RuntimeError("preparation service was already started")
            self._thread = threading.Thread(target=self._run,
                name="shadowbane-preparation", daemon=True)
            self._thread.start()

    def _read_intent(self):
        try:
            enabled, revision = self._intent()
            if type(enabled) is not bool or type(revision) is not int or revision < 0:
                raise ValueError("invalid preparation intent")
        except Exception as exc:
            with self._lock:
                self._intent_problem = f"Preparation controls unavailable: {type(exc).__name__}"
                return False, self._snapshot.control_revision
        with self._lock:
            self._intent_problem = None
        return enabled, revision

    def admission_allowed(self):
        """Fresh worker intent immediately before a new native proposal/entry."""
        enabled, _ = self._read_intent()
        with self._lock:
            return bool(enabled and not (self._handoff or self._stopping
                                         or self._blocked or self._closing
                                         or self._fault_detail is not None)
                        and self._supervision_allowed)

    def supervise(self, *, allowed):
        """Immediate host authority change; never a native call or explicit Resume."""
        if type(allowed) is not bool:
            raise ValueError("worker supervision must be boolean")
        with self._lock:
            self._supervision_allowed = allowed
        self._wake.set()

    def request_handoff(self):
        """Freeze fresh proposals now; return true only after native closure."""
        with self._lock:
            self._handoff = True
            ready = not self._blocked and self._owner is None and not self._inflight
        self._wake.set()
        return ready

    def release_handoff(self, *, cleanup_confirmed):
        if type(cleanup_confirmed) is not bool:
            raise ValueError("handoff requires typed cleanup proof")
        with self._lock:
            if not self._handoff:
                raise RuntimeError("no finite-operation handoff is reserved")
            if self._owner is not None or self._inflight:
                raise RuntimeError("preparation owner has not handed off")
            if not cleanup_confirmed:
                self._blocked = True
                self._snapshot = PreparationServiceSnapshot(
                    "needs_attention", self._snapshot.control_revision,
                    self._snapshot.preparation,
                    "The previous operation has not confirmed native cleanup.")
            else:
                self._handoff = False
        self._wake.set()

    def request_stop(self):
        with self._lock:
            self._stopping = True
        self._wake.set()

    @property
    def stopped(self):
        with self._lock:
            return self._thread is not None and not self._thread.is_alive()

    def _publish(self, state, revision, detail=None):
        with self._lock:
            if self._intent_problem is not None:
                state, detail = "needs_attention", self._intent_problem
            if self._fault_detail is not None:
                detail = self._fault_detail + ("; " + detail if detail else "")
            self._snapshot = PreparationServiceSnapshot(
                state, revision,
                PreparationStatus.disabled() if self._owner is None
                else self._owner.preparation_status,
                None if detail is None else str(detail)[:512])

    def _cycle(self):
        # Intent contains only explicit saved/control state and dispatch authority.
        # Temporary native manual/UI admission is handled by the coordinator.
        enabled, revision = self._read_intent()
        with self._lock:
            stopping, handoff, blocked = self._stopping, self._handoff, self._blocked
            if blocked:
                # No service-owned resource exists after a failed finite handback.
                # Exiting this thread does not credit that finite cleanup.
                return stopping and self._owner is None and not self._inflight
            allow_new = (enabled and self._supervision_allowed and not stopping
                         and not handoff and self._fault_detail is None)
            self._inflight = True
        try:
            if self._owner is None and allow_new:
                owner = self._factory()
                with self._lock:
                    self._owner = owner
                self._closing = False
            owner = self._owner
            if owner is None:
                with self._lock:
                    if not enabled or self._stopping:
                        state, detail = "paused", None
                    elif self._handoff:
                        state = "yielding"
                        detail = "Waiting for the finite operation to return ownership."
                    elif not self._supervision_allowed:
                        state, detail = "paused", "Worker dispatch is not currently allowed."
                    else:
                        # Saved buff settings disabled the factory.
                        state, detail = "disabled", None
                self._publish(state, revision, detail)
                return stopping
            renewal_failed = False
            try:
                owner.maintain()
            except Exception:
                renewal_failed = True
            # Recheck after factory/maintenance: a concurrent handoff freezes the
            # first proposal too, not just proposals on later loop iterations.
            enabled, revision = self._read_intent()
            with self._lock:
                allow_new = (enabled and self._supervision_allowed
                             and not self._stopping and not self._handoff
                             and self._fault_detail is None)
            settings_changed = False
            if not self._closing:
                try:
                    settings_changed = owner.settings_changed()
                except Exception:
                    # Unreadable settings forbid entry, not exact owner cleanup.
                    settings_changed = True
            if self._closing or renewal_failed or not allow_new or settings_changed:
                if not self._closing:
                    try:
                        owner.step(allow_new=False)
                    except Exception:
                        pass  # Passive owner stop retains exact unresolved native work.
                    self._closing = True
                    reason = ("preparation_fault" if self._fault_detail is not None
                              else "preparation_handoff")
                    confirmed, _, detail = owner.finish(reason)
                else:
                    confirmed, _, detail = owner.inspect_owner_closure()
                if not confirmed:
                    self._publish("needs_attention", revision, detail)
                    return False
                owner.close()
                with self._lock:
                    self._owner = None
                    self._closing = False
                detail = "Native preparation cleanup confirmed." if self._fault_detail else None
                self._publish("paused" if not enabled else "idle", revision, detail)
                with self._lock:
                    self._fault_detail = None
                return stopping
            owner.step(allow_new=True)
            self._publish("maintaining", revision)
            return False
        finally:
            with self._lock:
                self._inflight = False

    def _run(self):
        while True:
            try:
                if self._cycle():
                    return
            except Exception as exc:
                # Retain the owner and its original cleanup deadline. A failed
                # observation must not create a replacement producer or coordinator.
                with self._lock:
                    detail = f"{type(exc).__name__}: {exc}"
                    if self._owner is not None and self._fault_detail is None:
                        self._fault_detail = detail
                    # Internal recovery is not a finite-operation reservation.
                    # Copy cached presentation so a failing owner status getter
                    # cannot prevent the next cycle from closing that owner.
                    self._snapshot = PreparationServiceSnapshot(
                        "needs_attention", self._snapshot.control_revision,
                        self._snapshot.preparation,
                        (self._fault_detail or detail)[:512])
            self._wake.wait(self._interval)
            self._wake.clear()
