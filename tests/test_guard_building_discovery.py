import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_navigation_wire import IN_FLIGHT, UNRESOLVED, Outcome
from shadowbane_lab.manager.guard_discovery import read_guard_roster, run_guard_building_discovery
from shadowbane_lab.manager.vendor_job import VendorJobStore
from tests.test_vendor_building_discovery import Session


class GuardSession(Session):
    def open_guard(self, state, building, guard, key):
        result = super()._open(state, building, guard, key)
        if self.state.vendor_id:
            self.state = replace(self.state, vendor_type=37)
        return result

    def open_vendor(self, *args):
        raise AssertionError("guard traversal must never select a crafting vendor")

    def open_building(self, *args):
        result = super().open_building(*args)
        if result.outcome in (Outcome.UNAVAILABLE, Outcome.STALE):
            return replace(result, flags=0)
        return result


@pytest.fixture
def setup(tmp_path):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    binding = SimpleNamespace(game_process_id=988, game_process_started_at_100ns=123)
    operation = SimpleNamespace(operation_id="operation-" + "b" * 32)
    path = store.root / "guard-navigation" / (operation.operation_id + ".json")
    session = GuardSession(path)
    nearby = {
        "state": "complete", "identity": list(store.identity), "scene": 1, "root": 100,
        "game_process_id": 988, "game_creation_filetime": 123,
        "roster": {"buildings": [
            {"building": {"object_id": key, "object_type": 8}, "display_name": "Same tower name"}
            for key in (123, 456)
        ]},
    }
    tick = [0]

    def clock():
        tick[0] += 1
        return tick[0]

    def reader(binding, *, window):
        assert window in ("building", "guard")
        building = session.state.building_id
        rows = [] if session.mode == "empty" else [{
            "hireling": {"object_id": building * 10, "object_type": 37},
            "display_name": "Archer", "service_label": "Wall Archer",
            "qualified_guard_type": True, "rank": 1,
        }]
        result = {
            "process_id": binding.game_process_id,
            "process_creation_filetime_utc": binding.game_process_started_at_100ns,
            "building": {"object_id": building, "object_type": 8},
            "hirelings": rows, "building_roster_verified": True,
            "hireling_slots": 1, "vacant_hireling_slots": 1 - len(rows),
        }
        if window == "guard":
            result.update(
                selected_guard=rows[0]["hireling"], upgrade_cost_gold=100,
                upgrade_in_progress=False, can_upgrade=True,
            )
        return result

    def run(**overrides):
        kwargs = dict(cancelled=lambda: False, reader=reader, clock=clock, sleep=lambda _: None)
        kwargs.update(overrides)
        return run_guard_building_discovery(store, binding, operation, session, nearby, **kwargs)

    return SimpleNamespace(
        store=store, binding=binding, operation=operation, path=path,
        session=session, nearby=nearby, reader=reader, run=run,
    )


def test_typed_guard_traversal_verifies_duplicate_named_buildings_and_retains_quotes(setup):
    f = setup
    f.store.root.mkdir(parents=True)
    old = f.store.root / "nearby-summary.json"
    old.write_text('{"untouched":"vendor"}')
    result = f.run()
    assert result["state"] == "complete" and result["guards"] == 2
    assert result["candidate_buildings_verified"]
    assert not result["roster_complete"] and not result["town_membership_verified"]
    assert [(b, g) for b, g, _ in f.session.calls] == [(123, 0), (123, 1230), (456, 0), (456, 4560)]
    assert all(a["state"] == "observed" and "guard_id" in a for a in result["attempts"])
    assert result["roster"][0]["guards"][0]["observation"]["upgrade_cost_gold"] == 100
    assert old.read_text() == '{"untouched":"vendor"}'
    with pytest.raises(VendorBatchStopped, match="already attempted"):
        f.run()
    assert len(f.session.calls) == 4


