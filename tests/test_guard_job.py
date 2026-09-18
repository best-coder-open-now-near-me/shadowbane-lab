import copy
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.client_extension.vendor_navigation_wire import Snapshot
from shadowbane_lab.manager.guard_funding_cycle import (
    GuardFundingCycleStopped,
    run_guard_funding_cycle,
)
from shadowbane_lab.manager.guard_job import GuardJobStore, run_guard_upgrade_job
from shadowbane_lab.manager.guard_plan import build_guard_upgrade_plan
from shadowbane_lab.manager.vendor_job import VendorJobStore, _write
from tests.test_guard_funding_cycle import World

DISCOVERY = "operation-" + "a" * 32
JOB = "operation-" + "b" * 32
CONTEXT = Snapshot(scene=1, revision=1, root=100, manager=200)


@pytest.fixture
def setup(tmp_path):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    binding = SimpleNamespace(game_process_id=988, game_process_started_at_100ns=123,
                              game_window_handle=1000)
    common = dict(schema_version=1, identity=list(store.identity), operation_id=DISCOVERY,
                  game_process_id=988, game_creation_filetime=123, state="complete")
    nearby = dict(common, scene=1, root=100, roster={"buildings": [
        {"building": {"object_id": b, "object_type": 8}} for b in (123, 456)
    ]})
    discovery = dict(common, guards=2, attempts=[{"expected": CONTEXT.encode().hex()}], roster=[])
    for b, g in ((123, 777), (456, 778)):
        key = {"object_id": g, "object_type": 37}
        row = {"hireling": key, "rank": 1, "display_name": "Archer"}
        roster = dict(process_id=988, process_creation_filetime_utc=123,
                      building={"object_id": b, "object_type": 8},
                      hirelings=[row], hireling_slots=1, building_roster_verified=True)
        discovery["roster"].append(dict(
            building=roster["building"], display_name="Identical tower name", state="verified",
            roster=roster, guards=[dict(row, state="verified", window_verified=True,
                                      observation=dict(roster, selected_guard=key))],
        ))
    paths = [store.root / folder / (DISCOVERY + ".json")
             for folder in ("guard-discovery", "guard-navigation")]

    def save():
        for path, value in zip(paths, (nearby, discovery), strict=True):
            _write(path, value)
    save()
    jobs, clock, calls = GuardJobStore(store), [1000.0], []

    def begin(**kwargs):
        return jobs.begin(binding, SimpleNamespace(operation_id=JOB), DISCOVERY, CONTEXT,
                          now=clock[0], poll_seconds=60, **kwargs)

    def result(store, binding, operation, target, *, cancelled, minimum_rank, **kwargs):
        assert not cancelled()
        # Durable scheduling intent must precede even a read-only cycle.
        active = jobs.read(JOB)["active_cycle"]
        assert active["operation_id"] == operation.operation_id
        assert not calls or calls[-1]["operation_id"] != operation.operation_id
        record = dict(schema_version=2, funding_source="carried",
                      identity=list(store.identity), target=asdict(target),
                      operation_id=operation.operation_id, window=1000,
                      process_id=988, process_creation_filetime_utc=123, minimum_rank=minimum_rank,
                      state="unavailable", detail="No offer; maximum unverified.",
                      initial_rank=minimum_rank,
                      withdrawn=0, deposited=0, spent=0, actions=[])
        calls.append(record)
        _write(store.root / "guard-funding-cycles" / (operation.operation_id + ".json"), record)
        return record

    def run(**kwargs):
        options = dict(cancelled=lambda: False, cycle_runner=result, clock=lambda: clock[0],
                       sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds))
        options.update(kwargs)
        return run_guard_upgrade_job(store, binding, JOB, **options)
    return SimpleNamespace(**locals())


