import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_observation.native_city_registry import read_native_city_registry
from shadowbane_lab.manager import condemn_cycle
from shadowbane_lab.manager import condemn_job as module
from shadowbane_lab.manager.condemn_plan import CondemnPlanStore
from tests import test_condemn_cycle as cycle_tests
from tests.test_condemn_cycle import OWNER, ScopedTransport
from tests.test_condemn_plan import nearby
from tests.test_condemn_transaction import LIFE
from tests.test_native_city_registry import fixture as registry_memory

cycle_setup = cycle_tests.setup


@pytest.fixture
def setup(cycle_setup):
    base = cycle_setup
    plans = CondemnPlanStore(base.store)
    catalog = read_native_city_registry(registry_memory())
    for city in catalog["cities"]:
        for role in ("guild", "nation"):
            city[role]["key"]["object_id"] = 200
    candidates = nearby(base.store)
    second = deepcopy(candidates["roster"]["buildings"][0])
    second["building"]["object_id"] = 101
    second["hirelings"][0]["hireling"]["object_id"] = 301
    candidates["roster"]["buildings"].append(second)
    candidates.update(buildings=3, hirelings=3)
    prepared = plans.prepare(base.operation.operation_id, base.context, OWNER, candidates, catalog)
    jobs = module.CondemnJobStore(base.store)
    operation = SimpleNamespace(operation_id="operation-" + "b" * 32)
    record = jobs.begin(
        base.binding,
        operation,
        prepared["preparation_id"],
        prepared["sha256"],
        ["4:200", "5:200"],
        [100, 101],
        owner_reader=lambda _: OWNER,
    )
    base.options["mode"] = "existing"

    def cycle_runner(store, binding, operation, context, targets, owner, **options):
        return condemn_cycle.run_condemn_cycle(
            store,
            binding,
            operation,
            context,
            targets,
            owner,
            navigation_factory=base.navigation_factory,
            session_factory=base.session_factory,
            clock=base.clock,
            sleep=lambda _: None,
            **options,
        )

    def run(**options):
        return module.run_condemn_job(
            base.store,
            base.binding,
            record["job_id"],
            cancelled=lambda: False,
            owner_reader=lambda _: OWNER,
            cycle_runner=options.pop("cycle_runner", cycle_runner),
            **options,
        )

    return SimpleNamespace(base=base, jobs=jobs, record=record, run=run, cycle_runner=cycle_runner)


def count(setup):
    return sum(len(s._transport.commands) for s in setup.base.sessions)


def test_complete_job_visits_each_building_and_records_each_distinct_scope(setup):
    result = setup.run()
    assert result["state"] == "complete" and result["active_cycle"] is None
    assert len(result["cycles"]) == 2
    assert len(setup.jobs.progress(setup.jobs.read(result["job_id"]))) == 4
    assert len(CondemnProgressStore(setup.base.store.root).verified_native_targets(LIFE)) == 4
    assert setup.base.world.calls == ["building", "building"]
    before = count(setup)
    with pytest.raises(module.CondemnCycleStopped, match="ended"):
        setup.run()
    assert count(setup) == before


def test_pause_and_resume_never_revisit_finished_crests(setup):
    invoked = []

    def pause_between(*args, **kwargs):
        result = setup.cycle_runner(*args, **kwargs)
        invoked.append(result)
        if len(invoked) == 1:
            setup.jobs.request(setup.record["job_id"], "pause")
        return result

    result = setup.run(cycle_runner=pause_between)
    assert result["state"] == "paused" and len(setup.jobs.progress(result)) == 2
    first_requests = {
        a["request"] for a in CondemnProgressStore(setup.base.store.root).read()["attempts"]
    }
    setup.jobs.request(result["job_id"], "run")
    result = setup.run()
    assert result["state"] == "complete" and len(result["cycles"]) == 2
    attempts = CondemnProgressStore(setup.base.store.root).read()["attempts"]
    assert len(attempts) == 4 and first_requests < {a["request"] for a in attempts}
    assert setup.base.world.calls == ["building", "building"]


def test_restart_after_completed_cycle_recovers_proof_without_replaying(setup):
    def crash(*args, **kwargs):
        setup.cycle_runner(*args, **kwargs)
        raise KeyboardInterrupt("simulated worker termination before job update")

    with pytest.raises(KeyboardInterrupt):
        setup.run(cycle_runner=crash)
    saved = setup.jobs.read(setup.record["job_id"])
    assert saved["state"] == "running" and saved["active_cycle"]
    assert len(CondemnProgressStore(setup.base.store.root).read()["attempts"]) == 2
    result = setup.run()
    assert result["state"] == "complete" and len(setup.jobs.progress(result)) == 4
    assert len(result["cycles"]) == 2