def test_all_vacant_requires_complete_slot_observation_and_can_complete_candidate_pass(setup):
    setup.session.mode = "empty"
    result = setup.run()
    assert result["guards"] == 0 and result["buildings_verified"] == 2
    assert result["state"] == "complete" and result["candidate_buildings_verified"]
    assert not result["roster_complete"]
    assert len(setup.session.calls) == 2


def test_unknown_hirelings_retained_without_guard_selection(setup):
    def reader(binding, *, window):
        result = setup.reader(binding, window=window)
        result["hirelings"][0]["hireling"]["object_type"] = 99
        result["hirelings"][0]["qualified_guard_type"] = False
        return result
    result = setup.run(reader=reader)
    assert result["guards"] == 0
    assert result["roster"][0]["roster"]["hirelings"][0]["hireling"]["object_type"] == 99
    assert len(setup.session.calls) == 2


def test_inaccessible_building_is_partial_coverage_not_complete(setup):
    setup.session.mode = "unavailable"
    result = setup.run()
    assert result["state"] == "partial" and result["guards"] == 1
    assert not result["candidate_buildings_verified"]
    assert result["roster"][0]["state"] == "unavailable"


@pytest.mark.parametrize("mode", ["uncertain", "exception", "pending", "scene", "stale"])
def test_ambiguous_transition_stops_without_retry(setup, mode):
    setup.session.mode = mode
    with pytest.raises((VendorBatchStopped, OSError)):
        setup.run()
    assert len(setup.session.calls) == 1
    assert json.loads(setup.path.read_text())["state"] == "review"
    with pytest.raises(VendorBatchStopped, match="already attempted"):
        setup.run()
    assert len(setup.session.calls) == 1


@pytest.mark.parametrize("change", ["process", "building", "counts", "incomplete", "selected"])
def test_wrong_or_partial_guard_observation_cannot_advance(setup, change):
    def reader(binding, *, window):
        result = setup.reader(binding, window=window)
        if change == "process":
            result["process_id"] += 1
        elif change == "building":
            result["building"]["object_id"] += 1
        elif change == "counts":
            result["hireling_slots"] += 1
        elif change == "incomplete":
            result["building_roster_verified"] = False
        elif window == "guard":
            result["selected_guard"] = {"object_id": 999, "object_type": 37}
        return result
    with pytest.raises(VendorBatchStopped, match="roster"):
        setup.run(reader=reader)
    assert len(setup.session.calls) == (2 if change == "selected" else 1)


@pytest.mark.parametrize("flags", [IN_FLIGHT, UNRESOLVED])
def test_unavailable_with_pending_or_unresolved_flags_cannot_skip(setup, flags):
    original = setup.session.open_building
    setup.session.mode = "unavailable"
    setup.session.open_building = lambda *args: replace(original(*args), flags=flags)
    with pytest.raises(VendorBatchStopped):
        setup.run()
    assert len(setup.session.calls) == 1


def test_cancellation_after_durable_intent_sends_nothing(setup):
    def cancel():
        return setup.path.exists() and bool(json.loads(setup.path.read_text())["attempts"])
    with pytest.raises(VendorBatchStopped, match="cancelled"):
        setup.run(cancelled=cancel)
    assert not setup.session.calls
    assert json.loads(setup.path.read_text())["state"] == "cancelled"


def test_foreign_process_and_prior_unresolved_do_not_open(setup):
    setup.nearby["game_creation_filetime"] += 1
    with pytest.raises(VendorBatchStopped, match="another client"):
        setup.run()
    assert not setup.session.calls
    setup.nearby["game_creation_filetime"] -= 1
    setup.session.mode = "unresolved"
    with pytest.raises(VendorBatchStopped, match="previous window request"):
        setup.run()
    assert not setup.session.calls


