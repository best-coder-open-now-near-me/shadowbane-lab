import copy
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped, fill_available_slots
from shadowbane_lab.client_extension.vendor_budget import VendorBatchBudget
from shadowbane_lab.client_extension.vendor_completion import validate_completed_batch
from shadowbane_lab.client_extension.vendor_wire import Slot
from tests.test_manager_vendor_recipes import admit, save_recipe, setup
from tests.test_vendor_batch import MultipleSession, Session, snapshot


def ten_recipe():
    return replace(snapshot(tuple(Slot(600 + i * 100) for i in range(7))),
                   quantity=10, multiple=1)


def test_seven_ten_item_orders_cost_the_whole_seventy_item_batch_once():
    plan = VendorBatchBudget.from_snapshot(ten_recipe(), {2308551: 1660})
    assert plan.free_slots == 7 and plan.total_items == 70
    assert plan.total_costs == {2308551: 11620}
    assert VendorBatchBudget.from_dict(plan.as_dict()) == plan
    assert VendorBatchBudget.from_dict(plan.as_dict()).canonical_digest == plan.canonical_digest
    with pytest.raises(FrozenInstanceError):
        plan.capacity = 8
    occupied = replace(ten_recipe(), slots=(Slot(600, 12, 1), Slot(700, 13, 2),
                                           *ten_recipe().slots[2:]))
    partial = VendorBatchBudget.from_snapshot(occupied, {2308551: 1660})
    assert partial.total_items == 50 and partial.total_costs == {2308551: 8300}


@pytest.mark.parametrize("changes", [
    {"quantity": 11}, {"quantity": True}, {"quantity": 10, "multiple": 2},
    {"mode": 2}, {"prefix": 1}, {"suffix": 1}, {"recipe": 0},
])
def test_invalid_or_unowned_recipe_cannot_be_budgeted(changes):
    with pytest.raises(ValueError):
        VendorBatchBudget.from_snapshot(replace(ten_recipe(), **changes), {555: 1660})


@pytest.mark.parametrize("costs", [{}, {555: 0}, {555: True}, {0: 1660},
                                  {555: -1}, {555: 2**31}, {555: (2**31 - 1) // 7 + 1}])
def test_resource_bounds_reject_before_any_funding(costs):
    with pytest.raises(ValueError):
        VendorBatchBudget.from_snapshot(ten_recipe(), costs)


@pytest.mark.parametrize("field,value", [
    ("total_items", 7), ("total_costs", {"2308551": 1660}), ("capacity", True),
    ("owner", [1, 100, 2229645, 0]), ("recipe", [26990, 12, 10, True]),
    ("occupied", [1, 1]), ("schema_version", 2), ("unexpected", 1),
])
def test_saved_budget_is_canonical_and_cannot_change_quantity_or_total(field, value):
    record = VendorBatchBudget.from_snapshot(ten_recipe(), {2308551: 1660}).as_dict()
    record[field] = value
    with pytest.raises(ValueError):
        VendorBatchBudget.from_dict(record)


def test_budget_ignores_new_visit_addresses_but_pins_owner_recipe_and_capacity():
    state = ten_recipe()
    plan = VendorBatchBudget.from_snapshot(state, {2308551: 1660})
    assert plan.matches(replace(state, revision=7, recipe=401, menu=301, hireling=501,
                                slots=tuple(Slot(10000 + i * 100) for i in range(7))))
    for changes in ({"scene": 2}, {"root": 101}, {"vendor": 123}, {"building": 123},
                    {"quantity": 1}, {"item_template": 25860}, {"table": 16},
                    {"slots": state.slots + (Slot(5000),)},
                    {"slots": (Slot(600, 123, 1), *state.slots[1:])}):
        assert not plan.matches(replace(state, **changes))


def test_capacity_change_between_admission_and_fill_sends_nothing(tmp_path):
    path = tmp_path / "batch.json"
    session = Session(path)
    before = session.state
    session.state = replace(before, slots=before.slots + (Slot(800),))
    with pytest.raises(VendorBatchStopped, match="ownership or production changed"):
        fill_available_slots(session, path, before.vendor, expected_owner=before)
    assert not session.calls and not path.exists()


def test_multiple_growth_before_dispatch_cannot_expand_the_funded_request(tmp_path):
    path = tmp_path / "batch.json"
    session = MultipleSession(path)
    def grow():
        session.state = replace(session.state, slots=(*session.state.slots, Slot(900)))
    with pytest.raises(VendorBatchStopped, match="fund a new batch"):
        fill_available_slots(session, path, session.state.vendor, before_action=grow)
    record = json.loads(path.read_bytes())
    assert not session.calls and not record["requests"]
    assert record["planned_rolls"] == 3 and record["capacity"] == 4


def funded_selection(tmp_path):
    store, session, _ = setup(tmp_path)
    saved = save_recipe(store, session)
    selected = admit(saved, session)
    budget = VendorBatchBudget.from_snapshot(session.state, {555: 166})
    return store, session, dict(selected, batch_budget=budget.as_dict(),
                                batch_budget_sha256=budget.canonical_digest)


def test_job_start_rejects_rank_growth_after_funding_before_saving_job(tmp_path):
    store, session, selected = funded_selection(tmp_path)
    session.state = replace(session.state, slots=(*session.state.slots, Slot(800)))
    with pytest.raises(VendorBatchStopped, match="changed after funding"):
        store.begin(session, 1000, 100, selection=selected)
    assert store.current() is None and not session.calls


@pytest.mark.parametrize("corruption", ["missing", "hash", "quantity", "owner"])
def test_funded_job_restart_requires_the_original_budget(tmp_path, corruption):
    store, session, selected = funded_selection(tmp_path)
    record = store.begin(session, 1000, 100, selection=selected)
    assert record["schema_version"] == 3
    assert store.read(record["job_id"])["batch_budget"] == selected["batch_budget"]
    if corruption == "missing":
        record.pop("batch_budget")
    elif corruption == "hash":
        record["batch_budget_sha256"] = "f" * 64
    elif corruption == "quantity":
        record["batch_budget"]["recipe"][2] = 10
    else:
        record["batch_budget"]["owner"][3] += 1
    store.save(record)
    with pytest.raises((KeyError, ValueError)):
        store.current()
    assert not session.calls


def test_historical_growing_batch_remains_readable_without_replaying(tmp_path):
    initial = snapshot()
    states = [initial,
              replace(initial, slots=(Slot(600, 101, 1), Slot(700), Slot(800))),
              replace(initial, slots=(Slot(600, 101, 1), Slot(700, 102, 1), Slot(800)))]
    record = dict(schema_version=1, operation="fill_available_slots", state="complete",
                  batch_id="11111111-2222-4333-8444-555555555555", vendor_id=initial.vendor,
                  process_id=988, process_creation_filetime_utc=123, window=1000,
                  initial_snapshot=initial.encode().hex(), planned_rolls=3, capacity=3,
                  capacity_history=[2, 3], items=[101, 102, 103], requests=[])
    for index, state in enumerate(states):
        record["requests"].append(dict(request_key=f"11111111-2222-4333-8444-{index + 1:012d}",
                                       state="observed", expected_snapshot=state.encode().hex(),
                                       item_id=index + 101))
    assert validate_completed_batch(json.dumps(record).encode())[0] == record
    broken = copy.deepcopy(record)
    broken["capacity_policy"] = "initial"
    with pytest.raises(ValueError):
        validate_completed_batch(json.dumps(broken).encode())