def test_lost_native_reply_cannot_be_resumed_by_new_worker(setup, monkeypatch):
    submit = ScopedTransport.submit

    def timeout(self, command, timeout_ms):
        if command.kind.name == "ENSURE":
            self.mode = "timeout"
        return submit(self, command, timeout_ms)

    monkeypatch.setattr(ScopedTransport, "submit", timeout)
    with pytest.raises(RuntimeError):
        setup.run()
    record = setup.jobs.read(setup.record["job_id"])
    assert record["state"] == "review" and record["active_cycle"]
    assert CondemnProgressStore(setup.base.store.root).read()["active"]
    before = count(setup)
    with pytest.raises(module.CondemnCycleStopped):
        setup.run()
    assert count(setup) == before


def test_stop_while_idle_finishes_control_without_requiring_a_worker(setup):
    setup.jobs.request(setup.record["job_id"], "stop")
    assert setup.jobs.read(setup.record["job_id"])["state"] == "stopped"
    assert not setup.base.sessions and not setup.base.world.calls


def test_pause_before_start_and_resume_keeps_the_same_selection(setup):
    setup.jobs.request(setup.record["job_id"], "pause")
    result = setup.run()
    assert result["state"] == "paused" and not setup.base.sessions
    setup.jobs.request(result["job_id"], "run")
    assert setup.run()["state"] == "complete"


@pytest.mark.parametrize("change", ["process", "window"])
def test_changed_binding_stops_without_creating_a_cycle(setup, change):
    if change == "process":
        setup.base.binding.game_process_id += 1
    else:
        setup.base.binding.game_window_handle += 1
    with pytest.raises(module.CondemnCycleStopped, match="session"):
        setup.run()
    assert not setup.base.sessions and not setup.base.world.calls


def test_missing_active_cycle_is_not_treated_as_unattempted_work(setup):
    def crash(*_args, **_kwargs):
        raise KeyboardInterrupt("before cycle publish")

    with pytest.raises(KeyboardInterrupt):
        setup.run(cycle_runner=crash)
    with pytest.raises(OSError):
        setup.run()
    assert setup.jobs.read(setup.record["job_id"])["state"] == "review"
    assert not setup.base.sessions


def test_changed_sealed_cycle_blocks_progress_instead_of_recounting(setup):
    result = setup.run()
    reference = result["cycles"][0]
    path = setup.base.store.root / "condemn-cycles" / (reference["operation_id"] + ".json")
    cycle = json.loads(path.read_bytes())
    cycle["actions"].pop()
    path.write_text(json.dumps(cycle))
    with pytest.raises(module.CondemnCycleStopped, match="proof changed"):
        setup.jobs.progress(result)


def test_job_cannot_add_an_unselected_catalog_identity_after_start(setup):
    record = setup.jobs.read(setup.record["job_id"])
    record["selection"]["targets"][0] = "6400000008000000c90000001700000004000000"
    setup.jobs.save(record)
    with pytest.raises(module.CondemnCycleStopped, match="targets changed"):
        setup.jobs.read(record["job_id"])


def test_completed_native_proof_cannot_be_replaced_by_cycle_status(setup):
    result = setup.run()
    progress = CondemnProgressStore(setup.base.store.root)
    record = json.loads(progress.path.read_bytes())
    record["attempts"].pop()
    progress.path.write_text(json.dumps(record))
    with pytest.raises(module.CondemnCycleStopped, match="lacks durable completion"):
        setup.jobs.progress(result)


def test_resume_recovers_a_native_receipt_before_cycle_status_was_saved(setup, monkeypatch):
    from shadowbane_lab.manager import condemn_cycle as cycle_module

    original = cycle_module._write

    def interrupted(path, record):
        if record["actions"] and record["actions"][-1]["state"] == "already_enabled":
            raise KeyboardInterrupt("after native receipt before cycle receipt")
        original(path, record)

    monkeypatch.setattr(cycle_module, "_write", interrupted)
    with pytest.raises(KeyboardInterrupt):
        setup.run()
    assert len(CondemnProgressStore(setup.base.store.root).read()["attempts"]) == 1
    monkeypatch.setattr(cycle_module, "_write", original)
    result = setup.run()
    assert result["state"] == "complete"
    assert len(CondemnProgressStore(setup.base.store.root).read()["attempts"]) == 4
    assert len(result["cycles"]) == 3
