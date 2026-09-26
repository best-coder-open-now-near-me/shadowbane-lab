import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_navigation_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    Host,
    Outcome,
    Receipt,
    Snapshot,
)
from shadowbane_lab.manager.vendor_job import VendorJobStore
from shadowbane_lab.manager.vendor_navigation import run_building_discovery

REQUEST = "01000000-0000-0000-0000-000000000000"


class Session:
    def __init__(self, path):
        self.path = path
        self.state = Snapshot(1, 1, 100, 200)
        self.transition = None
        self.calls = []
        self.mode = ""
        self.focus_wait = False

    def renew_lease(self):
        pass

    def inspect(self):
        flags = IN_FLIGHT if self.mode == "pending" and self.calls else READY
        if self.mode == "unresolved":
            flags = UNRESOLVED | IN_FLIGHT
        if self.focus_wait:
            self.focus_wait = False
            flags = 0
        return Receipt(
            REQUEST, Host(1, 1, 1), 1000, Outcome.OBSERVED, flags, self.state, self.transition
        )

    def open_building(self, state, building, key):
        return self._open(state, building, 0, key)

    def open_vendor(self, state, building, vendor, key):
        return self._open(state, building, vendor, key)

    def _open(self, state, building, vendor, key):
        journal = json.loads(self.path.read_text(encoding="utf-8"))
        intent = journal["attempts"][-1]
        assert intent["request_key"] == key and intent["state"] == "prepared"
        assert intent["expected"] == state.encode().hex()
        assert state == self.state
        self.calls.append((building, vendor, key))
        if self.mode == "exception":
            raise OSError("interrupted native call")
        outcome = Outcome.SUBMITTED
        if self.mode == "stale":
            outcome = Outcome.STALE
        elif self.mode == "all_unavailable" or self.mode == "unavailable" and building == 123:
            outcome = Outcome.UNAVAILABLE
        elif self.mode == "uncertain":
            outcome = Outcome.UNCERTAIN
        else:
            self.state = replace(
                self.state,
                revision=self.state.revision + 1,
                front_hud=500 if vendor else 300,
                mode=6,
                building_hud=300,
                initialized=1,
                building_id=building,
                building_type=8,
                capacity=1,
                occupied=1,
                selected_entry=(
                    400 if vendor else (350 if self.mode in {"vacancy", "secondary"} else 0)
                ),
                vendor_id=vendor,
                vendor_type=42 if vendor else 0,
                vendor_hud=500 if vendor else 0,
                visible=3 if vendor else 1,
            )
            if self.mode == "scene":
                self.state = replace(self.state, scene=2)
            if self.mode == "empty":
                self.state = replace(self.state, occupied=0)
        self.transition = key
        return Receipt(key, Host(1, 1, 1), 1000, outcome, IN_FLIGHT, state, key)


@pytest.fixture
def fixture(tmp_path):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    binding = SimpleNamespace(game_process_id=988, game_process_started_at_100ns=123)
    operation = SimpleNamespace(operation_id="operation-" + "a" * 32)
    path = store.root / "navigation" / (operation.operation_id + ".json")
    session = Session(path)
    nearby = {
        "state": "complete",
        "scene": 1, "root": 100,
        "identity": list(store.identity),
        "game_process_id": 988,
        "game_creation_filetime": 123,
        "roster": {
            "buildings": [
                {
                    "building": {"object_id": key, "object_type": 8},
                    "display_name": f"Building {key}",
                }
                for key in (123, 456)
            ]
        },
    }
    tick = [0]

    def clock():
        tick[0] += 1
        return tick[0]

    def reader(binding, *, window):
        assert window in ("building", "vendor")
        building = session.state.building_id
        return {
            "process_id": binding.game_process_id,
            "process_creation_filetime_utc": binding.game_process_started_at_100ns,
            "building": {"object_id": building, "object_type": 8},
            "vendors": [
                {
                    "vendor": {"object_id": building * 10, "object_type": 42},
                    "display_name": "Sage",
                    "service_label": "Magic",
                }
            ],
        }

    def run(**overrides):
        kwargs = dict(cancelled=lambda: False, reader=reader, clock=clock, sleep=lambda _: None)
        kwargs.update(overrides)
        return run_building_discovery(store, binding, operation, session, nearby, **kwargs)

    return SimpleNamespace(
        store=store,
        binding=binding,
        operation=operation,
        path=path,
        session=session,
        nearby=nearby,
        reader=reader,
        run=run,
    )


