"""Authenticated dashboard admission and exact-worker execution for Condemn jobs."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.record_store import exclusive_record_lock, read_record_bytes

from .condemn_cycle import CondemnCycleStopped
from .condemn_job import CondemnJobStore, run_condemn_job
from .condemn_preparation import prepare_condemn
from .guard_job import GuardJobStore
from .guard_owner import read_guard_owner
from .operation import (
    WorkerOperationExecution,
    WorkerOperationKind,
    WorkerOperationState,
    new_worker_operation,
)
from .vendor_job import VendorJobStore, _write

CAPABILITY = "condemn_jobs_v1"


def _read(path):
    return json.loads(read_record_bytes(path, 32 * 1024))


def _other_jobs_idle(store):
    vendor, guard = store.current(), GuardJobStore(store).current()
    if (
        vendor
        and vendor["state"] not in {"complete", "stopped"}
        or guard
        and guard["state"] not in {"stopped", "insufficient", "unavailable", "travel"}
    ):
        raise CondemnCycleStopped("Stop the other job or finish guard Travel before using Condemn.")
    GuardSpendingJournal(store.root).assert_idle()
    CondemnProgressStore(store.root).assert_idle()


class ManagerCondemnControl:
    def __init__(self, root, node_id, permits, operations, *, clock=time.time):
        self.root, self.node_id = Path(root), node_id
        self.permits, self.operations, self.clock = permits, operations, clock

    def store(self, client_id, instance_id):
        return VendorJobStore(self.root, self.node_id, client_id, instance_id)

    def summary(self, client_id, instance_id):
        if not instance_id:
            return None
        store = self.store(client_id, instance_id)
        jobs = CondemnJobStore(store)
        result = dict(prepared=None, job=None)
        try:
            result["prepared"] = jobs.plans.current()
            current = jobs.current()
            if current:
                completed = jobs.progress(current)
                result["job"] = dict(
                    job_id=current["job_id"],
                    state=current["state"],
                    detail=current["detail"],
                    control=jobs.control(current["job_id"]),
                    completed=len(completed),
                    total=len(current["selection"]["targets"]),
                    buildings=len({t[:16] for t in current["selection"]["targets"]}),
                )
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            result["error"] = str(exc) or "Saved Condemn progress needs review."
        return result

    def execute(self, action, client_id, instance_id, *, job_id=None, selection=None):
        if action not in {
            "condemn-prepare",
            "condemn-start",
            "condemn-pause",
            "condemn-resume",
            "condemn-stop",
        }:
            raise ValueError("unknown Condemn action")
        if (action == "condemn-start") != (selection is not None):
            raise ValueError("Condemn start requires an explicit selection")
        if selection is not None and (
            not isinstance(selection, dict)
            or set(selection) != {"preparation_id", "sha256", "crests", "buildings"}
        ):
            raise ValueError("invalid Condemn selection")
        store = self.store(client_id, instance_id)
        jobs = CondemnJobStore(store)
        with exclusive_record_lock(store.root / "admission.lock"):
            current = jobs.current()
            if action in {"condemn-pause", "condemn-resume", "condemn-stop"}:
                if not current or current["job_id"] != job_id:
                    raise CondemnCycleStopped("The Condemn job changed; refresh its controls.")
            elif job_id is not None:
                raise ValueError("this Condemn action does not accept a job ID")
            if action in {"condemn-pause", "condemn-stop"}:
                jobs.request(job_id, action.removeprefix("condemn-"))
                return
            permit, now = self.permits.inspect_permit(client_id), self.clock()
            if (
                permit is None
                or not permit.allowed
                or permit.node_id != self.node_id
                or permit.client_id != client_id
                or permit.instance_id != instance_id
                or not permit.issued_at <= now < permit.expires_at
            ):
                raise CondemnCycleStopped("Resume client dispatch and wait for a healthy worker.")
            expected = dict(
                schema_version=1,
                capability=CAPABILITY,
                worker_id=permit.worker_id,
                process_id=permit.process_id,
                process_started_at_100ns=permit.process_started_at_100ns,
            )
            path = store.root / "condemn-worker-capability.json"
            if not path.exists() or _read(path) != expected:
                raise CondemnCycleStopped("Restart this worker with the Condemn-capable host.")
            target = (
                permit.node_id,
                permit.client_id,
                permit.instance_id,
                permit.worker_id,
                permit.process_id,
                permit.process_started_at_100ns,
            )
            if any(
                s.operation.target_identity() == target
                and (
                    s.receipt is None
                    and s.operation.expires_at > now
                    or s.receipt is not None
                    and not s.receipt.state.terminal
                )
                for s in self.operations.inspect_slot(client_id)
            ):
                raise CondemnCycleStopped("Another operation owns this worker.")
            _other_jobs_idle(store)
            if action == "condemn-resume":
                # Job admission validates any recoverable lease-expiry boundary.
                jobs.request(job_id, "run")
                command = "condemn resume " + job_id
                operation = new_worker_operation(
                    permit, WorkerOperationKind.CONDEMN, command, now=now
                )
            else:
                if current and current["state"] not in {"complete", "stopped"}:
                    raise CondemnCycleStopped("Continue or stop the current Condemn job first.")
                op_id = "operation-" + uuid.uuid4().hex
                command = "condemn prepare"
                if action == "condemn-start":
                    jobs.plans.select(
                        selection["preparation_id"],
                        selection["sha256"],
                        selection["crests"],
                        selection["buildings"],
                    )
                    command = "condemn start " + op_id
                operation = new_worker_operation(
                    permit, WorkerOperationKind.CONDEMN, command, now=now, operation_id=op_id
                )
                if selection is not None:
                    _write(
                        store.root / "condemn-requests" / (op_id + ".json"),
                        dict(
                            schema_version=1,
                            operation_id=op_id,
                            target=list(operation.target_identity()),
                            selection=selection,
                        ),
                    )
            self.operations.submit(operation)


class CondemnWorkerExecutor:
    def __init__(
        self,
        root,
        node_id,
        binding,
        *,
        prepare=prepare_condemn,
        runner=run_condemn_job,
        owner_reader=read_guard_owner,
    ):
        self.root, self.node_id, self.binding = Path(root), node_id, binding
        self.prepare, self.runner, self.owner_reader = prepare, runner, owner_reader
        self.worker = None

    def store(self):
        return VendorJobStore(
            self.root, self.node_id, self.binding.client_id, self.binding.instance_id
        )

    def initialize(self, worker_id, process):
        self.worker = (worker_id, process.process_id, process.process_started_at_100ns)
        _write(
            self.store().root / "condemn-worker-capability.json",
            dict(
                schema_version=1,
                capability=CAPABILITY,
                worker_id=worker_id,
                process_id=process.process_id,
                process_started_at_100ns=process.process_started_at_100ns,
            ),
        )

    def execute(self, operation, *, stop_signal):
        b = self.binding
        if (
            operation.kind is not WorkerOperationKind.CONDEMN
            or operation.node_id != self.node_id
            or operation.client_id != b.client_id
            or operation.instance_id != b.instance_id
            or self.worker
            != (
                operation.worker_id,
                operation.worker_process_id,
                operation.worker_process_started_at_100ns,
            )
            or b.worker_id is not None
            and operation.worker_id != b.worker_id
        ):
            raise CondemnCycleStopped("Condemn operation does not own this exact worker.")
        if stop_signal.is_set():
            return WorkerOperationExecution(
                WorkerOperationState.CANCELLED, "Condemn dispatch paused."
            )
        store = self.store()
        _other_jobs_idle(store)
        jobs = CondemnJobStore(store)
        if operation.command == "condemn prepare":
            current = jobs.current()
            if current and current["state"] not in {"complete", "stopped"}:
                raise CondemnCycleStopped("The existing Condemn job still owns this selection.")
            prepared = self.prepare(store, b, operation, cancelled=stop_signal.is_set)
            return WorkerOperationExecution(
                WorkerOperationState.SUCCEEDED,
                f"Found {len(prepared['catalog']['entries'])} scoped crests and "
                f"{len(prepared['buildings'])} nearby guard buildings. "
                "Choose the selection to apply.",
            )
        if operation.command.startswith("condemn start "):
            if operation.command.removeprefix("condemn start ") != operation.operation_id:
                raise CondemnCycleStopped("Condemn start belongs to another selection request.")
            request = _read(store.root / "condemn-requests" / (operation.operation_id + ".json"))
            if (
                set(request) != {"schema_version", "operation_id", "target", "selection"}
                or request["schema_version"] != 1
                or request["operation_id"] != operation.operation_id
                or request["target"] != list(operation.target_identity())
            ):
                raise CondemnCycleStopped("The saved Condemn selection request changed owner.")
            selected = request["selection"]
            record = jobs.begin(
                b,
                operation,
                selected["preparation_id"],
                selected["sha256"],
                selected["crests"],
                selected["buildings"],
                owner_reader=self.owner_reader,
            )
            job_id = record["job_id"]
        elif operation.command.startswith("condemn resume "):
            job_id = operation.command.removeprefix("condemn resume ")
            current = jobs.current()
            if not current or current["job_id"] != job_id:
                raise CondemnCycleStopped("The selected Condemn job changed.")
        else:
            raise CondemnCycleStopped("Unknown Condemn worker command.")
        record = self.runner(
            store, b, job_id, cancelled=stop_signal.is_set, owner_reader=self.owner_reader
        )
        return WorkerOperationExecution(
            WorkerOperationState.SUCCEEDED
            if record["state"] == "complete"
            else WorkerOperationState.CANCELLED
            if record["state"] in {"paused", "stopped"}
            else WorkerOperationState.FAILED,
            record["detail"],
        )
