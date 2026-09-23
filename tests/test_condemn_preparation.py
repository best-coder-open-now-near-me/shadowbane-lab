from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.city_window_wire import Outcome, Snapshot
from shadowbane_lab.client_extension.vendor_navigation_wire import Snapshot as NavigationSnapshot
from shadowbane_lab.client_observation.native_city_registry import read_native_city_registry
from shadowbane_lab.manager import condemn_preparation as module
from shadowbane_lab.manager.condemn_plan import CondemnPlanStore
from shadowbane_lab.manager.vendor_job import VendorJobStore
from tests.test_condemn_cycle import OWNER
from tests.test_condemn_plan import nearby
from tests.test_condemn_transaction import BEFORE, LIFE
from tests.test_guard_building_discovery import GuardSession
from tests.test_native_city_registry import fixture as registry_memory


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    binding = SimpleNamespace(
        game_process_id=LIFE.process_id,
        game_process_started_at_100ns=LIFE.creation,
        game_window_handle=1000,
    )
    operation = SimpleNamespace(operation_id="operation-" + "a" * 32)
    roster = nearby(store)
    state = Snapshot(
        scene=LIFE.scene_epoch,
        revision=1,
        root=BEFORE.root,
        manager=200,
        hud=300,
        active_manager=200,
        mode=1,
        building_count=2,
        visible=1,
    )
    session = Mock(
        identity=NativeClientProcessIdentity(LIFE.process_id, LIFE.creation), window=1000
    )
    session.inspect.return_value = SimpleNamespace(outcome=Outcome.OBSERVED, snapshot=state)
    catalog = read_native_city_registry(registry_memory())
    values = [deepcopy((OWNER, LIFE.local, catalog)) for _ in range(3)]
    monkeypatch.setattr(module, "_run_discovery", lambda *args, **kwargs: roster)

    navigation = GuardSession(store.root / "guard-navigation" / (operation.operation_id + ".json"))
    navigation.state = NavigationSnapshot(LIFE.scene_epoch, 1, BEFORE.root, 200)
    navigation.identity, navigation.window = session.identity, session.window
    navigation.close = Mock()

    def navigation_factory(_):
        session.close.assert_called_once_with()
        return navigation

    def reader(binding, *, window):
        assert window == "building"  # Condemn does not open rank-up menus.
        building = navigation.state.building_id
        rows = deepcopy(roster["roster"]["buildings"][0 if building == 100 else 1]["hirelings"])
        # Model a cold cached roster: the response still contains a guard.
        if not rows:
            rows = [dict(hireling=dict(object_id=building * 3, object_type=37))]
        return dict(process_id=LIFE.process_id, process_creation_filetime_utc=LIFE.creation,
                    building=dict(object_id=building, object_type=8), hirelings=rows,
                    building_roster_verified=True, hireling_slots=1, vacant_hireling_slots=0)

    def run(**changes):
        return module.prepare_condemn(
            store,
            binding,
            operation,
            cancelled=lambda: False,
            session_factory=lambda _: session,
            catalog_reader=lambda _: values.pop(0),
            navigation_session_factory=navigation_factory, roster_reader=reader,
            owner_reader=lambda _: OWNER,
            **changes,
        )

    return SimpleNamespace(
        store=store,
        session=session,
        run=run,
        values=values,
        state=state,
        operation=operation,
        roster=roster,
        navigation=navigation,
    )


def test_preparation_pins_catalog_and_nearby_source_without_hostility_actions(setup):
    result = setup.run()
    assert len(result["catalog"]["entries"]) == 3
    assert len(result["buildings"]) == 1
    assert setup.session.inspect.call_count == 2
    setup.session.close.assert_called_once_with()
    setup.navigation.close.assert_called_once_with()
    assert [g for _, g, _ in setup.navigation.calls] == [0, 0]
    assert not (setup.store.root / "condemn-cycles").exists()
    assert CondemnPlanStore(setup.store).current() == result


@pytest.mark.parametrize("case", ["window", "character", "local", "scene", "changing"])
def test_foreign_or_changing_capture_does_not_publish_preparation(setup, case):
    from dataclasses import replace

    if case == "window":
        setup.session.window = 99
    elif case == "character":
        setup.values[1][0]["character_name"] = "Other"
    elif case == "local":
        owner, _, catalog = setup.values[1]
        setup.values[1] = owner, (21, 53), catalog
    elif case == "scene":
        setup.session.inspect.return_value.snapshot = replace(setup.state, scene=99)
    else:
        setup.session.inspect.side_effect = [
            SimpleNamespace(outcome=Outcome.OBSERVED, snapshot=setup.state),
            SimpleNamespace(outcome=Outcome.OBSERVED, snapshot=replace(setup.state, revision=2)),
        ]
    with pytest.raises(RuntimeError):
        setup.run()
    assert CondemnPlanStore(setup.store).current() is None
    setup.session.close.assert_called_once_with()


