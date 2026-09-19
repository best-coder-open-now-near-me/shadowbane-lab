"""Persistent, fair guard scheduling over the exact funding transaction boundary."""
from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import asdict
from types import SimpleNamespace

from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.client_extension.vendor_navigation_wire import Snapshot
from shadowbane_lab.record_store import exclusive_record_lock, read_record_bytes

from .guard_funding_cycle import (
    GuardFundingCycleStopped,
    run_guard_funding_cycle,
)
from .guard_plan import build_guard_upgrade_plan, operation_id
from .vendor_job import _write

TERMINAL = {"stopped", "insufficient", "unavailable", "review"}


def _read(path):
    return json.loads(read_record_bytes(path, 64 * 1024 * 1024))


class GuardJobStore:
    """Separate guard ownership and controls under the existing exact client store."""

    def __init__(self, store):
        self.store, self.root = store, store.root / "guard-jobs"

    def path(self, job_id):
        return self.root / (operation_id(job_id) + ".json")

    def read(self, job_id):
        record = _read(self.path(job_id))
        if (record.get("schema_version") not in {1, 2} or record.get("job_id") != job_id
                or record.get("identity") != list(self.store.identity)
                or record.get("state") not in {
                    "ready", "running", "waiting", "paused", "travel", "scanning", *TERMINAL}):
            raise GuardFundingCycleStopped("The guard job record is invalid.")
        return record

    def current(self):
        path = self.root / "current.json"
        return self.read(_read(path)["job_id"]) if path.exists() else None

    def save(self, record):
        _write(self.path(record["job_id"]), record)

    def control(self, job_id):
        value = _read(self.root / (operation_id(job_id) + ".control.json"))
        if set(value) != {"mode"} or value["mode"] not in {"run", "pause", "travel", "stop"}:
            raise GuardFundingCycleStopped("The guard job control is invalid.")
        return value["mode"]

    def request(self, job_id, mode):
        if mode not in {"run", "pause", "travel", "stop"}:
            raise ValueError("invalid guard job mode")
        with exclusive_record_lock(self.root / "control.lock"):
            current = self.current()
            if (not current or current["job_id"] != job_id or (current["state"] in TERMINAL
                        and not (mode == "travel" and current["state"] == "unavailable"))
                    or self.control(job_id) == "stop"):
                raise GuardFundingCycleStopped("The guard job changed or needs review.")
            if current["state"] == "scanning" and mode != "stop":
                raise GuardFundingCycleStopped("Wait for the current area scan to finish.")
            _write(self.root / (job_id + ".control.json"), {"mode": mode})
            if mode in {"stop", "travel"}:
                try:
                    with exclusive_record_lock(self.root / "runner.lock", timeout_seconds=0.1):
                        current = self.read(job_id)
                        try:
                            GuardSpendingJournal(self.store.root).assert_idle()
                            if current["active_cycle"]:
                                raise GuardFundingCycleStopped(
                                    "Interrupted guard cycle needs review.")
                        except RuntimeError as exc:
                            current.update(state="review", detail=str(exc))
                        else:
                            current.update(
                                state="stopped" if mode == "stop" else "travel",
                                detail="Guard upgrades stopped." if mode == "stop" else
                                "Safe to move. Click Continue here when you arrive.",
                            )
                        self.save(current)
                except TimeoutError:
                    pass  # The live runner will observe the durable Stop control.

    def begin(self, binding, operation, discovery_id, context, *, now=None, poll_seconds=300):
        job_id = operation_id(operation.operation_id)
        if (type(poll_seconds) not in (int, float) or not math.isfinite(poll_seconds)
                or not 60 <= poll_seconds <= 3600):
            raise ValueError("guard rank checks must be between one minute and one hour apart")
        with exclusive_record_lock(self.root / "runner.lock", timeout_seconds=0.1):
            previous = self.current()
            if self.path(job_id).exists() or previous and previous["state"] not in {
                "stopped", "insufficient", "unavailable",
            }:
                raise GuardFundingCycleStopped("Continue or review the existing guard job first.")
            GuardSpendingJournal(self.store.root).assert_idle()
            plan = build_guard_upgrade_plan(self.store, binding, discovery_id, context)
            record = {
                "schema_version": 2, "funding_source": "carried",
                "identity": list(self.store.identity), "job_id": job_id,
                "plan": asdict(plan), "window": binding.game_window_handle,
                "state": "ready", "detail": "Ready to upgrade the verified guards.",
                "created_at": time.time() if now is None else now,
                "poll_seconds": poll_seconds, "active_cycle": None, "cursor": 0,
                "withdrawn": 0, "deposited": 0, "spent": 0, "upgrades_started": 0,
                "town_coverage_verified": False, "maximum_rank_verified": False,
                "guards": [{"state": "ready", "minimum_rank": rank, "observed_rank": rank,
                            "next_check_at": 0, "last_cycle": None, "upgrades_started": 0}
                           for rank in plan.initial_ranks],
            }
            self.save(record)
            _write(self.root / (job_id + ".control.json"), {"mode": "run"})
            _write(self.root / "current.json", {"job_id": job_id})
            return record

    def remembered(self, binding, job_id, context):
        record = self.read(job_id)
        targets = _validate_plan(self, binding, record)
        if any((t.scene, t.root) != (context.scene, context.root) for t in targets):
            raise GuardFundingCycleStopped("Travel cannot cross a game scene or character change.")
        return {(t.building, t.guard) for t in targets}

    def continue_here(self, binding, job_id, discovery_id, context):
        """Atomically extend one job; never reset accounting or a guard's rank floor."""
        with exclusive_record_lock(self.root / "control.lock"), exclusive_record_lock(
            self.root / "runner.lock", timeout_seconds=0.1,
        ):
            record = self.read(job_id)
            if (not self.current() or self.current()["job_id"] != job_id
                    or record["state"] not in {"travel", "scanning"}
                    or self.control(job_id) != "travel"
                    or record["active_cycle"]):
                raise GuardFundingCycleStopped("Wait until Travel says it is safe to move.")
            GuardSpendingJournal(self.store.root).assert_idle()
            known = self.remembered(binding, job_id, context)
            plan = build_guard_upgrade_plan(
                self.store, binding, discovery_id, context, allow_empty=True,
            )
            added = {(t.building, t.guard) for t in plan.targets}
            if known & added:
                raise GuardFundingCycleStopped("The new area duplicates existing guard evidence.")
            navigation = _read(self.store.root / "guard-navigation" / (discovery_id + ".json"))
            visible = set()
            for building in navigation["roster"]:
                if building["state"] not in {"verified", "partial"}:
                    continue
                for guard in building["guards"]:
                    key = (building["building"]["object_id"], guard["hireling"]["object_id"])
                    if guard.get("state") == "remembered":
                        if key not in known or guard.get("window_verified") is not False:
                            raise GuardFundingCycleStopped("Remembered guard provenance changed.")
                        visible.add(key)
                    elif guard.get("window_verified") is True:
                        visible.add(key)
            record.setdefault("area_plans", []).append(asdict(plan))
            record["guards"].extend(
                dict(state="ready", minimum_rank=rank, observed_rank=rank, next_check_at=0,
                     last_cycle=None, upgrades_started=0) for rank in plan.initial_ranks
            )
            targets = _validate_plan(self, binding, json.loads(json.dumps(record)))
            record["area_indices"] = [i for i, t in enumerate(targets)
                                      if (t.building, t.guard) in visible]
            record.update(state="ready",
                          detail="Continuing here; previous guard progress retained.")
            self.save(record)
            _write(self.root / (job_id + ".control.json"), {"mode": "run"})
            return record