def test_plan_uses_exact_typed_guards_despite_duplicate_names(setup):
    f = setup
    plan = build_guard_upgrade_plan(f.store, f.binding, DISCOVERY, CONTEXT)
    assert [(t.building, t.guard) for t in plan.targets] == [(123, 777), (456, 778)]
    assert plan.initial_ranks == (1, 1) and plan.candidate_buildings == 2
    result = f.begin()
    assert not result["town_coverage_verified"] and not result["maximum_rank_verified"]
    with pytest.raises(GuardFundingCycleStopped, match="existing guard job"):
        f.begin()
    assert not f.calls


@pytest.mark.parametrize("change", ["pid", "creation", "scene", "root", "navigation_scene",
                                      "selected", "type", "membership", "rank", "count",
                                      "unfinished"])
def test_plan_rejects_wrong_or_incomplete_provenance(setup, change):
    f = setup
    detail = f.discovery["roster"][0]["guards"][0]["observation"]
    if change == "pid":
        f.nearby["game_process_id"] += 1
    elif change == "creation":
        f.discovery["game_creation_filetime"] += 1
    elif change in {"scene", "root"}:
        f.nearby[change] += 1
    elif change == "navigation_scene":
        f.discovery["attempts"][0]["expected"] = replace(CONTEXT, scene=2).encode().hex()
    elif change == "selected":
        detail["selected_guard"] = {"object_id": 9999, "object_type": 37}
    elif change == "type":
        f.discovery["roster"][0]["guards"][0]["hireling"] = {"object_id": 777, "object_type": 42}
    elif change == "membership":
        detail["hirelings"] = []
    elif change == "rank":
        detail["hirelings"][0]["rank"] = True
    elif change == "count":
        f.discovery["guards"] += 1
    elif change == "unfinished":
        f.discovery["state"] = "opening"
    f.save()
    with pytest.raises(GuardFundingCycleStopped):
        f.begin()
    assert f.jobs.current() is None and not f.calls


def test_partial_discovery_admits_verified_guards_without_inventing_coverage(setup):
    f = setup
    f.discovery.update(state="partial", guards=1)
    f.discovery["roster"][1] = dict(f.discovery["roster"][1], state="unavailable", guards=[])
    f.save()
    record = f.begin()
    assert len(record["guards"]) == 1
    assert record["plan"]["candidate_buildings"] == 2
    assert record["plan"]["verified_buildings"] == 1
    assert not record["town_coverage_verified"]


def test_no_offer_is_unavailable_not_maximum_or_town_complete(setup):
    f = setup
    f.begin()
    record = f.run()
    assert record["state"] == "unavailable" and record["spent"] == 0
    assert len(f.calls) == 2
    assert not record["maximum_rank_verified"] and not record["town_coverage_verified"]
    f.run()
    assert len(f.calls) == 2


def test_carried_gold_exhaustion_stops_before_later_guards(setup):
    f = setup
    f.begin()

    def runner(*args, **kwargs):
        record = f.result(*args, **kwargs)
        record["state"] = "insufficient"
        _write(f.store.root / "guard-funding-cycles" / (record["operation_id"] + ".json"), record)
        return record
    record = f.run(cycle_runner=runner)
    assert record["state"] == "insufficient" and len(f.calls) == 1
    assert record["spent"] == 0


def test_fair_rank_scheduling_waits_and_raises_minimum_rank(setup):
    f = setup
    f.begin()
    order = []

    def runner(*args, **kwargs):
        record = f.result(*args, **kwargs)
        order.append((record["target"]["guard"], kwargs["minimum_rank"], f.clock[0]))
        if len(order) <= 2:
            record.update(state="started", withdrawn=0, deposited=80, spent=100, quoted_cost=100,
                          initial_rank=1, observed_rank=1, upgrade_in_progress=True)
        _write(f.store.root / "guard-funding-cycles" / (record["operation_id"] + ".json"), record)
        return record
    record = f.run(cycle_runner=runner)
    assert order == [(777, 1, 1000), (778, 1, 1000), (777, 2, 1060), (778, 2, 1060)]
    assert (record["withdrawn"], record["deposited"], record["spent"]) == (0, 160, 200)
    assert record["upgrades_started"] == 2


