import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_budget import VendorBatchBudget
from shadowbane_lab.client_extension.vendor_order_batch import (
    queue_quantity_orders,
    validate_queued_orders,
)
from shadowbane_lab.client_extension.vendor_recipe import RandomOrderSpec, RandomRecipeSpec
from shadowbane_lab.client_extension.vendor_wire import IN_FLIGHT, Outcome, Slot
from tests.test_vendor_automatic_replies import cooking, send
from tests.test_vendor_batch import Session as BaseSession
from tests.test_vendor_batch import receipt, snapshot
from tests.test_vendor_random_recipe import preparation_for

SPEC = RandomOrderSpec(RandomRecipeSpec(26990, 12), 10, True)


def preparation(session):
    raw = json.loads(preparation_for(session, spec=SPEC))
    raw.update(schema_version=2, operation="prepare_order")
    return json.dumps(raw).encode()


class Recorder:
    process_id = BaseSession.identity.process_id
    creation = BaseSession.identity.creation_filetime_utc

    def __init__(self, parent=None):
        self.parent, self.records = parent, []
        self.incomplete = False
        self.cursor = dict(process_id=self.process_id, creation=self.creation, sequence=0,
                           overwritten=0, rejected=0, ticket_drops=0,
                           capture_incomplete=False, read_errors=0)

    def bookmark(self):
        return dict(cursor=dict(self.cursor), history_discarded=0, history_missing=0,
                    command_admitted=False)

    def available(self):
        return {}

    def context(self):
        return SimpleNamespace(initial=self.parent.state,
                               sequence=self.cursor["sequence"] + len(self.records))

    def append(self, item, *, complete=0, raw_count=1, template=None):
        self.records.extend(cooking(self.context(), item, complete=complete,
                                    queue_count_raw=raw_count,
                                    template=self.parent.state.item_template
                                    if template is None else template))

    def serialized(self, action=1, **changes):
        if action == 1:
            changes.update(reference=[self.parent.state.item_template, 0],
                           marker_raw=self.parent.state.table,
                           quantity_raw=self.parent.state.quantity,
                           multiple_raw=self.parent.state.multiple)
        self.records.extend(send(self.context(), action, **changes))

    def drain(self):
        if self.records:
            self.cursor["sequence"] = self.records[-1]["sequence"]
            self.cursor["overwritten"] = max(0, self.cursor["sequence"] - 256)
        records, self.records = self.records, []
        return dict(cursor=dict(self.cursor, capture_incomplete=self.incomplete),
                    records=records, capture_incomplete=self.incomplete)


class Session(BaseSession):
    def __init__(self, path, behavior="normal", capacity=7):
        super().__init__(path)
        self.state = replace(snapshot(tuple(Slot(600 + i * 100) for i in range(capacity))),
                             quantity=10, multiple=1)
        self.behavior, self.counts = behavior, (0,) * capacity
        self.pending = None
        self.recorder = Recorder(self)

    def inspect_orders(self):
        if self.pending:
            key = self.pending
            self.pending = None
            slots = list(self.state.slots)
            counts = list(self.counts)
            for index, slot in enumerate(slots):
                if slot.item:
                    continue
                self.next_item += 1
                slots[index] = replace(slot, item=self.next_item, state=1)
                counts[index] = 1
                self.recorder.append(self.next_item, template=self.state.item_template
                                     + int(self.behavior == "wrong_template"))
            if self.behavior == "grows":
                slots.append(Slot(9999))
                counts.append(0)
            self.counts = tuple(counts)
            self.state = replace(self.state, revision=self.state.revision + 1, slots=tuple(slots))
            if self.behavior == "closes":
                self.state = replace(self.state, recipe=0, quantity=0)
            self.last_transition = self.next_item, key
        return replace(receipt(self.state, item=self.last_transition[0],
                               transition=self.last_transition[1]), remaining_counts=self.counts)

    def create_orders(self, expected, key, *, batch_key, budget):
        saved = json.loads(self.path.read_bytes())
        request = saved["requests"][-1]
        assert request["state"] == "prepared" and request["request_key"] == key
        assert request["expected_snapshot"] == expected.encode().hex()
        assert budget.orders == saved["planned_orders"] and budget.cost_per_order == 1660
        assert saved["batch_id"] == batch_key and expected == self.state
        self.calls.append(key)
        if self.behavior == "lost":
            raise TimeoutError("lost Create acknowledgement")
        self.recorder.serialized()
        self.pending = key
        return replace(receipt(expected, key, Outcome.SUBMITTED, IN_FLIGHT),
                       remaining_counts=self.counts)


