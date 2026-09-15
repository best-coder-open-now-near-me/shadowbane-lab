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
        if self.mode == "unavailable" and building == 123:
            outcome = Outcome.UNAVAILABLE
        elif self.mode == "uncertain":
            outcome = Outcome.UNCERTAIN
        else:
            self.state = replace(
                self.state,
                revision=self.state.revision + 1,
                active_manager=200,
                mode=6,
                building_hud=300,
                initialized=1,
                building_id=building,
                building_type=8,
                capacity=1,
                occupied=1,
                selected_entry=400 if vendor else 0,
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


def test_two_buildings_and_vendors_are_verified_without_touching_crafting(fixture):
    f = fixture
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
    result = f.run()
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
