"""Guard dashboard admission and execution through the exact client worker ledger."""

from __future__ import annotations

import json
import time
from pathlib import Path

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.client_extension.vendor_navigation_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    Outcome,
    Snapshot,
)
from shadowbane_lab.record_store import exclusive_record_lock, read_record_bytes

from .guard_discovery import run_guard_discovery
from .guard_funding_cycle import GuardFundingCycleStopped, open_guard_cycle_session
from .guard_job import TERMINAL, GuardJobStore, run_guard_upgrade_job
from .guard_owner import read_guard_owner, require_owner
from .guard_plan import build_guard_upgrade_plan
from .operation import (
    WorkerOperationExecution,
    WorkerOperationKind,
    WorkerOperationState,
    new_worker_operation,
)
from .vendor_job import VendorJobStore, _write


def _read(path):
    return json.loads(read_record_bytes(path, 1024 * 1024))


def _prepared(store):
    path = store.root / "guard-prepared.json"
    if not path.exists():
        return None
    record = _read(path)
    if record.get("schema_version") not in {1, 2} or record.get("identity") != list(store.identity):
        raise GuardFundingCycleStopped("The prepared guard selection belongs to another client.")
    return record


class ManagerGuardControl:
    def __init__(self, root, node_id, permits, operations, *, clock=time.time):
        self.root, self.node_id = Path(root), node_id
        self.permits, self.operations, self.clock = permits, operations, clock

    def store(self, client_id, instance_id):
        return VendorJobStore(self.root, self.node_id, client_id, instance_id)

    def summary(self, client_id, instance_id):
        if not instance_id:
            return None
        store = self.store(client_id, instance_id)
        jobs = GuardJobStore(store)
        current, prepared = jobs.current(), _prepared(store)
        summary = {"prepared": None, "job": None}
        if prepared:
            summary["prepared"] = {
                k: prepared[k]
                for k in (
                    "discovery_id",
                    "guards",
                    "buildings",
                    "candidate_buildings",
                )
            }
        if current:
            summary["job"] = {
                k: current[k]
                for k in (
                    "job_id",
                    "state",
                    "detail",
                    "withdrawn",
                    "deposited",
                    "spent",
                    "upgrades_started",
                    "town_coverage_verified",
                    "maximum_rank_verified",
                )
            }
            summary["job"].update(
                control=jobs.control(current["job_id"]),
                guards=len(current["guards"]),
                waiting=sum(g["state"] == "waiting" for g in current["guards"]),
                nearby=len(current.get("area_indices", current["guards"])),
            )
        return summary

    def execute(self, action, client_id, instance_id, *, job_id=None):
        if action not in {
            "guard-discover",
            "guard-start",
            "guard-pause",
            "guard-resume",
            "guard-stop",
            "guard-travel",
            "guard-continue",
        }:
            raise ValueError("unknown guard action")
        store = self.store(client_id, instance_id)
        jobs = GuardJobStore(store)
        with exclusive_record_lock(store.root / "admission.lock"):
            current = jobs.current()
            if action in {
                "guard-pause", "guard-resume", "guard-stop", "guard-travel", "guard-continue",
            }:
                if not current or current["job_id"] != job_id:
                    raise GuardFundingCycleStopped(
                        "The selected guard job changed; refresh its controls."
                    )
            if action in {"guard-pause", "guard-stop", "guard-travel"}:
                jobs.request(job_id, action.removeprefix("guard-"))
                return
            permit, now = self.permits.inspect_permit(client_id), self.clock()
            if (
                permit is None
                or not permit.allowed
                or permit.instance_id != instance_id
                or permit.node_id != self.node_id
                or permit.client_id != client_id
                or not permit.issued_at <= now < permit.expires_at
            ):
                raise GuardFundingCycleStopped(
                    "Resume client dispatch and wait for a healthy worker."
                )
            expected = dict(
                schema_version=1,
                capability="guard_jobs_travel_v4",
                worker_id=permit.worker_id,
                process_id=permit.process_id,
                process_started_at_100ns=permit.process_started_at_100ns,
            )
            path = store.root / "guard-worker-capability.json"
            if not path.exists() or _read(path) != expected:
                raise GuardFundingCycleStopped("Restart this worker with the guard-capable host.")
            target = (
                permit.node_id,
                permit.client_id,
                permit.instance_id,
                permit.worker_id,
                permit.process_id,
                permit.process_started_at_100ns,
            )
            inflight = [
                s
                for s in self.operations.inspect_slot(client_id)
                if s.operation.target_identity() == target
                and (
                    s.receipt is None
                    and s.operation.expires_at > now
                    or s.receipt is not None
                    and not s.receipt.state.terminal
                )
            ]
            if inflight:
                raise GuardFundingCycleStopped("Another operation owns this worker.")
            if action == "guard-continue":
                if current["state"] != "travel" or jobs.control(job_id) != "travel":
                    raise GuardFundingCycleStopped("Wait until Travel says it is safe to move.")
                GuardSpendingJournal(store.root).assert_idle()
                command = "guard continue " + job_id
            elif action == "guard-resume":
                if current["state"] in TERMINAL or jobs.control(job_id) == "travel":
                    raise GuardFundingCycleStopped("This guard job has ended or needs review.")
                jobs.request(job_id, "run")
                command = "guard resume " + job_id
            else:
                vendor = store.current()
                if (
                    current
                    and current["state"] not in {"stopped", "insufficient", "unavailable"}
                    or vendor
                    and vendor["state"] not in {"complete", "stopped", "review"}
                ):
                    raise GuardFundingCycleStopped("Continue or stop the existing job first.")
                GuardSpendingJournal(store.root).assert_idle()
                if action == "guard-discover":
                    command = "guard discover"
                else:
                    prepared = _prepared(store)
                    if (not prepared or prepared.get("schema_version") != 2
                            or prepared.get("funding_source") != "carried"
                            or prepared["discovery_id"] != job_id):
                        raise GuardFundingCycleStopped("Find guards before starting upgrades.")
                    command = "guard start " + prepared["discovery_id"]
            self.operations.submit(
                new_worker_operation(
                    permit,
                    WorkerOperationKind.GUARD,
                    command,
                    now=now,
                )
            )