@pytest.mark.parametrize("mode", ["", "vacancy", "secondary"])
def test_two_buildings_and_vendors_are_verified_without_touching_crafting(fixture, mode):
    f = fixture
    f.session.mode = mode
    f.store.root.mkdir(parents=True)
    current = f.store.root / "current.json"
    current.write_text('{"job_id":"existing-review"}')
    f.session.focus_wait = True
    result = f.run()
    assert result["state"] == "complete"
    assert result["buildings_verified"] == result["vendors"] == 2
    assert not result["roster_complete"] and not result["town_membership_verified"]
    assert [(b, v) for b, v, _ in f.session.calls] == [(123, 0), (123, 1230), (456, 0), (456, 4560)]
    assert all(a["state"] == "observed" for a in result["attempts"])
    assert len({key for _, _, key in f.session.calls}) == 4
    assert current.read_text() == '{"job_id":"existing-review"}'
    with pytest.raises(VendorBatchStopped, match="already attempted"):
        f.run()
    assert len(f.session.calls) == 4


@pytest.mark.parametrize("mode", ["uncertain", "exception", "pending", "scene"])
def test_unconfirmed_window_stops_and_never_replays(fixture, mode):
    f = fixture
    f.session.mode = mode
    with pytest.raises((VendorBatchStopped, OSError)):
        f.run()
    assert len(f.session.calls) == 1
    saved = json.loads(f.path.read_text())
    assert saved["state"] == "review"
    assert saved["attempts"][0]["state"] != "observed"
    with pytest.raises(VendorBatchStopped, match="already attempted"):
        f.run()
    assert len(f.session.calls) == 1


def test_unavailable_before_native_entry_can_skip_to_next_building(fixture):
    f = fixture
    f.session.mode = "unavailable"
    result = f.run()
    assert result["state"] == "complete"
    assert result["roster"][0]["state"] == "unavailable"
    assert result["attempts"][0]["state"] == "not_submitted"
    assert result["vendors"] == 1


def test_empty_window_does_not_claim_complete_empty_roster(fixture):
    f = fixture
    f.session.mode = "empty"
    with pytest.raises(VendorBatchStopped, match="No vendor windows"):
        f.run()
    result = json.loads(f.path.read_text())
    assert result["state"] == "review"
    assert result["vendors"] == result["buildings_verified"] == 0
    assert not result["roster_complete"]
    assert all(row["state"] == "no_visible_hirelings" for row in result["roster"])


def test_cancelled_and_unresolved_states_never_open(fixture):
    f = fixture
    f.session.mode = "unresolved"
    with pytest.raises(VendorBatchStopped, match="previous window request"):
        f.run()
    assert not f.session.calls


def test_cancel_after_intent_prevents_publication(fixture):
    f = fixture

    def cancel():
        return f.path.exists() and bool(json.loads(f.path.read_text())["attempts"])

    with pytest.raises(VendorBatchStopped, match="cancelled"):
        f.run(cancelled=cancel)
    assert not f.session.calls
    saved = json.loads(f.path.read_text())
    assert saved["state"] == "cancelled" and saved["attempts"][0]["state"] == "prepared"


@pytest.mark.parametrize("change", ["process", "building", "snapshot"])
def test_independent_roster_mismatch_blocks_next_window(fixture, change):
    f = fixture

    def changed(binding, *, window):
        result = f.reader(binding, window=window)
        if change == "process":
            result["process_id"] += 1
        elif change == "building":
            result["building"]["object_id"] += 1
        else:
            f.session.state = replace(f.session.state, revision=f.session.state.revision + 1)
        return result

    with pytest.raises(VendorBatchStopped, match="roster changed"):
        f.run(reader=changed)
    assert len(f.session.calls) == 1


def test_foreign_nearby_discovery_never_opens(fixture):
    fixture.nearby["game_creation_filetime"] += 1
    with pytest.raises(VendorBatchStopped, match="another client"):
        fixture.run()
    assert not fixture.session.calls


def test_stale_window_stops_instead_of_skipping_every_building(fixture):
    f = fixture
    f.session.mode = "stale"
    with pytest.raises(VendorBatchStopped, match="state changed"):
        f.run()
    saved = json.loads(f.path.read_text())
    assert saved["state"] == "review"
    assert len(f.session.calls) == 1
    assert saved["attempts"][0]["state"] == "not_submitted"
    assert saved["attempts"][0]["outcome"] == "STALE"
    with pytest.raises(VendorBatchStopped, match="already attempted"):
        f.run()
    assert len(f.session.calls) == 1


def test_all_unavailable_is_review_not_success(fixture):
    fixture.session.mode = "all_unavailable"
    with pytest.raises(VendorBatchStopped, match="No vendor windows"):
        fixture.run()
    saved = json.loads(fixture.path.read_text())
    assert saved["state"] == "review" and saved["vendors"] == 0
    assert all(row["state"] == "unavailable" for row in saved["roster"])