def _validate_plan(jobs, binding, record):
    if record.get("schema_version") != 2 or record.get("funding_source") != "carried":
        raise GuardFundingCycleStopped(
            "The previous warehouse-funded job needs review; no replay sent.")
    plans = [record["plan"], *record.get("area_plans", [])]
    targets, ranks = [], []
    for plan in plans:
        current = build_guard_upgrade_plan(
            jobs.store, binding, plan["discovery_operation_id"],
            Snapshot.decode(bytes.fromhex(plan["context_snapshot"])), allow_empty=True,
        )
        if json.loads(json.dumps(asdict(current))) != plan:
            raise GuardFundingCycleStopped("The guard plan or game window changed.")
        targets.extend(current.targets)
        ranks.extend(current.initial_ranks)
    if (record["window"] != binding.game_window_handle
            or len(record["guards"]) != len(targets)
            or len({t.guard for t in targets}) != len(targets)
            or len({(t.scene, t.root) for t in targets}) != 1):
        raise GuardFundingCycleStopped("The guard plan or game window changed.")
    active = record.get("area_indices", list(range(len(targets))))
    if (not isinstance(active, list) or len(set(active)) != len(active)
            or any(type(i) is not int or not 0 <= i < len(targets) for i in active)):
        raise GuardFundingCycleStopped("The active guard area is invalid.")
    for guard, initial in zip(record["guards"], ranks, strict=True):
        if (guard["state"] not in {"ready", "waiting", "insufficient", "unavailable"}
                or type(guard["minimum_rank"]) is not int
                or not initial <= guard["minimum_rank"] < 2**32 - 1
                or type(guard["next_check_at"]) not in (float, int)
                or not math.isfinite(guard["next_check_at"])):
            raise GuardFundingCycleStopped("The guard progress record is invalid.")
    return tuple(targets)