@pytest.mark.parametrize("mode", ["pause", "stop"])
def test_control_before_run_never_invokes_a_cycle(setup, mode):
    f = setup
    f.begin()
    f.jobs.request(JOB, mode)
    record = f.run()
    assert record["state"] == ("paused" if mode == "pause" else "stopped")
    assert not f.calls
    if mode == "pause":
        f.jobs.request(JOB, "run")
        assert f.run()["state"] == "unavailable"
    else:
        with pytest.raises(GuardFundingCycleStopped):
            f.jobs.request(JOB, "run")


def test_cancellation_while_waiting_leaves_no_pending_cycle(setup):
    f = setup
    f.begin()

    def runner(*args, **kwargs):
        record = f.result(*args, **kwargs)
        record["state"] = "waiting"
        _write(f.store.root / "guard-funding-cycles" / (record["operation_id"] + ".json"), record)
    record = f.run(cycle_runner=runner, cancelled=lambda: f.clock[0] >= 1002)
    assert record["state"] == "stopped" and record["active_cycle"] is None
    assert len(f.calls) == 2


def test_restart_recovers_confirmed_cycle_once_without_replaying(setup):
    f = setup
    f.begin()
    original = f.jobs.read(JOB)
    cycle_id = "operation-" + "c" * 32
    original.update(state="running", active_cycle={"operation_id": cycle_id, "index": 0})
    f.jobs.save(original)
    target = build_guard_upgrade_plan(f.store, f.binding, DISCOVERY, CONTEXT).targets[0]
    result = f.result(f.store, f.binding, SimpleNamespace(operation_id=cycle_id), target,
                      cancelled=lambda: False, minimum_rank=1)
    result.update(state="started", withdrawn=0, deposited=80, spent=100,
                  initial_rank=1, observed_rank=1, quoted_cost=100)
    _write(f.store.root / "guard-funding-cycles" / (cycle_id + ".json"), result)
    record = f.run()
    assert [c["target"]["guard"] for c in f.calls] == [777, 778, 777]
    assert [c["minimum_rank"] for c in f.calls] == [1, 1, 2]
    assert record["spent"] == 100 and record["upgrades_started"] == 1
    assert f.run()["spent"] == 100
    assert len(f.calls) == 3


@pytest.mark.parametrize("state", [None, "running", "review", "cancelled", "foreign"])
def test_interrupted_cycle_blocks_new_job_and_never_replays(setup, state):
    f = setup
    f.begin()
    original = f.jobs.read(JOB)
    cycle_id = "operation-" + "c" * 32
    original.update(state="running", active_cycle={"operation_id": cycle_id, "index": 0})
    f.jobs.save(original)
    if state:
        target = build_guard_upgrade_plan(f.store, f.binding, DISCOVERY, CONTEXT).targets[0]
        result = f.result(f.store, f.binding, SimpleNamespace(operation_id=cycle_id), target,
                          cancelled=lambda: False, minimum_rank=1)
        if state == "foreign":
            result["window"] += 1
        else:
            result["state"] = state
        _write(f.store.root / "guard-funding-cycles" / (cycle_id + ".json"), result)
    before = len(f.calls)
    with pytest.raises((GuardFundingCycleStopped, OSError)):
        f.run()
    assert f.jobs.read(JOB)["state"] == "review" and len(f.calls) == before
    with pytest.raises(GuardFundingCycleStopped, match="existing guard job"):
        f.jobs.begin(f.binding, SimpleNamespace(operation_id="operation-" + "d" * 32),
                     DISCOVERY, CONTEXT)


def test_changed_retained_discovery_cannot_silently_change_saved_plan(setup):
    f = setup
    f.begin()
    f.discovery["roster"][0]["display_name"] = "Edited discovery"
    f.save()
    with pytest.raises(GuardFundingCycleStopped, match="plan or game window"):
        f.run()
    assert not f.calls


