"""Existing results are kept once before a new batch reserves funds."""
import copy
import json
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_collection import (
    collect_completed_items,
    validate_collection,
)
from shadowbane_lab.client_extension.vendor_wire import IN_FLIGHT, Slot
from shadowbane_lab.manager.vendor_collection import (
    collect_saved_vendor_results,
    require_collections_idle,
)
from shadowbane_lab.manager.vendor_job import VendorJobStore, run_vendor_job
from tests.test_manager_vendor_orders import Session as OrderSession
from tests.test_manager_vendor_recipes import BINDING, OWNER, operation
from tests.test_vendor_batch import receipt


class Session(OrderSession):
    def __init__(self, store, capacity=7):
        super().__init__(store, capacity)
        self.path = store.root / "collections" / operation().operation_id / "collection.json"
        self.state = replace(self.state, recipe=0, slots=tuple(
            Slot(slot.entry, 100 + index, 2) for index, slot in enumerate(self.state.slots)))
        self.behavior = "normal"

    def inspect(self):
        if self.keep_pending:
            if self.behavior == "queue_only":
                item, _ = self.keep_pending
                self.state = replace(self.state, slots=tuple(
                    Slot(s.entry) if s.item == item else s for s in self.state.slots))
                return receipt(self.state, flags=IN_FLIGHT)
            if self.behavior == "owner_changed":
                return receipt(replace(self.state, scene=self.state.scene + 1))
        result = super().inspect()
        if self.behavior == "uncorrelated" and self.keeps:
            return replace(result, transition_request=None, transition_item=0)
        return result if self.focused else replace(result, flags=0)

    def keep(self, expected, item, key):
        saved = json.loads(self.path.read_bytes())
        request = saved["requests"][-1]
        assert request["state"] == "prepared" and request["request_key"] == key
        assert request["item"] == item and request["expected_snapshot"] == expected.encode().hex()
        assert expected == self.state and self.focused
        self.keeps.append(item)
        if self.behavior == "lost":
            raise OSError("lost Keep acknowledgement")
        self.keep_pending = item, key
        return receipt(expected, key, flags=IN_FLIGHT, outcome=1)


@pytest.fixture
def session(tmp_path):
    return Session(VendorJobStore(tmp_path, "node", "client", "instance"))


def run(session, **kwargs):
    return collect_completed_items(
        session, session.path, context=dict(identity=list(session.store.identity), owner=OWNER),
        clock=lambda: session.time, sleeper=session.sleep, **kwargs)


def test_all_sixteen_completed_items_are_durably_kept_once_without_spending(tmp_path):
    session = Session(VendorJobStore(tmp_path, "node", "client", "instance"), 16)
    result = run(session)
    assert validate_collection(session.path.read_bytes()) == result
    assert result["state"] == "complete" and result["creates"] == result["funds_moved"] == 0
    assert session.keeps == list(range(100, 116)) and session.inventory == set(session.keeps)
    assert not session.calls and session.state.free_slots == 16
    require_collections_idle(session.store)
    with pytest.raises(VendorBatchStopped, match="never replay"):
        run(session)
    assert len(session.keeps) == 16


def test_empty_queue_is_a_complete_no_action_collection(session):
    session.state = replace(session.state, slots=tuple(Slot(s.entry) for s in session.state.slots))
    assert run(session)["items"] == []
    assert not session.keeps and not session.calls and not session.menu_calls
    require_collections_idle(session.store)


def test_cooking_prevents_collection_before_any_action_or_journal(session):
    session.state = replace(session.state, slots=(replace(session.state.slots[0], state=1),)
                            + session.state.slots[1:])
    with pytest.raises(VendorBatchStopped, match="not ready"):
        run(session)
    assert not session.path.exists() and not session.keeps and not session.menu_calls


@pytest.mark.parametrize("mode", ["lost", "queue_only", "owner_changed", "uncorrelated"])
def test_uncertain_keep_blocks_new_work_and_never_replays(session, mode):
    session.behavior = mode
    with pytest.raises((OSError, VendorBatchStopped)):
        run(session)
    saved = json.loads(session.path.read_bytes())
    assert saved["state"] == "review" and len(session.keeps) == 1 and not session.calls
    with pytest.raises(VendorBatchStopped, match="Unresolved"):
        require_collections_idle(session.store)
    with pytest.raises(VendorBatchStopped, match="Unresolved"):
        run_vendor_job(session.store, session, session.window)
    assert session.store.current() is None
    with pytest.raises(VendorBatchStopped, match="never replay"):
        run(session)
    assert len(session.keeps) == 1


def test_collection_waits_for_focus_and_cancellation_prevents_next_keep(session):
    session.focused = False
    session.after_sleep = lambda: setattr(session, "focused", True)
    assert run(session)["state"] == "complete" and session.renewals
    other = Session(VendorJobStore(session.store.root.parent, "node2", "client", "instance"))
    with pytest.raises(VendorBatchStopped, match="cancelled"):
        run(other, cancelled=lambda: bool(other.keeps))
    assert len(other.keeps) == 1
    assert json.loads(other.path.read_bytes())["requests"][0]["state"] == "observed_in_inventory"


def test_saved_owner_is_rechecked_under_execution_lock_before_collection(session):
    selection = dict(owner=OWNER, building=dict(object_id=session.state.building),
                     vendor=dict(object_id=session.state.vendor))
    op = operation()
    session.path = session.store.root / "collections" / op.operation_id / "collection.json"
    result = collect_saved_vendor_results(
        session.store, BINDING, op, session, selection, cancelled=lambda: False,
        reader=session.reader)
    assert result["items"] == session.keeps
    assert result["context"]["owner"] == OWNER
    selection["owner"] = dict(OWNER, character="Someone else")
    with pytest.raises(VendorBatchStopped, match="another character"):
        collect_saved_vendor_results(session.store, BINDING, operation(), session, selection,
                                    cancelled=lambda: False, reader=session.reader)


def test_corrupt_historical_collection_cannot_authorize_new_work(session):
    original = run(session)
    mutations = [
        lambda r: r.update(state="running"),
        lambda r: r["requests"].pop(),
        lambda r: r["requests"][0]["receipt"].update(flags=IN_FLIGHT),
        lambda r: r["requests"][0]["receipt"].update(transition_item=999),
        lambda r: r["requests"][0].update(request_key=r["requests"][1]["request_key"]),
        lambda r: r["context"].update(identity=["node", "client", "other-instance"]),
        lambda r: r["context"]["owner"].update(key=[123, True]),
        lambda r: r.update(inventory_menu_utf8="{}"),
        lambda r: r.update(final_snapshot=r["initial_snapshot"]),
        lambda r: r.update(creates=True),
    ]
    for mutate in mutations:
        changed = copy.deepcopy(original)
        mutate(changed)
        session.path.write_text(json.dumps(changed))
        with pytest.raises(VendorBatchStopped, match="Unresolved"):
            require_collections_idle(session.store)