def _apply_cycle(jobs, record, target, now):
    active = record["active_cycle"]
    cycle = _read(jobs.store.root / "guard-funding-cycles" / (active["operation_id"] + ".json"))
    guard = record["guards"][active["index"]]
    if (cycle.get("schema_version") != 2
            or cycle.get("funding_source") != "carried" or cycle.get("withdrawn") != 0
            or cycle.get("identity") != record["identity"]
            or cycle.get("operation_id") != active["operation_id"]
            or cycle.get("target") != asdict(target) or cycle.get("window") != record["window"]
            or cycle.get("process_id") != target.process_id
            or cycle.get("process_creation_filetime_utc") != target.creation
            or cycle.get("minimum_rank") != guard["minimum_rank"]
            or cycle.get("state") not in {"started", "waiting", "insufficient", "unavailable"}
            or any(a.get("state") != "confirmed" for a in cycle.get("actions", []))
            or any(type(cycle.get(k)) is not int or cycle[k] < 0
                   for k in ("withdrawn", "deposited", "spent", "initial_rank"))):
        raise GuardFundingCycleStopped("The interrupted guard cycle needs review; no replay sent.")
    if cycle["state"] == "started":
        if (cycle["spent"] <= 0 or cycle["spent"] != cycle.get("quoted_cost")
                or cycle["initial_rank"] < guard["minimum_rank"]):
            raise GuardFundingCycleStopped("The completed guard upgrade lacks its exact debit.")
        guard["minimum_rank"] = cycle["initial_rank"] + 1
        guard["upgrades_started"] += 1
        record["upgrades_started"] += 1
    guard.update(
        state="waiting" if cycle["state"] in {"started", "waiting"} else cycle["state"],
        observed_rank=cycle.get("observed_rank", cycle["initial_rank"]),
        next_check_at=now + record["poll_seconds"], last_cycle=active["operation_id"],
        detail=cycle["detail"],
    )
    for name in ("withdrawn", "deposited", "spent"):
        record[name] += cycle[name]
    record.update(active_cycle=None, cursor=(active["index"] + 1) % len(record["guards"]))
    jobs.save(record)  # Accounting and clearing the in-flight marker are one atomic replacement.