def test_wrong_process_at_restart_stops_before_native_activity(setup):
    f = setup
    f.begin()
    f.binding.game_process_started_at_100ns += 1
    with pytest.raises(GuardFundingCycleStopped, match="another client lifetime"):
        f.run()
    assert not f.calls


def test_real_cycles_advance_rank_and_do_not_spend_twice_on_stale_rank(setup):
    f = setup
    f.discovery["roster"] = f.discovery["roster"][:1]
    f.discovery["guards"] = 1
    f.nearby["roster"]["buildings"] = f.nearby["roster"]["buildings"][:1]
    f.save()
    f.begin()
    world = World()

    def sleep(seconds):
        f.clock[0] += seconds
        if f.clock[0] >= 1001:
            # A disappearing progress bar alone is not rank completion.
            world.upgrading = False
    with pytest.raises(GuardFundingCycleStopped, match="expected rank"):
        f.run(cycle_runner=run_guard_funding_cycle, sleep=sleep,
              cycle_options={"session_factory": world.factory, "sleep": lambda _: None})
    record = f.jobs.read(JOB)
    assert record["state"] == "review" and record["spent"] == 100
    assert world.calls.count("upgrade") == 1 and world.calls.count("withdraw") == 0
    GuardSpendingJournal(f.store.root).assert_idle()


def test_real_cycle_lost_deposit_blocks_later_guards(setup):
    f = setup
    f.begin()
    world = World()
    world.fail = "deposit"
    with pytest.raises(TimeoutError, match="deposit"):
        f.run(cycle_runner=run_guard_funding_cycle,
              cycle_options={"session_factory": world.factory, "sleep": lambda _: None})
    record = f.jobs.read(JOB)
    assert record["state"] == "review" and record["active_cycle"]["index"] == 0
    assert world.calls.count("deposit") == 1 and "upgrade" not in world.calls
    before = copy.copy(world.calls)
    f.run()
    assert world.calls == before


def test_real_cycles_keep_upgrading_after_observed_rank_completion(setup):
    f = setup
    f.discovery["roster"] = f.discovery["roster"][:1]
    f.discovery["guards"] = 1
    f.nearby["roster"]["buildings"] = f.nearby["roster"]["buildings"][:1]
    f.save()
    f.begin()
    world = World()
    world.purse = 180

    def sleep(seconds):
        f.clock[0] += seconds
        if world.upgrading:
            world.rank += 1
            world.upgrading = False
            world.offer = world.rank < 3
    record = f.run(cycle_runner=run_guard_funding_cycle, sleep=sleep,
                   cycle_options={"session_factory": world.factory, "sleep": lambda _: None})
    assert record["state"] == "unavailable" and record["upgrades_started"] == 2
    assert record["guards"][0]["observed_rank"] == 3
    assert record["spent"] == 200 and world.gold == 1000 and world.purse == world.funds == 0
    assert world.calls.count("upgrade") == 2 and world.calls.count("withdraw") == 0
    assert not record["maximum_rank_verified"]


def test_pause_after_cycle_then_resume_retains_confirmed_accounting(setup):
    f = setup
    f.begin()

    def runner(*args, **kwargs):
        f.result(*args, **kwargs)
        f.jobs.request(JOB, "pause")
    assert f.run(cycle_runner=runner)["state"] == "paused"
    assert len(f.calls) == 1
    f.jobs.request(JOB, "run")
    assert f.run()["state"] == "unavailable"
    assert [c["target"]["guard"] for c in f.calls] == [777, 778]


@pytest.mark.parametrize("change", ["legacy_schema", "funding_source"])
def test_legacy_or_changed_funding_policy_never_resumes_spending(setup, change):
    f = setup
    record = f.begin()
    if change == "legacy_schema":
        record["schema_version"] = 1
        record.pop("funding_source")
    else:
        record["funding_source"] = "warehouse"
    f.jobs.save(record)
    assert f.jobs.current()["job_id"] == JOB
    with pytest.raises(GuardFundingCycleStopped, match="needs review"):
        f.run()
    assert not f.calls and f.jobs.read(JOB)["state"] == "review"
