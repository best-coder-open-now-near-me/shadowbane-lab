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
    owner = dict(player_pointer=123456, character_name="poley", server_name="Wonderbane")
    def owner_reader(_):
        return dict(owner)
    jobs, clock, calls = GuardJobStore(store, owner_reader=owner_reader), [1000.0], []

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
        options = dict(owner_reader=owner_reader, cancelled=lambda: False, cycle_runner=result,
                       clock=lambda: clock[0],
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


AREA = "operation-" + "e" * 32


def travel_scan(f, *, known=(777,), new=True, context=CONTEXT):
    """A fresh owned roster includes one remembered guard and a new tower."""
    nearby, discovery = copy.deepcopy(f.nearby), copy.deepcopy(f.discovery)
    nearby["operation_id"] = discovery["operation_id"] = AREA
    nearby.update(scene=context.scene, root=context.root)
    discovery["attempts"] = [{"expected": context.encode().hex()}]
    discovery["roster"] = [b for b in discovery["roster"]
                            if b["guards"][0]["hireling"]["object_id"] in known]
    for b in discovery["roster"]:
        b["state"] = "partial"
        b["guards"][0].update(state="remembered", window_verified=False)
        b["guards"][0].pop("observation")
    if new:
        b = copy.deepcopy(f.discovery["roster"][1])
        b["building"]["object_id"] = 789
        b["guards"][0]["hireling"]["object_id"] = 779
        discovery["roster"].append(b)
    nearby["roster"]["buildings"] = [{"building": b["building"]}
                                      for b in discovery["roster"]]
    discovery.update(state="partial", guards=int(new))
    for folder, value in (("guard-discovery", nearby), ("guard-navigation", discovery)):
        _write(f.store.root / folder / (AREA + ".json"), value)


def test_travel_finishes_active_transaction_before_safe_to_move(setup):
    f = setup
    f.begin()

    def runner(*args, **kwargs):
        f.jobs.request(JOB, "travel")
        assert not kwargs["cancelled"]()
        assert f.jobs.read(JOB)["state"] == "running"
        result = f.result(*args, **kwargs)
        result.update(state="started", spent=100, deposited=80, quoted_cost=100)
        _write(f.store.root / "guard-funding-cycles" / (result["operation_id"] + ".json"), result)
    record = f.run(cycle_runner=runner)
    assert record["state"] == "travel" and record["active_cycle"] is None
    assert record["spent"] == 100 and record["guards"][0]["minimum_rank"] == 2
    assert len(f.calls) == 1


def test_continue_merges_new_guards_preserves_progress_and_prioritizes_new(setup):
    f = setup
    record = f.begin()
    record["guards"][0].update(state="waiting", minimum_rank=2, observed_rank=1,
                               next_check_at=900, upgrades_started=1)
    record.update(spent=100, deposited=80, upgrades_started=1)
    f.jobs.save(record)
    f.jobs.request(JOB, "travel")
    before = f.jobs.read(JOB)["guards"]
    travel_scan(f)
    merged = f.jobs.continue_here(f.binding, JOB, AREA, CONTEXT)
    assert merged["guards"][:2] == before
    assert merged["area_indices"] == [0, 2]  # Out-of-area guard 778 remains remembered.
    assert merged["spent"] == 100 and merged["upgrades_started"] == 1
    result = f.run()
    assert [c["target"]["guard"] for c in f.calls] == [779, 777]
    assert f.calls[1]["minimum_rank"] == 2
    assert result["state"] == "travel" and result["spent"] == 100
    assert len(result["guards"]) == 3


def test_return_to_known_area_preserves_timer_without_any_guard_cycle(setup):
    f = setup
    record = f.begin()
    record["guards"][0].update(state="waiting", next_check_at=2000)
    f.jobs.save(record)
    f.jobs.request(JOB, "travel")
    travel_scan(f, new=False)
    f.jobs.continue_here(f.binding, JOB, AREA, CONTEXT)
    result = f.run(cancelled=lambda: f.clock[0] >= 1002)
    assert not f.calls
    assert result["guards"][0]["next_check_at"] == 2000
    assert len(result["guards"]) == 2


@pytest.mark.parametrize("change", ["scene", "duplicate", "foreign_remembered", "running"])
def test_continue_rejects_invalid_area_without_changing_progress(setup, change):
    f = setup
    f.begin()
    f.jobs.request(JOB, "travel")
    travel_scan(f)
    context = CONTEXT
    if change == "scene":
        context = replace(CONTEXT, scene=2)
    elif change == "running":
        f.jobs.request(JOB, "run")
    else:
        path = f.store.root / "guard-navigation" / (AREA + ".json")
        import json
        value = json.loads(path.read_text())
        if change == "foreign_remembered":
            value["roster"][0]["guards"][0]["hireling"]["object_id"] = 999
            value["roster"][0]["roster"]["hirelings"][0]["hireling"]["object_id"] = 999
        else:
            value["roster"][0] = f.discovery["roster"][0]
            value["guards"] += 1
        _write(path, value)
    before = f.jobs.read(JOB)
    with pytest.raises(GuardFundingCycleStopped):
        f.jobs.continue_here(f.binding, JOB, AREA, context)
    assert f.jobs.read(JOB) == before
    assert not f.calls


def test_travel_never_clears_an_interrupted_cycle(setup):
    f = setup
    record = f.begin()
    record["active_cycle"] = {"operation_id": DISCOVERY, "index": 0}
    f.jobs.save(record)
    f.jobs.request(JOB, "travel")
    assert f.jobs.read(JOB)["state"] == "review"
    assert f.jobs.read(JOB)["active_cycle"] == record["active_cycle"]


def test_movement_epoch_change_preserves_history_and_uses_fresh_area_on_restart(setup):
    f = setup
    f.begin()
    before = f.jobs.read(JOB)
    f.jobs.request(JOB, "travel")
    moved = replace(CONTEXT, scene=14)
    travel_scan(f, context=moved)
    merged = f.jobs.continue_here(f.binding, JOB, AREA, moved)
    assert merged["plan"] == before["plan"]
    assert merged["guards"][:2] == before["guards"]
    assert merged["area_indices"] == [0, 2]
    f.run()  # New runner reconstructs eligibility and context from durable evidence.
    assert [c["target"]["scene"] for c in f.calls] == [14, 14]
    assert {c["target"]["guard"] for c in f.calls} == {777, 779}
    assert f.jobs.read(JOB)["plan"] == before["plan"]


@pytest.mark.parametrize("field", ["player_pointer", "character_name", "server_name"])
def test_changed_character_cannot_scan_or_spend(setup, field):
    f = setup
    f.begin()
    f.jobs.request(JOB, "travel")
    f.owner[field] = 999 if field == "player_pointer" else "another"
    before = f.jobs.read(JOB)
    with pytest.raises(GuardFundingCycleStopped, match="character changed"):
        f.jobs.remembered(f.binding, JOB, replace(CONTEXT, scene=14))
    assert f.jobs.read(JOB) == before
    f.jobs.request(JOB, "run")
    with pytest.raises(GuardFundingCycleStopped, match="character changed"):
        f.run()
    assert not f.calls


@pytest.mark.parametrize("field", ["root", "manager"])
def test_travel_rejects_changed_window_owner(setup, field):
    f = setup
    f.begin()
    f.jobs.request(JOB, "travel")
    with pytest.raises(GuardFundingCycleStopped, match="root or manager"):
        f.jobs.remembered(f.binding, JOB, replace(CONTEXT, **{field: 999}))


def test_unseen_guard_cannot_be_inserted_into_active_area(setup):
    f = setup
    f.begin()
    f.jobs.request(JOB, "travel")
    moved = replace(CONTEXT, scene=14)
    travel_scan(f, context=moved)
    record = f.jobs.continue_here(f.binding, JOB, AREA, moved)
    record["area_indices"] = [0, 1, 2]
    f.jobs.save(record)
    with pytest.raises(GuardFundingCycleStopped, match="owned roster"):
        f.run()
    assert not f.calls


def test_legacy_unspent_travel_adopts_owner_without_changing_any_progress(setup):
    f = setup
    record = f.begin()
    del record["owner"]
    f.jobs.save(record)
    f.jobs.request(JOB, "travel")
    before = f.jobs.read(JOB)
    f.jobs.pin_unspent_owner(f.binding, JOB, replace(CONTEXT, scene=14))
    after = f.jobs.read(JOB)
    assert after.pop("owner") == f.owner
    assert after.pop("owner_adoption") == "idle_unspent_fresh_roster_required"
    assert after == before
    assert not f.calls


@pytest.mark.parametrize("change", ["spent", "deposited", "withdrawn", "upgrades_started",
                                     "active", "journal", "running"])
def test_legacy_ownership_cannot_adopt_paid_or_unresolved_work(setup, change):
    f = setup
    record = f.begin()
    del record["owner"]
    record["state"] = "travel"
    if change in {"spent", "deposited", "withdrawn", "upgrades_started"}:
        record[change] = 1
    elif change == "active":
        record["active_cycle"] = {"operation_id": DISCOVERY, "index": 0}
    elif change == "running":
        record["state"] = "running"
    f.jobs.save(record)
    _write(f.jobs.root / (JOB + ".control.json"), {"mode": "travel"})
    if change == "journal":
        from unittest.mock import patch
        with patch.object(GuardSpendingJournal, "assert_idle", side_effect=RuntimeError("pending")):
            with pytest.raises(RuntimeError, match="pending"):
                f.jobs.pin_unspent_owner(f.binding, JOB, CONTEXT)
    else:
        with pytest.raises(GuardFundingCycleStopped, match="needs review"):
            f.jobs.pin_unspent_owner(f.binding, JOB, CONTEXT)
    assert "owner" not in f.jobs.read(JOB) and not f.calls


def test_migrated_legacy_job_requires_fresh_roster_before_any_cycle(setup):
    f = setup
    record = f.begin()
    del record["owner"]
    f.jobs.save(record)
    f.jobs.request(JOB, "travel")
    f.jobs.pin_unspent_owner(f.binding, JOB, CONTEXT)
    f.jobs.request(JOB, "run")
    with pytest.raises(GuardFundingCycleStopped, match="fresh area"):
        f.run()
    assert not f.calls


def test_fresh_area_confirmed_cycle_is_accounted_once_after_restart(setup):
    f = setup
    f.begin()
    f.jobs.request(JOB, "travel")
    moved = replace(CONTEXT, scene=14)
    travel_scan(f, context=moved)
    record = f.jobs.continue_here(f.binding, JOB, AREA, moved)
    cycle_id = "operation-" + "f" * 32
    record.update(state="running", active_cycle={"operation_id": cycle_id, "index": 0})
    f.jobs.save(record)
    target = replace(build_guard_upgrade_plan(
        f.store, f.binding, DISCOVERY, CONTEXT).targets[0], scene=14)
    cycle = f.result(f.store, f.binding, SimpleNamespace(operation_id=cycle_id), target,
                     cancelled=lambda: False, minimum_rank=1)
    cycle.update(state="started", spent=100, quoted_cost=100, deposited=80, observed_rank=1)
    _write(f.store.root / "guard-funding-cycles" / (cycle_id + ".json"), cycle)
    _write(f.jobs.root / (JOB + ".control.json"), {"mode": "travel"})
    first = f.run()
    second = f.run()
    assert first["spent"] == second["spent"] == 100
    assert first["upgrades_started"] == second["upgrades_started"] == 1
    assert len(f.calls) == 1
    assert f.jobs.read(JOB)["plan"]["targets"][0]["scene"] == 1