@pytest.mark.parametrize("field", ["scene", "root"])
@pytest.mark.parametrize("value", [None, True, 0, -1, "1"])
def test_missing_or_invalid_candidate_provenance_never_opens(fixture, field, value):
    f = fixture
    if value is None:
        del f.nearby[field]
    else:
        f.nearby[field] = value
    with pytest.raises(VendorBatchStopped, match="scene provenance"):
        f.run()
    assert not f.session.calls
    saved = json.loads(f.path.read_text())
    assert saved["state"] == "review" and not saved["attempts"]
    assert saved[field] == value
    summary = json.loads((f.store.root / "nearby-summary.json").read_text())
    assert summary[field] == value and summary["state"] == "review"
    with pytest.raises(VendorBatchStopped, match="already attempted"):
        f.run()
    assert not f.session.calls


@pytest.mark.parametrize("change", ["scene", "root"])
def test_candidate_provenance_mismatch_is_durable_before_first_open(fixture, change):
    f = fixture
    f.session.state = replace(f.session.state, **{change: getattr(f.session.state, change) + 1})
    with pytest.raises(VendorBatchStopped, match="different scene"):
        f.run()
    assert not f.session.calls
    saved = json.loads(f.path.read_text())
    assert saved["state"] == "review" and saved["attempts"] == []
    assert (saved["scene"], saved["root"]) == (1, 100)


@pytest.mark.parametrize("change", [None, "scene", "root"])
def test_worker_city_to_navigation_handoff_keeps_original_scene(fixture, monkeypatch, change):
    from functools import partial
    from unittest.mock import Mock

    from shadowbane_lab.manager import vendor_control
    from shadowbane_lab.manager.operation import WorkerOperationKind, WorkerOperationState
    from shadowbane_lab.manager.vendor_discovery import run_discovery
    from tests.test_city_window import OPENED, STATE, receipt

    f = fixture
    f.binding.client_id, f.binding.instance_id, f.binding.worker_id = "client", "instance", "worker"
    f.operation.kind = WorkerOperationKind.VENDOR
    f.operation.client_id, f.operation.instance_id = "client", "instance"
    f.operation.worker_id, f.operation.node_id = "worker", "node"
    f.operation.command = "vendor discover"
    city = Mock()
    city.closed = False
    # Different ordinary city/native navigation managers are expected; only the
    # shared root and scene identify the same client scene across this handoff.
    city_state = replace(STATE, manager=800)
    city_opened = replace(OPENED, manager=800, active_manager=800, building_count=2)
    city.inspect.side_effect = [receipt(city_state), receipt(city_opened), receipt(city_opened)]
    city.open.return_value = receipt(outcome=Outcome.SUBMITTED, flags=0)

    def close_city():
        city.closed = True
        if change:
            f.session.state = replace(
                f.session.state, **{change: getattr(f.session.state, change) + 1},
            )

    city.close.side_effect = close_city
    f.session.close = Mock()

    def navigation(binding):
        assert binding is f.binding and city.closed
        return f.session

    candidates = dict(f.nearby["roster"], process_id=988, process_creation_filetime_utc=123)
    for building in candidates["buildings"]:
        building["vendors"] = []
    # Use both real production phases through the actual worker; replace only
    # native observation adapters with deterministic owned-scene fixtures.
    monkeypatch.setattr(vendor_control, "run_discovery", partial(
        run_discovery, reader=lambda _: candidates, sleep=lambda _: None,
    ))
    monkeypatch.setattr(vendor_control, "run_building_discovery", partial(
        run_building_discovery, reader=f.reader, sleep=lambda _: None,
    ))
    crafting = Mock(side_effect=AssertionError("discovery cannot craft"))
    executor = vendor_control.VendorWorkerExecutor(
        f.store.root.parents[3], "node", f.binding, session_factory=crafting,
        city_session_factory=lambda _: city, navigation_session_factory=navigation,
    )
    if change:
        with pytest.raises(VendorBatchStopped, match="different scene"):
            executor.execute(f.operation, stop_signal=SimpleNamespace(is_set=lambda: False))
        assert not f.session.calls
    else:
        result = executor.execute(f.operation, stop_signal=SimpleNamespace(is_set=lambda: False))
        assert result.state == WorkerOperationState.SUCCEEDED and len(f.session.calls) == 4
    city.close.assert_called_once_with()
    f.session.close.assert_called_once_with()
    crafting.assert_not_called()
    discovery_path = f.store.root / "discovery" / (f.operation.operation_id + ".json")
    discovery = json.loads(discovery_path.read_text())
    assert (discovery["scene"], discovery["root"]) == (1, 100)
    assert discovery["expected"] == city_state.encode().hex()
    summary = json.loads((f.store.root / "nearby-summary.json").read_text())
    assert (summary["scene"], summary["root"]) == (1, 100)
    assert summary["state"] == ("review" if change else "complete")


@pytest.mark.parametrize("field,value", [("scene", 2**64), ("root", 2**32)])
def test_candidate_provenance_requires_native_wire_width(fixture, field, value):
    fixture.nearby[field] = value
    with pytest.raises(VendorBatchStopped, match="scene provenance"):
        fixture.run()
    assert not fixture.session.calls
    assert json.loads(fixture.path.read_text())["state"] == "review"
