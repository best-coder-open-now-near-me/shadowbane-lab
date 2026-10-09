"""Passive exact-worker preparation reporting, separate from operation ownership."""
import threading
import time
from dataclasses import dataclass

from shadowbane_lab.pve.preparation_status import PreparationStatus

from .preparation_service import PreparationServiceSnapshot
from .worker import WorkerHealthState, WorkerHeartbeat, parse_worker_heartbeat


@dataclass(frozen=True, slots=True)
class WorkerPreparationStatus:
    heartbeat: WorkerHeartbeat
    service: PreparationServiceSnapshot

    def to_dict(self):
        value = self.service
        return dict(schema_version=1, heartbeat=self.heartbeat.to_dict(),
                    state=value.state, control_revision=value.control_revision,
                    preparation=value.preparation.to_dict(), detail=value.detail)

    @classmethod
    def parse(cls, value):
        if (not isinstance(value, dict) or set(value) != {
                "schema_version", "heartbeat", "state", "control_revision", "preparation", "detail"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or value["state"] not in {"starting", "paused", "disabled", "idle",
                                          "maintaining", "yielding", "needs_attention"}
                or type(value["control_revision"]) is not int or value["control_revision"] < 0
                or (value["detail"] is not None and (
                    not isinstance(value["detail"], str) or len(value["detail"]) > 512))):
            raise ValueError("invalid worker preparation status")
        return cls(parse_worker_heartbeat(value["heartbeat"]), PreparationServiceSnapshot(
            value["state"], value["control_revision"],
            PreparationStatus.from_dict(value["preparation"]), value["detail"]))


class PreparationStatusPublisher:
    """One replaceable pending value; reporting never blocks supervision/native IPC."""
    def __init__(self, ledger):
        self._ledger = ledger
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._latest = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="preparation-status", daemon=True)
        self._thread.start()

    def publish(self, heartbeat, service):
        with self._lock:
            if self._closed:
                return
            self._latest = WorkerPreparationStatus(heartbeat, service)
        self._wake.set()

    def _run(self):
        while True:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                value, closed = self._latest, self._closed
                self._latest = None
            if value is not None:
                try:
                    self._ledger.publish_preparation_status(value)
                except (OSError, RuntimeError, ValueError):
                    pass  # Failed reporting expires; it never changes native authority.
            if closed:
                return

    def close(self):
        with self._lock:
            self._closed = True
        self._wake.set()
        self._thread.join(timeout=1)


def project_status(record, worker, binding, *, now=None):
    unavailable = dict(state="unavailable", current=False, preparation=None, detail=None)
    if record is None or binding is None or worker.heartbeat is None:
        return unavailable
    now = time.time() if now is None else now
    recorded, current = record.heartbeat, worker.heartbeat
    if (worker.state is not WorkerHealthState.HEALTHY
            or (recorded.node_id, recorded.client_id, recorded.instance_id, recorded.worker_id,
                recorded.process_id, recorded.process_started_at_100ns)
            != (current.node_id, current.client_id, current.instance_id, current.worker_id,
                current.process_id, current.process_started_at_100ns)
            or recorded.instance_id != binding.instance_id
            or recorded.sequence > current.sequence
            or not 0 <= now - recorded.observed_at <= 3):
        return unavailable
    preparation = record.service.preparation
    actor = preparation.actor
    if actor is not None and (actor.process_id, actor.process_creation) != (
            binding.process_id, binding.process_started_at_100ns):
        return unavailable
    fresh = (preparation.captured_at is not None
             and 0 <= now - preparation.captured_at <= 3)
    return dict(state=record.service.state, current=fresh,
                preparation=preparation.to_dict(), detail=record.service.detail,
                control_revision=record.service.control_revision)