@pytest.mark.parametrize("window", ["building", "guard"])
@pytest.mark.parametrize("fails", [False, True])
def test_read_adapter_closes_exact_client_memory(window, fails):
    memory = Mock()
    target = (
        "read_native_building_hirelings" if window == "building" else "read_native_guard_upgrade"
    )
    with patch("shadowbane_lab.manager.guard_discovery._memory", return_value=memory), patch(
        "shadowbane_lab.manager.guard_discovery." + target,
        side_effect=ValueError("changed") if fails else None, return_value={"ok": True},
    ) as reader:
        if fails:
            with pytest.raises(ValueError):
                read_guard_roster(object(), window=window)
        else:
            assert read_guard_roster(object(), window=window) == {"ok": True}
    reader.assert_called_once_with(memory)
    memory.close.assert_called_once_with()


@pytest.mark.parametrize("value", [None, 2])
def test_city_to_building_scene_change_does_not_open(setup, value):
    setup.nearby["scene"] = value
    with pytest.raises(VendorBatchStopped, match="scene"):
        setup.run()
    assert not setup.session.calls


def test_membership_change_after_guard_selection_stops(setup):
    # A replacement non-guard row must not quietly change the building roster.
    def reader(binding, *, window):
        result = setup.reader(binding, window=window)
        if window == "guard":
            result["hirelings"].append({
                "hireling": {"object_id": 9999, "object_type": 99},
            })
            setup.session.state = replace(setup.session.state, occupied=2, capacity=2)
            result["hireling_slots"] = 2
        return result
    with pytest.raises(VendorBatchStopped, match="roster changed"):
        setup.run(reader=reader)
    assert len(setup.session.calls) == 2


@pytest.mark.parametrize("failure", [None, "city", "navigation"])
def test_two_stage_discovery_holds_one_producer_and_closes_on_failure(setup, failure):
    from shadowbane_lab.manager.guard_discovery import run_guard_discovery
    from tests.test_city_window import OPENED, receipt

    f = setup
    city = Mock()
    city.closed = False
    city.close.side_effect = lambda: setattr(city, "closed", True)
    city.inspect.side_effect = [
        receipt(), receipt(replace(OPENED, building_count=2)),
        receipt(replace(OPENED, building_count=2)),
    ]
    city.open.return_value = receipt(outcome=Outcome.SUBMITTED, flags=0)
    if failure == "city":
        city.open.side_effect = OSError("lost city response")
    if failure == "navigation":
        f.session.mode = "exception"
    f.session.close = Mock()
    factories = []

    def navigation(binding):
        assert city.closed  # The previous producer lease must have been released.
        factories.append(binding)
        return f.session

    candidates = dict(f.nearby["roster"], process_id=988, process_creation_filetime_utc=123)
    for building in candidates["buildings"]:
        building["hirelings"] = []  # Cache need not list guards to visit a building.
    kwargs = dict(
        cancelled=lambda: False, city_session_factory=lambda binding: city,
        navigation_session_factory=navigation, candidate_reader=lambda binding: candidates,
        roster_reader=f.reader, sleep=lambda _: None,
    )
    if failure:
        with pytest.raises(OSError):
            run_guard_discovery(f.store, f.binding, f.operation, **kwargs)
    else:
        result = run_guard_discovery(f.store, f.binding, f.operation, **kwargs)
        assert result["state"] == "complete" and result["guards"] == 2
    city.close.assert_called_once_with()
    if failure == "city":
        assert factories == []
        f.session.close.assert_not_called()
    else:
        f.session.close.assert_called_once_with()
    path = f.store.root / "guard-discovery" / (f.operation.operation_id + ".json")
    saved = json.loads(path.read_text())
    assert saved["expected"] and saved["scene"] == 1 and saved["root"] == 100
    assert saved["state"] == ("review" if failure == "city" else "complete")
    calls = len(f.session.calls)
    with pytest.raises(VendorBatchStopped, match="already attempted"):
        run_guard_discovery(f.store, f.binding, f.operation, **kwargs)
    assert len(f.session.calls) == calls
