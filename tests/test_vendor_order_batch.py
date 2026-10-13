import copy
import json
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_budget import VendorBatchBudget
from shadowbane_lab.client_extension.vendor_order_batch import (
    queue_quantity_orders,
    validate_queued_orders,
)
from shadowbane_lab.client_extension.vendor_recipe import RandomOrderSpec, RandomRecipeSpec
from shadowbane_lab.client_extension.vendor_wire import IN_FLIGHT, Outcome, Slot
from tests.test_vendor_batch import Session as BaseSession
from tests.test_vendor_batch import receipt, snapshot
from tests.test_vendor_random_recipe import preparation_for

SPEC = RandomOrderSpec(RandomRecipeSpec(26990, 12), 10, False)


def preparation(session):
    raw = json.loads(preparation_for(session, spec=SPEC))
    raw.update(schema_version=2, operation="prepare_order")
    return json.dumps(raw).encode()


class Recorder:
    process_id = BaseSession.identity.process_id
    creation = BaseSession.identity.creation_filetime_utc

    def __init__(self):
        self.incomplete = False
        self.cursor = dict(process_id=self.process_id, creation=self.creation, sequence=0,
                           overwritten=0, rejected=0, ticket_drops=0,
                           capture_incomplete=False, read_errors=0)

    def bookmark(self):
        return dict(cursor=dict(self.cursor), history_discarded=0, history_missing=0,
                    command_admitted=False)

    def drain(self):
        return dict(cursor=dict(self.cursor, capture_incomplete=self.incomplete),
                    records=[], capture_incomplete=self.incomplete)


class Session(BaseSession):
    def __init__(self, path, behavior="normal", capacity=7):
        super().__init__(path)
        self.state = replace(snapshot(tuple(Slot(600 + i * 100) for i in range(capacity))),
                             quantity=10)
        self.behavior, self.counts = behavior, (0,) * capacity
        self.pending = None

    def inspect_orders(self):
        if self.pending:
            key = self.pending
            self.pending = None
            index = next(i for i, slot in enumerate(self.state.slots) if not slot.item)
            self.next_item += 1
            slots = list(self.state.slots)
            slots[index] = replace(slots[index], item=self.next_item, state=1)
            counts = list(self.counts)
            counts[index] = 10 if self.behavior == "wrong_count" else 9
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
        self.pending = key
        return replace(receipt(expected, key, Outcome.SUBMITTED, IN_FLIGHT),
                       remaining_counts=self.counts)


def run(session, reader=None, **kwargs):
    return queue_quantity_orders(
        session, session.path, SPEC, VendorBatchBudget.from_snapshot(session.state, {555: 1660}),
        preparation(session), reader or Recorder(), sleeper=lambda _: None, **kwargs,
    )


def test_seven_slots_are_seventy_items_with_seven_journaled_quantity_creates(tmp_path):
    session = Session(tmp_path / "create.json")
    result = run(session)
    assert result["state"] == "queued" and result["planned_items"] == 70
    assert len(session.calls) == len(result["initial_items"]) == 7
    assert result["batch_budget"]["total_costs"] == {"555": 11620}
    assert validate_queued_orders(session.path.read_bytes())[0] == result


def test_growth_defers_extra_slot_to_next_batch(tmp_path):
    session = Session(tmp_path / "create.json", capacity=2)
    def grow():
        if len(session.calls) == 1 and len(session.state.slots) == 2:
            session.state = replace(session.state, slots=(*session.state.slots, Slot(999)))
            session.counts += (0,)
    result = run(session, before_action=grow)
    assert len(session.calls) == 2 and result["planned_items"] == 20
    assert result["capacity_history"] == [2, 3]
    validate_queued_orders(session.path.read_bytes())


def test_each_closed_recipe_is_reopened_with_separate_completed_proof(tmp_path):
    session = Session(tmp_path / "create.json", behavior="closes", capacity=2)
    def reopen(index):
        assert index == 1 and not session.state.recipe
        session.state = replace(session.state, recipe=401, quantity=10,
                                revision=session.state.revision + 1)
        return preparation(session)
    assert run(session, prepare_next=reopen)["state"] == "queued"
    validate_queued_orders(session.path.read_bytes())


@pytest.mark.parametrize("behavior", ["wrong_count", "lost"])
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
    ("observed_counts", [0] * 7), ("expected_counts", None),
    ("preparation_sha256", "0" * 64), ("state", "submitted"),
    ("item_id", True), ("transition_request", None),
])
def test_historical_validation_requires_every_observed_transition(tmp_path, field, value):
    session = Session(tmp_path / "create.json")
    raw = copy.deepcopy(run(session))
    raw["requests"][0][field] = value
    with pytest.raises(ValueError):
        validate_queued_orders(json.dumps(raw).encode())