def run_guard_upgrade_job(
    store, binding, job_id, *, cancelled, cycle_runner=run_guard_funding_cycle,
    cycle_options=None, clock=time.time, sleep=time.sleep,
):
    """Round-robin all admitted guards, waiting for new ranks without replaying actions.

    A restart may account for a fully confirmed cycle exactly once. Missing,
    partial or uncertain cycle records stop the entire job, including new IDs.
    A no-offer result remains unavailable; it never proves maximum rank or city
    coverage. Pause takes effect after the current transaction; Stop cancels it.
    """
    jobs = GuardJobStore(store)
    with exclusive_record_lock(jobs.root / "runner.lock", timeout_seconds=0.1):
        record = jobs.read(job_id)
        if not jobs.current() or jobs.current()["job_id"] != job_id:
            raise GuardFundingCycleStopped("This guard job is no longer current.")
        if record["state"] in TERMINAL:
            return record
        journal = GuardSpendingJournal(store.root)
        try:
            targets = _validate_plan(jobs, binding, record)
            journal.assert_idle()
            if record["active_cycle"]:
                active = record["active_cycle"]
                operation_id(active["operation_id"])
                if type(active["index"]) is not int or not 0 <= active["index"] < len(targets):
                    raise GuardFundingCycleStopped("The interrupted guard target is invalid.")
                _apply_cycle(jobs, record, targets[active["index"]], clock())
            while True:
                mode = jobs.control(job_id)
                if cancelled() or mode == "stop":
                    record.update(state="stopped", detail="Guard upgrades stopped.")
                    jobs.save(record)
                    return record
                if mode in {"pause", "travel"}:
                    record.update(
                        state="paused" if mode == "pause" else "travel",
                        detail="Guard upgrades paused between transactions." if mode == "pause"
                        else "Safe to move. Click Continue here when you arrive.",
                    )
                    jobs.save(record)
                    return record
                journal.assert_idle()
                if any(g["state"] == "insufficient" for g in record["guards"]):
                    record.update(state="insufficient",
                                  detail="Carried gold is insufficient. Refill before restarting.")
                    jobs.save(record)
                    return record
                area = record.get("area_indices", list(range(len(targets))))
                remaining = [i for i in area
                             if record["guards"][i]["state"] in {"ready", "waiting"}]
                if not remaining and "area_indices" in record:
                    _write(jobs.root / (job_id + ".control.json"), {"mode": "travel"})
                    record.update(state="travel", detail=
                                  "No pending guards in this area. Move, then click Continue here.")
                    jobs.save(record)
                    return record
                if not remaining:
                    insufficient = any(g["state"] == "insufficient" for g in record["guards"])
                    record.update(
                        state="insufficient" if insufficient else "unavailable",
                        detail="Remaining offers exceed available gold." if insufficient else
                        "No upgrade offers remain. Maximum rank and town coverage are unverified.",
                    )
                    jobs.save(record)
                    return record
                now = clock()
                due = [i for i in remaining if record["guards"][i]["next_check_at"] <= now]
                if not due:
                    if record["state"] != "waiting":
                        record.update(state="waiting", detail="Waiting for guard ranks to finish.")
                        jobs.save(record)
                    next_check = min(record["guards"][i]["next_check_at"] for i in remaining)
                    sleep(min(1.0, next_check - now))
                    continue
                index = min(due, key=lambda i: (
                    record["guards"][i]["upgrades_started"] > 0,
                    (i - record["cursor"]) % len(targets),
                ))
                cycle_id = "operation-" + uuid.uuid4().hex
                record.update(state="running", detail="Checking and funding the next guard.",
                              active_cycle={"operation_id": cycle_id, "index": index})
                jobs.save(record)  # No native activity can precede the durable cycle identity.
                cycle_runner(
                    store, binding, SimpleNamespace(operation_id=cycle_id), targets[index],
                    cancelled=lambda: cancelled() or jobs.control(job_id) == "stop",
                    minimum_rank=record["guards"][index]["minimum_rank"], **(cycle_options or {}),
                )
                journal.assert_idle()
                _apply_cycle(jobs, record, targets[index], clock())
        except Exception as exc:
            record.update(state="review", detail=str(exc) or type(exc).__name__)
            jobs.save(record)
            raise