def test_cold_cache_discovers_guards_from_building_responses(setup):
    for row in setup.roster["roster"]["buildings"]:
        row["hirelings"] = []
    setup.roster["hirelings"] = 0
    result = setup.run()
    assert len(result["buildings"]) == 2
    saved = CondemnPlanStore(setup.store).read(setup.operation.operation_id)
    assert saved["schema_version"] == 2 and saved["nearby"]["hirelings"] == 0
    assert saved["verified_rosters"]["guards_observed"] == 2
    assert saved["verified_rosters"]["guards"] == 0


@pytest.mark.parametrize("case", ["identity", "scene", "character", "local", "lost_response"])
def test_roster_stage_failure_does_not_publish_or_reopen(setup, case):
    if case == "identity":
        setup.navigation.window = 99
    elif case == "scene":
        setup.navigation.state = replace(setup.navigation.state, scene=99)
    elif case == "character":
        setup.values[2][0]["character_name"] = "Other"
    elif case == "local":
        owner, _, catalog = setup.values[2]
        setup.values[2] = owner, (21, 53), catalog
    else:
        setup.navigation.mode = "exception"
    with pytest.raises((RuntimeError, OSError)):
        setup.run()
    assert CondemnPlanStore(setup.store).current() is None
    setup.navigation.close.assert_called_once_with()
    if case == "lost_response":
        assert len(setup.navigation.calls) == 1


@pytest.mark.parametrize("case", ["scene", "process", "building", "count", "attempt", "guard"])
def test_prepared_roster_evidence_cannot_be_rebound(setup, case):
    from shadowbane_lab.manager.vendor_job import _write

    setup.run()
    plans = CondemnPlanStore(setup.store)
    record = plans.read(setup.operation.operation_id)
    evidence = record["verified_rosters"]
    if case == "scene":
        evidence["scene"] += 1
    elif case == "process":
        evidence["roster"][0]["roster"]["process_id"] += 1
    elif case == "building":
        evidence["roster"][0]["building"]["object_id"] += 1
    elif case == "count":
        evidence["roster"][0]["roster"]["hireling_slots"] += 1
    elif case == "attempt":
        evidence["attempts"][0]["state"] = "not_submitted"
    else:
        evidence["roster"][0]["guards"] = []
    _write(plans.path(setup.operation.operation_id), record)
    with pytest.raises(ValueError):
        plans.current()


def test_coverage_keeps_verified_no_guard_buildings_and_exact_candidate_identities(setup):
    result = setup.run()
    coverage = result["coverage"]
    assert coverage["candidate_buildings"] == 2
    assert coverage["verified_guard_buildings"] == 1
    assert coverage["verified_no_guard_buildings"] == 1
    assert coverage["unavailable_buildings"] == coverage["unverified_buildings"] == 0
    assert [(r["building"], r["state"], r["guards"]) for r in coverage["buildings"]] == [
        ([100, 8], "verified_guards", 1), ([200, 8], "verified_no_guards", 0),
    ]
    assert not coverage["town_coverage_verified"]


def test_all_unavailable_pass_publishes_exceptions_without_any_selectable_guard(setup):
    setup.navigation.mode = "all_unavailable"
    for row in setup.roster["roster"]["buildings"]:
        row["display_name"] = "Irekei Barracks"
        row["hirelings"] = []
    setup.roster["hirelings"] = 0
    result = setup.run()
    assert result["buildings"] == []
    coverage = result["coverage"]
    assert coverage["candidate_buildings"] == coverage["unavailable_buildings"] == 2
    assert coverage["verified_no_guard_buildings"] == coverage["verified_guard_buildings"] == 0
    assert {tuple(r["building"]) for r in coverage["buildings"]} == {(100, 8), (200, 8)}
    assert all(r["guards"] is None and "no action was submitted" in r["detail"]
               for r in coverage["buildings"])
    plans = CondemnPlanStore(setup.store)
    before = plans.path(result["preparation_id"]).read_bytes()
    assert CondemnPlanStore(setup.store).current() == result
    with pytest.raises(ValueError, match="observed crests and guard buildings"):
        plans.select(result["preparation_id"], result["sha256"], ["5:20"], [100])
    assert plans.path(result["preparation_id"]).read_bytes() == before
    assert not (setup.store.root / "condemn-cycles").exists()
