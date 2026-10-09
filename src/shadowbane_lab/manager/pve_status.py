"""Bounded, passive progress projection for the existing exact PvE worker."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from shadowbane_lab.pve.preparation_status import PvEProgress

from .operation import WorkerOperation, WorkerOperationKind, parse_worker_operation
from .worker import WorkerHealthState


@dataclass(frozen=True, slots=True)
class WorkerPvEProgress:
    operation: WorkerOperation
    progress: PvEProgress

    def __post_init__(self):
        if (
            not isinstance(self.operation, WorkerOperation)
            or self.operation.kind is not WorkerOperationKind.PVE
        ):
            raise ValueError("PvE progress requires exact PvE operation")
        if not isinstance(self.progress, PvEProgress):
            raise ValueError("PvE progress must be typed")

    def to_dict(self):
        return dict(
            schema_version=1, operation=self.operation.to_dict(), progress=self.progress.to_dict()
        )

    @classmethod
    def parse(cls, value):
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "operation", "progress"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
        ):
            raise ValueError("invalid worker PvE progress schema")
        return cls(
            parse_worker_operation(value["operation"]), PvEProgress.from_dict(value["progress"])
        )


class PvEProgressPublisher:
    """One coalescing writer with no native access; scheduler never waits for disk.

    There is only one latest bounded value. Operation receipts remain the sole
    terminal authority; late writes after stop/replacement are rejected by ledger.
    """

    def __init__(
        self, ledger, operation, *, process_id, process_creation, clock=time.monotonic, interval=1.0
    ):
        self._ledger, self._operation = ledger, operation
        self._process = (process_id, process_creation)
        self._clock = clock
        self._interval = interval
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._closing = False
        self._latest = None
        self._written = None
        self._thread = threading.Thread(target=self._run, name="pve-status", daemon=True)
        self._thread.start()

    def __call__(self, progress):
        if not isinstance(progress, PvEProgress):
            raise ValueError("progress must be typed")
        actor = progress.preparation.actor
        if actor is not None and (actor.process_id, actor.process_creation) != self._process:
            raise ValueError("progress actor differs from exact worker binding")
        tracking_actor = progress.tracking.actor
        if tracking_actor is not None and (
            tracking_actor.process_id, tracking_actor.process_creation_filetime_utc
        ) != self._process:
            raise ValueError("progress tracking actor differs from exact worker binding")
        with self._lock:
            if self._closing:
                return
            self._latest = WorkerPvEProgress(self._operation, progress)
        self._wake.set()

    def _run(self):
        next_write = float("-inf")
        while True:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                closing = self._closing
            delay = max(0.0, next_write - self._clock())
            if delay and not closing:
                # New captures replace the pending value without shortening the rate limit.
                while delay and not closing:
                    self._wake.wait(delay)
                    self._wake.clear()
                    with self._lock:
                        closing = self._closing
                    delay = max(0.0, next_write - self._clock())
            with self._lock:
                record, closing = self._latest, self._closing
            if record is not None and record != self._written:
                next_write = self._clock() + self._interval
                try:
                    self._ledger.publish_pve_progress(record)
                    self._written = record
                except (OSError, RuntimeError, ValueError):
                    pass  # Dashboard naturally reports stale/unavailable, never fake freshness.
            if closing:
                return

    def close(self):
        with self._lock:
            self._closing = True
        self._wake.set()
        # No native responsibilities belong to this writer. Ledger still rejects a
        # delayed write if operation retirement completes before its bounded I/O.
        self._thread.join(timeout=2.0)


def project_status(record, snapshot, worker, instance_id, *, now=None, max_age=3.0):
    """Never relabel a historical capture as current after stop, replacement or stall."""
    now = time.time() if now is None else now
    if record is None or snapshot is None or record.operation != snapshot.operation:
        return dict(state="unavailable", current=False, progress=None)
    op, receipt = snapshot.operation, snapshot.receipt
    progress = record.progress
    observed = progress.preparation.captured_at
    age = None if observed is None else now - observed
    heartbeat = worker.heartbeat
    worker_matches = (
        worker.state is WorkerHealthState.HEALTHY
        and worker.dispatch_allowed
        and worker.active_worker_count == 1
        and heartbeat is not None
        and (
            heartbeat.node_id,
            heartbeat.client_id,
            heartbeat.instance_id,
            heartbeat.worker_id,
            heartbeat.process_id,
            heartbeat.process_started_at_100ns,
        )
        == op.target_identity()
    )
    if receipt is not None and receipt.state.terminal:
        state = "ended"
    elif instance_id != op.instance_id or not worker_matches:
        state = "worker_unavailable"
    elif not 0 <= now - progress.observed_at <= max_age or (
        age is not None and not 0 <= age <= max_age
    ):
        state = "stale"
    elif not progress.preparation.enabled:
        state = "disabled"
    elif not progress.preparation.complete:
        state = "unknown"
    else:
        state = "current"
    tracking = progress.tracking.at(now).to_dict()
    # Contact freshness is independent of whether any buff group is enabled or known.
    if tracking["enabled"]:
        if receipt is not None and receipt.state.terminal:
            tracking.update(current=False, state="ended")
        elif instance_id != op.instance_id or not worker_matches:
            tracking.update(current=False, state="worker_unavailable")
        elif not 0 <= now - progress.observed_at <= max_age:
            tracking.update(current=False, state="stale")
        elif receipt is None:
            tracking.update(current=False, state="unavailable")
    return dict(
        state=state,
        current=state == "current",
        tracking=tracking,
        operation_id=op.operation_id,
        age_seconds=age,
        progress=progress.to_dict(),
        operation_state=None if receipt is None else receipt.state.value,
    )