class GuardWorkerExecutor:
    def __init__(
        self,
        root,
        node_id,
        binding,
        *,
        session_factory=open_guard_cycle_session,
        discover=run_guard_discovery,
        runner=run_guard_upgrade_job,
        owner_reader=read_guard_owner,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        self.root, self.node_id, self.binding = Path(root), node_id, binding
        self.session_factory, self.discover, self.runner = session_factory, discover, runner
        self.clock, self.sleep = clock, sleep
        self.owner_reader = owner_reader

    def store(self):
        return VendorJobStore(
            self.root, self.node_id, self.binding.client_id, self.binding.instance_id
        )

    def initialize(self, worker_id, process):
        _write(
            self.store().root / "guard-worker-capability.json",
            dict(
                schema_version=1,
                capability="guard_jobs_travel_v4",
                worker_id=worker_id,
                process_id=process.process_id,
                process_started_at_100ns=process.process_started_at_100ns,
            ),
        )

    def execute(self, operation, *, stop_signal):
        b = self.binding
        if (
            operation.kind is not WorkerOperationKind.GUARD
            or operation.node_id != self.node_id
            or operation.client_id != b.client_id
            or operation.instance_id != b.instance_id
            or b.worker_id is not None
            and operation.worker_id != b.worker_id
        ):
            raise GuardFundingCycleStopped("Guard operation does not own this exact worker.")
        if stop_signal.is_set():
            return WorkerOperationExecution(
                WorkerOperationState.CANCELLED, "Guard dispatch paused."
            )
        store = self.store()
        journal = GuardSpendingJournal(store.root)
        journal.assert_idle()
        continuing = operation.command.startswith("guard continue ")
        jobs = GuardJobStore(store, owner_reader=self.owner_reader)
        if continuing:
            job_id = operation.command.removeprefix("guard continue ")
            current = jobs.current()
            if (not current or current["job_id"] != job_id or current["state"] != "travel"
                    or jobs.control(job_id) != "travel" or current["active_cycle"]):
                raise GuardFundingCycleStopped("Wait until Travel says it is safe to move.")
        if operation.command == "guard discover" or continuing:
            owner = self.owner_reader(b)
            path = store.root / "guard-preparations" / (operation.operation_id + ".json")
            with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
                if path.exists():
                    raise GuardFundingCycleStopped("This guard preparation was already attempted.")
                _write(path, {"state": "capturing", "operation_id": operation.operation_id})
                session = self.session_factory(b, "navigation", journal=journal)
                try:
                    if (
                        session.identity
                        != NativeClientProcessIdentity(
                            b.game_process_id, b.game_process_started_at_100ns
                        )
                        or session.window != b.game_window_handle
                    ):
                        raise GuardFundingCycleStopped(
                            "The scene observer belongs to another client."
                        )
                    deadline = self.clock() + 60
                    while True:
                        if stop_signal.is_set():
                            raise GuardFundingCycleStopped("Guard discovery cancelled.")
                        session.renew_lease()
                        receipt = session.inspect()
                        if receipt.outcome != Outcome.OBSERVED or receipt.flags & (
                            IN_FLIGHT | UNRESOLVED
                        ):
                            raise GuardFundingCycleStopped(
                                "The current window has an unresolved action."
                            )
                        if receipt.flags & READY:
                            context = receipt.snapshot
                            if context.empty:
                                raise GuardFundingCycleStopped("An in-world scene is required.")
                            break
                        if self.clock() >= deadline:
                            raise GuardFundingCycleStopped("Return to the game to find guards.")
                        self.sleep(0.1)
                finally:
                    session.close()
            # Release the observer producer before City Command/navigation takes ownership.
            options = {}
            if continuing:
                jobs.pin_unspent_owner(b, job_id, context)
                options["remembered"] = jobs.remembered(b, job_id, context)
                with exclusive_record_lock(jobs.root / "control.lock"):
                    current = jobs.read(job_id)
                    if current["state"] != "travel" or jobs.control(job_id) != "travel":
                        raise GuardFundingCycleStopped("Travel changed before the scan.")
                    current.update(state="scanning",
                                   detail="Finding guards here; keep the game in front.")
                    jobs.save(current)
            try:
                self.discover(
                    store, b, operation,
                    cancelled=lambda: stop_signal.is_set() or
                    (continuing and jobs.control(job_id) == "stop"), **options,
                )
                require_owner(owner, self.owner_reader(b))
                if continuing:
                    jobs.continue_here(b, job_id, operation.operation_id, context)
            except Exception as exc:
                if continuing:
                    current = jobs.read(job_id)
                    try:
                        journal.assert_idle()
                    except RuntimeError:
                        current.update(state="review", detail=str(exc))
                    else:
                        if current["state"] != "stopped":
                            current.update(state="travel", detail=
                                           "Area scan stopped. Safe to move, then Continue here.")
                    jobs.save(current)
                raise
            if continuing:
                record = self.runner(store, b, job_id, cancelled=stop_signal.is_set,
                                     owner_reader=self.owner_reader)
                return self._result(record)
            plan = build_guard_upgrade_plan(store, b, operation.operation_id, context)
            prepared = dict(
                schema_version=2,
                funding_source="carried",
                owner=owner,
                identity=list(store.identity),
                discovery_id=operation.operation_id,
                context=context.encode().hex(),
                process_id=b.game_process_id,
                creation=b.game_process_started_at_100ns,
                window=b.game_window_handle,
                guards=len(plan.targets),
                buildings=plan.verified_buildings,
                candidate_buildings=plan.candidate_buildings,
            )
            _write(path, dict(prepared, state="prepared"))
            _write(store.root / "guard-prepared.json", prepared)
            return WorkerOperationExecution(
                WorkerOperationState.SUCCEEDED,
                f"Found {len(plan.targets)} verified guards. Full town coverage is unverified.",
            )
        jobs = GuardJobStore(store, owner_reader=self.owner_reader)
        if operation.command.startswith("guard start "):
            prepared = _prepared(store)
            if (
                not prepared
                or prepared.get("schema_version") != 2
                or prepared.get("funding_source") != "carried"
                or "owner" not in prepared
                or prepared["discovery_id"] != operation.command.removeprefix("guard start ")
                or (prepared["process_id"], prepared["creation"], prepared["window"])
                != (b.game_process_id, b.game_process_started_at_100ns, b.game_window_handle)
            ):
                raise GuardFundingCycleStopped("The prepared guard selection changed.")
            record = jobs.begin(
                b,
                operation,
                prepared["discovery_id"],
                Snapshot.decode(bytes.fromhex(prepared["context"])),
                expected_owner=prepared.get("owner"),
            )
            job_id = record["job_id"]
        elif operation.command.startswith("guard resume "):
            job_id = operation.command.removeprefix("guard resume ")
        else:
            raise GuardFundingCycleStopped("Unknown guard worker command.")
        record = self.runner(store, b, job_id, cancelled=stop_signal.is_set,
                                     owner_reader=self.owner_reader)
        return self._result(record)

    @staticmethod
    def _result(record):
        return WorkerOperationExecution(
            WorkerOperationState.FAILED
            if record["state"] == "review"
            else WorkerOperationState.CANCELLED
            if record["state"] in {"paused", "travel", "stopped"}
            else WorkerOperationState.SUCCEEDED,
            record["detail"],
        )