def run(session, reader=None, **kwargs):
    reader = reader or session.recorder
    reader.parent = session
    session.recorder = reader
    return queue_quantity_orders(
        session, session.path, SPEC, VendorBatchBudget.from_snapshot(session.state, {555: 1660}),
        preparation(session), reader, character=(123, 53), sleeper=lambda _: None, **kwargs,
    )


def test_seven_slots_are_seventy_items_with_one_journaled_batch_create(tmp_path):
    session = Session(tmp_path / "create.json")
    result = run(session)
    assert result["state"] == "queued" and result["planned_items"] == 70
    assert len(session.calls) == 1 and len(result["initial_items"]) == 7
    assert result["batch_budget"]["total_costs"] == {"555": 11620}
    assert validate_queued_orders(session.path.read_bytes())[0] == result


def test_growth_defers_extra_slot_to_next_batch(tmp_path):
    session = Session(tmp_path / "create.json", behavior="grows", capacity=2)
    result = run(session)
    assert len(session.calls) == 1 and result["planned_items"] == 20
    assert result["capacity_history"] == [2, 3]
    validate_queued_orders(session.path.read_bytes())


def test_multiple_create_can_close_recipe_after_single_batch_submission(tmp_path):
    session = Session(tmp_path / "create.json", behavior="closes", capacity=2)
    assert run(session)["state"] == "queued"
    validate_queued_orders(session.path.read_bytes())


def test_capacity_growth_before_submission_requires_fresh_batch_funding(tmp_path):
    session = Session(tmp_path / "create.json", capacity=2)
    def grow():
        session.state = replace(session.state, slots=(*session.state.slots, Slot(999)))
        session.counts += (0,)
    with pytest.raises(VendorBatchStopped, match="replan funding"):
        run(session, before_action=grow)
    assert not session.calls
    assert json.loads(session.path.read_bytes())["requests"] == []


@pytest.mark.parametrize("behavior", ["wrong_template", "lost"])
def test_uncertain_create_stops_without_replay(tmp_path, behavior):
    session = Session(tmp_path / "create.json", behavior)
    with pytest.raises((VendorBatchStopped, TimeoutError)):
        run(session)
    assert len(session.calls) == 1
    assert json.loads(session.path.read_bytes())["state"] == "review"
    with pytest.raises(VendorBatchStopped, match="never replay"):
        run(session)
    assert len(session.calls) == 1


def test_recorder_loss_prevents_next_create(tmp_path):
    session = Session(tmp_path / "create.json")
    reader = Recorder()
    def lose():
        reader.incomplete = True
    with pytest.raises(VendorBatchStopped, match="incomplete"):
        run(session, reader, before_action=lose)
    assert not session.calls


@pytest.mark.parametrize("field,value", [
    ("planned_items", True), ("planned_orders", 8), ("capacity", 17),
    ("initial_counts", [0]), ("initial_counts", [False] * 7),
    ("capacity_history", [True, 7]), ("process_id", True),
    ("batch_budget_sha256", "0" * 64),
])
def test_historical_validation_rejects_changed_budget_or_identity(tmp_path, field, value):
    session = Session(tmp_path / "create.json")
    raw = run(session)
    raw[field] = value
    with pytest.raises(ValueError):
        validate_queued_orders(json.dumps(raw).encode())


@pytest.mark.parametrize("field,value", [
    ("observed_counts", [False] * 7), ("expected_counts", None),
    ("preparation_sha256", "0" * 64), ("state", "submitted"),
    ("item_ids", [True]), ("transition_request", None),
])
def test_historical_validation_requires_every_observed_transition(tmp_path, field, value):
    session = Session(tmp_path / "create.json")
    raw = copy.deepcopy(run(session))
    raw["requests"][0][field] = value
    with pytest.raises(ValueError):
        validate_queued_orders(json.dumps(raw).encode())
