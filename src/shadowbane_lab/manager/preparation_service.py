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
        self._handoff = False
        self._blocked = False
        self._inflight = False
        self._owner = None
        self._closing = False
        self._thread = None
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
            self._snapshot = PreparationServiceSnapshot(
                state, revision,
                PreparationStatus.disabled() if self._owner is None
                else self._owner.preparation_status,
                None if detail is None else str(detail)[:512])

    def _cycle(self):
        # Intent contains only explicit saved/control state and dispatch authority.
        # Temporary native manual/UI admission is handled by the coordinator.
        enabled, revision = self._intent()
        with self._lock:
            stopping, handoff, blocked = self._stopping, self._handoff, self._blocked
            if blocked:
                return False
            allow_new = enabled and not stopping and not handoff
            self._inflight = True
        try:
            if self._owner is None and allow_new:
                owner = self._factory()
                with self._lock:
                    self._owner = owner
                self._closing = False
            owner = self._owner
            if owner is None:
                self._publish("paused" if not enabled else "disabled", revision)
                return stopping
            renewal_failed = False
            try:
                owner.maintain()
            except Exception:
                renewal_failed = True
            # Recheck after factory/maintenance: a concurrent handoff freezes the
            # first proposal too, not just proposals on later loop iterations.
            with self._lock:
                allow_new = enabled and not self._stopping and not self._handoff
            if self._closing or renewal_failed or not allow_new or owner.settings_changed():
                if not self._closing:
                    try:
                        owner.step(allow_new=False)
                    except Exception:
                        pass  # Passive owner stop retains exact unresolved native work.
                    self._closing = True
                    confirmed, _, detail = owner.finish("preparation_handoff")
                else:
                    confirmed, _, detail = owner.inspect_owner_closure()
                if not confirmed:
                    self._publish("needs_attention", revision, detail)
                    return False
                owner.close()
                with self._lock:
                    self._owner = None
                self._closing = False
                self._publish("paused" if not enabled else "idle", revision)
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
                self._publish("needs_attention", self.snapshot.control_revision,
                              f"{type(exc).__name__}: {exc}")
                with self._lock:
                    if self._owner is not None:
                        self._handoff = True
            self._wake.wait(self._interval)
            self._wake.clear()
