"""Persistent finite Condemn jobs with proof-backed progress across building cycles."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from types import SimpleNamespace

from shadowbane_lab.client_extension.condemn_evidence import Lifetime, canonical
from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.condemn_wire import Command, Target, Verb
from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.record_store import exclusive_record_lock, read_record_bytes

from .condemn_cycle import CondemnContext, CondemnCycleStopped, run_condemn_cycle
from .condemn_plan import CondemnPlanStore
from .guard_owner import read_guard_owner, require_owner
from .guard_plan import operation_id
from .vendor_job import _write

STATES = {"ready", "running", "paused", "complete", "stopped", "review"}
TERMINAL = {"complete", "stopped", "review"}
LIMIT = 32 * 1024 * 1024


def _read(path, limit=LIMIT):
    return json.loads(read_record_bytes(path, limit))


def _digest(record):
    return hashlib.sha256(canonical(record)).hexdigest()


class CondemnJobStore:
    def __init__(self, store):
        self.store, self.root = store, store.root / "condemn-jobs"
        self.plans = CondemnPlanStore(store)

    def path(self, job_id):
        return self.root / (operation_id(job_id) + ".json")

    def read(self, job_id):
        r = _read(self.path(job_id))
        if (
            set(r)
            != {
                "schema_version",
                "identity",
                "job_id",
                "window",
                "selection",
                "selection_sha256",
                "state",
                "detail",
                "cycles",
                "active_cycle",
            }
            or type(r["schema_version"]) is not int
            or r["schema_version"] != 1
            or r["identity"] != list(self.store.identity)
            or r["job_id"] != job_id
            or r["state"] not in STATES
            or not isinstance(r["detail"], str)
            or type(r["window"]) is not int
            or not 0 < r["window"] < 2**32
            or not isinstance(r["cycles"], list)
            or len(r["cycles"]) > 4096
        ):
            raise CondemnCycleStopped("The Condemn job record is invalid.")
        s = r["selection"]
        if _digest(s) != r["selection_sha256"]:
            raise CondemnCycleStopped("The selected Condemn targets changed.")
        if set(s) != {
            "preparation_id",
            "preparation_sha256",
            "context",
            "owner",
            "targets",
            "town_coverage_verified",
            "complete_guild_directory_verified",
            "nation_inheritance_verified",
        } or any(
            s[k] is not False
            for k in (
                "town_coverage_verified",
                "complete_guild_directory_verified",
                "nation_inheritance_verified",
            )
        ):
            raise CondemnCycleStopped("The Condemn job scope changed.")
        source = self.plans.read(s["preparation_id"])
        if (
            _digest(source) != s["preparation_sha256"]
            or source["context"] != s["context"]
            or source["owner"] != s["owner"]
        ):
            raise CondemnCycleStopped("The Condemn job no longer matches its source.")
        _, catalog, buildings = self.plans._validate(source)
        crests = {(tuple(c["identity"]), c["scope"]) for c in catalog["entries"]}
        observed = {tuple(b["building"]) for b in buildings}
        targets = s["targets"]
        if not isinstance(targets, list) or not 0 < len(targets) <= 4096:
            raise CondemnCycleStopped("Invalid Condemn target count.")
        parsed = [Target.decode(bytes.fromhex(t)) for t in targets]
        if len(set(parsed)) != len(parsed) or any(
            t.encode().hex() != raw
            or t.building not in observed
            or (t.identity, t.scope) not in crests
            for t, raw in zip(parsed, targets, strict=True)
        ):
            raise CondemnCycleStopped("Condemn targets differ from the observed selection.")
        # Canonical ordering keeps each building in one contiguous group.
        if parsed != sorted(parsed, key=lambda t: (t.building, t.scope, t.identity)):
            raise CondemnCycleStopped("Condemn target order changed.")
        seen = set()
        for index, cycle in enumerate(r["cycles"]):
            if set(cycle) != {"operation_id", "targets", "sha256"}:
                raise CondemnCycleStopped("Invalid Condemn cycle reference.")
            ident = operation_id(cycle["operation_id"])
            if ident in seen:
                raise CondemnCycleStopped("Repeated Condemn cycle reference.")
            seen.add(ident)
            if cycle["sha256"] is None:
                if index != len(r["cycles"]) - 1 or r["active_cycle"] != ident:
                    raise CondemnCycleStopped("An unfinished Condemn cycle lost its owner.")
            elif (
                not isinstance(cycle["sha256"], str)
                or len(cycle["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in cycle["sha256"])
            ):
                raise CondemnCycleStopped("Invalid saved Condemn cycle digest.")
        if r["active_cycle"] is not None and (
            not r["cycles"]
            or r["cycles"][-1]["operation_id"] != r["active_cycle"]
            or r["cycles"][-1]["sha256"] is not None
        ):
            raise CondemnCycleStopped("Invalid active Condemn cycle.")
        return r

    def current(self):
        path = self.root / "current.json"
        if not path.exists():
            return None
        pointer = _read(path, 256)
        if set(pointer) != {"job_id"}:
            raise CondemnCycleStopped("Invalid Condemn job pointer.")
        return self.read(pointer["job_id"])

    def save(self, record):
        _write(self.path(record["job_id"]), record)

    def control(self, job_id):
        r = _read(self.root / (operation_id(job_id) + ".control.json"), 256)
        if set(r) != {"mode"} or r["mode"] not in {"run", "pause", "stop"}:
            raise CondemnCycleStopped("Invalid Condemn job control.")
        return r["mode"]

    def request(self, job_id, mode):
        if mode not in {"run", "pause", "stop"}:
            raise ValueError("invalid Condemn control")
        with exclusive_record_lock(self.root / "control.lock"):
            current = self.current()
            if (
                not current
                or current["job_id"] != job_id
                or self.control(job_id) == "stop"
            ):
                raise CondemnCycleStopped("The Condemn job changed or needs review.")
            if (
                mode == "run"
                and current["state"] == "review"
                and current["detail"] == "native action host lease expired"
            ):
                # Only a proven completed boundary can recover this pre-dispatch
                # failure. Missing/uncertain native receipts still prohibit resume.
                with exclusive_record_lock(self.root / "runner.lock", timeout_seconds=0.1):
                    CondemnProgressStore(self.store.root).assert_idle()
                    GuardSpendingJournal(self.store.root).assert_idle()
                    self.progress(current, recover=True)
                    current.update(
                        state="paused",
                        detail="Lease expired at a verified boundary; completed crests retained.",
                    )
                    self.save(current)
            if current["state"] in TERMINAL:
                raise CondemnCycleStopped("The Condemn job changed or needs review.")
            _write(self.root / (job_id + ".control.json"), {"mode": mode})
            if mode != "run":
                try:
                    with exclusive_record_lock(self.root / "runner.lock", timeout_seconds=0.1):
                        current = self.read(job_id)
                        try:
                            self.progress(current, recover=True)
                        except (OSError, ValueError, RuntimeError) as exc:
                            current.update(state="review", detail=str(exc))
                        else:
                            current.update(
                                state="stopped" if mode == "stop" else "paused",
                                detail="Stopped with completed crests saved."
                                if mode == "stop"
                                else "Paused with completed crests saved.",
                            )
                        self.save(current)
                except TimeoutError:
                    pass  # The running cycle observes the control at its next safe boundary.

    def begin(self, binding, operation, preparation, digest, crests, buildings, *, owner_reader):
        job_id = operation_id(operation.operation_id)
        with exclusive_record_lock(self.root / "control.lock"):
            current = self.current()
            if (
                self.path(job_id).exists()
                or current
                and current["state"] not in {"complete", "stopped"}
            ):
                raise CondemnCycleStopped("Continue the existing Condemn job first.")
            selection = self.plans.select(preparation, digest, crests, buildings)
            life = Lifetime(**selection["context"]["lifetime"])
            if (life.process_id, life.creation) != (
                binding.game_process_id,
                binding.game_process_started_at_100ns,
            ):
                raise CondemnCycleStopped("The crest selection belongs to another game session.")
            require_owner(selection["owner"], owner_reader(binding))
            GuardSpendingJournal(self.store.root).assert_idle()
            record = dict(
                schema_version=1,
                identity=list(self.store.identity),
                job_id=job_id,
                window=binding.game_window_handle,
                selection=selection,
                selection_sha256=_digest(selection),
                state="ready",
                detail="Ready to apply the selected crests.",
                cycles=[],
                active_cycle=None,
            )
            self.save(record)
            _write(self.root / (job_id + ".control.json"), {"mode": "run"})
            _write(self.root / "current.json", {"job_id": job_id})
            return self.read(job_id)

    def progress(self, record, *, recover=False):
        """Count only native-qualified state, anchored to each saved cycle action.

        Recovery may seal the last interrupted cycle only when both journals are
        idle and every dispatched crest has durable proof. Missing intent/receipt
        is review, never a reason to resubmit that crest.
        """
        saved = CondemnProgressStore(self.store.root).read()
        attempts = {a["request"]: a for a in saved["attempts"]}
        if recover:
            CondemnProgressStore(self.store.root).assert_idle()
            GuardSpendingJournal(self.store.root).assert_idle()
        expected = record["selection"]["targets"]
        completed, requests = [], set()
        for reference in record["cycles"]:
            active = reference["sha256"] is None
            if active and not recover:
                break  # Summary may report only sealed progress while the worker writes.
            path = self.store.root / "condemn-cycles" / (reference["operation_id"] + ".json")
            cycle = _read(path)
            if (
                not active
                and _digest(cycle) != reference["sha256"]
                or cycle.get("schema_version") != 1
                or cycle.get("identity") != list(self.store.identity)
                or cycle.get("operation_id") != reference["operation_id"]
                or cycle.get("context") != record["selection"]["context"]
                or cycle.get("owner") != record["selection"]["owner"]
                or cycle.get("window") != record["window"]
                or cycle.get("targets") != reference["targets"]
                or cycle.get("state") not in {"running", "paused", "complete", "review"}
            ):
                raise CondemnCycleStopped("Saved Condemn building proof changed.")
            remaining = expected[len(completed) :]
            group = reference["targets"]
            if (
                not isinstance(group, list)
                or not group
                or group != remaining[: len(group)]
                or len({Target.decode(bytes.fromhex(t)).building for t in group}) != 1
            ):
                raise CondemnCycleStopped("Saved Condemn building order changed.")
            actions = cycle["actions"]
            if not isinstance(actions, list) or len(actions) > len(group):
                raise CondemnCycleStopped("Invalid Condemn building progress.")
            for index, action in enumerate(actions):
                if (
                    set(action) != {"target", "request", "state"}
                    or action["target"] != group[index]
                    or action["request"] in requests
                    or action["state"] not in {"intent", "state_verified", "already_enabled"}
                ):
                    raise CondemnCycleStopped("Invalid completed crest reference.")
                native = attempts.get(action["request"])
                if (
                    not native
                    or native.get("kind") != "native"
                    or native["state"] not in {"state_verified", "already_enabled"}
                    or native["lifetime"] != record["selection"]["context"]["lifetime"]
                ):
                    raise CondemnCycleStopped("An interrupted crest lacks durable completion.")
                command = Command.decode(bytes.fromhex(native["command"]), Verb.ENSURE)
                if (
                    command.target.encode().hex() != action["target"]
                    or command.window != record["window"]
                    or command.expected.root != record["selection"]["context"]["root"]
                ):
                    raise CondemnCycleStopped("The completed crest belongs to another building.")
                completed.append(action["target"])
                requests.add(action["request"])
            if cycle["state"] == "complete" and len(actions) != len(group):
                raise CondemnCycleStopped("A completed building has unfinished crests.")
            if active:
                # An empty or partial interrupted cycle cannot be silently retried.
                # A normal pause is an explicit safe boundary, including zero actions.
                if cycle["state"] not in {"complete", "paused"} and not actions:
                    raise CondemnCycleStopped("An interrupted building needs review.")
                reference["sha256"] = _digest(cycle)
                record["active_cycle"] = None
        if record["state"] == "complete" and len(completed) != len(expected):
            raise CondemnCycleStopped("The completed Condemn job lacks full selected progress.")
        return tuple(completed)


def run_condemn_job(
    store,
    binding,
    job_id,
    *,
    cancelled,
    owner_reader=read_guard_owner,
    cycle_runner=run_condemn_cycle,
    clock=time.monotonic,
):
    jobs = CondemnJobStore(store)
    with exclusive_record_lock(jobs.root / "runner.lock", timeout_seconds=0.1):
        record = jobs.read(job_id)
        if record["state"] in TERMINAL:
            raise CondemnCycleStopped("This Condemn job has ended or needs review.")
        try:
            selection = record["selection"]
            context = CondemnContext(
                Lifetime(**selection["context"]["lifetime"]), selection["context"]["root"]
            )
            if (context.lifetime.process_id, context.lifetime.creation, record["window"]) != (
                binding.game_process_id,
                binding.game_process_started_at_100ns,
                binding.game_window_handle,
            ):
                raise CondemnCycleStopped("The Condemn job belongs to another game session.")
            require_owner(selection["owner"], owner_reader(binding))
            completed = jobs.progress(record, recover=True)
            jobs.save(record)
            deadline = clock() + 3600
            while True:
                if cancelled():
                    raise CondemnCycleStopped("Condemn dispatch authority ended.")
                require_owner(selection["owner"], owner_reader(binding))
                control = jobs.control(job_id)
                remaining = selection["targets"][len(completed) :]
                if not remaining:
                    record.update(
                        state="complete", detail="All selected building crests are confirmed."
                    )
                    break
                if control != "run" or clock() >= deadline:
                    record.update(
                        state="stopped" if control == "stop" else "paused",
                        detail="Stopped with completed crests saved."
                        if control == "stop"
                        else "Paused with completed crests saved.",
                    )
                    break
                building = Target.decode(bytes.fromhex(remaining[0])).building
                group = []
                for raw in remaining:
                    if Target.decode(bytes.fromhex(raw)).building != building:
                        break
                    group.append(raw)
                if len(record["cycles"]) >= 4096:
                    raise CondemnCycleStopped("Condemn cycle history is at capacity.")
                cycle_id = "operation-" + uuid.uuid4().hex
                record["cycles"].append(dict(operation_id=cycle_id, targets=group, sha256=None))
                record.update(
                    active_cycle=cycle_id,
                    state="running",
                    detail=(
                        f"Applying crests: {len(completed)} of "
                        f"{len(selection['targets'])} confirmed."
                    ),
                )
                jobs.save(record)
                cycle_runner(
                    store,
                    binding,
                    SimpleNamespace(operation_id=cycle_id),
                    context,
                    tuple(Target.decode(bytes.fromhex(t)) for t in group),
                    selection["owner"],
                    cancelled=cancelled,
                    owner_reader=owner_reader,
                    pause_requested=lambda: jobs.control(job_id) != "run" or clock() >= deadline,
                )
                completed = jobs.progress(record, recover=True)
                jobs.save(record)
            jobs.save(record)
            return record
        except Exception as exc:
            record.update(state="review", detail=str(exc) or type(exc).__name__)
            jobs.save(record)
            raise
