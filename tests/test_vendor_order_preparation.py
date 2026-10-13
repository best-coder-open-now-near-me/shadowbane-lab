import copy
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_menu import prepare_order, validate_completed_menu
from shadowbane_lab.client_extension.vendor_menu_wire import IN_FLIGHT, Outcome, Receipt, Snapshot
from shadowbane_lab.client_extension.vendor_recipe import (
    RandomOrderSpec,
    RandomRecipeSpec,
    validate_recipe_preparation,
)
from tests.test_vendor_menu import HOST, Session, recipe, state

SPEC = RandomOrderSpec(RandomRecipeSpec(25860, 16), 10)


class OrderSession(Session):
    def open_order_recipe(self, expected, key):
        response = super().send("open_recipe", expected, key)
        self.calls[-1] = "open_order_recipe"
        self.snapshot = replace(self.snapshot, quantity=1, multiple=1)
        return response

    def select_order_recipe(self, expected, template, key):
        response = super().send("select_recipe", expected, key, template)
        self.calls[-1] = "select_order_recipe"
        return response

    def random_order_mode(self, expected, key):
        response = super().send("random_mode", expected, key)
        self.calls[-1] = "random_order_mode"
        return response

    def order_quantity(self, expected, quantity, key):
        saved = json.loads(self.path.read_bytes())
        attempt = saved["requests"][-1]
        assert attempt["state"] == "prepared" and attempt["request_key"] == key
        assert (attempt["template"] == quantity
                and attempt["expected_snapshot"] == expected.encode().hex())
        assert self.snapshot == expected
        self.calls.append("order_quantity")
        if self.mode == "lost":
            raise TimeoutError("quantity acknowledgement lost")
        self.snapshot = replace(expected, revision=expected.revision + 1, quantity=quantity)
        self.transition = key
        if self.after_send:
            self.after_send()
        return Receipt(key, HOST, 999, Outcome.SUBMITTED, IN_FLIGHT, expected)


def run(session, spec=SPEC):
    return prepare_order(session, session.path, state(), spec,
                         clock=lambda: session.time, sleeper=session.sleep)


def ready(quantity=10):
    return recipe(item_template=25860, selected_template=25860, activated_template=25860,
                  table=16, mode=1, quantity=quantity, multiple=1,
                  prefix=3362971591, suffix=3362971591)


def test_prepares_ten_per_slot_through_correlated_non_spending_hooks(tmp_path):
    session = OrderSession(tmp_path / "prepare.json", state(inventory=800, front_hud=800))
    result = run(session)
    assert result["schema_version"] == 2 and result["state"] == "complete"
    assert session.calls == ["close_inventory", "open_order_recipe", "select_order_recipe",
                             "random_order_mode", "order_quantity"]
    assert result["requested_recipe"] == SPEC.as_dict()
    completed, _, final = validate_completed_menu(session.path.read_bytes())
    assert completed == result and SPEC.matches(final)
    validate_recipe_preparation(session.path.read_bytes(), SPEC, final,
                                process_id=1234, process_creation_filetime_utc=5678, window=999)


def test_existing_prepared_ten_item_menu_requires_no_actions(tmp_path):
    session = OrderSession(tmp_path / "prepare.json", ready())
    assert run(session)["requests"] == [] and not session.calls
    assert SPEC.matches(validate_completed_menu(session.path.read_bytes())[2])


def test_changes_only_quantity_when_same_random_order_is_selected(tmp_path):
    session = OrderSession(tmp_path / "prepare.json", ready(3))
    assert run(session)["state"] == "complete"
    assert session.calls == ["order_quantity"]


def test_single_slot_quantity_ten_keeps_native_fanout_bounded(tmp_path):
    spec = RandomOrderSpec(SPEC.recipe, 10, multiple=False)
    session = OrderSession(tmp_path / "prepare.json", state())
    result = run(session, spec)
    assert session.calls == ["open_recipe", "select_recipe", "random_mode", "order_quantity"]
    assert spec.matches(validate_completed_menu(session.path.read_bytes())[2])
    assert result["requested_recipe"]["multiple"] is False


def test_single_recipe_is_closed_and_reopened_in_multiple_mode(tmp_path):
    session = OrderSession(tmp_path / "prepare.json", replace(ready(1), multiple=0))
    run(session)
    assert session.calls[0:2] == ["close_recipe", "open_order_recipe"]
    assert SPEC.matches(session.snapshot)


def test_different_recipe_is_reopened_before_selection_on_any_page(tmp_path):
    session = OrderSession(tmp_path / "prepare.json", replace(ready(), item_template=26990,
                           selected_template=26990, activated_template=26990))
    run(session)
    assert session.calls[0:2] == ["close_recipe", "open_order_recipe"]


def test_lost_quantity_ack_is_preserved_and_never_replayed(tmp_path):
    session = OrderSession(tmp_path / "prepare.json", ready(1), mode="lost")
    with pytest.raises(TimeoutError):
        run(session)
    assert json.loads(session.path.read_bytes())["state"] == "review"
    with pytest.raises(VendorBatchStopped, match="never replay"):
        run(session)
    assert session.calls == ["order_quantity"]


@pytest.mark.parametrize("corruption", ["quantity", "multiple", "schema", "request_argument",
                                       "missing_transition", "owner", "single_operation"])
def test_preparation_recovery_requires_exact_order_and_all_transitions(tmp_path, corruption):
    session = OrderSession(tmp_path / "prepare.json", ready(1))
    original = run(session)
    record = copy.deepcopy(original)
    if corruption == "quantity":
        record["requested_recipe"]["quantity"] = 9
    elif corruption == "multiple":
        record["requested_recipe"]["multiple"] = 1
    elif corruption == "schema":
        record["schema_version"] = 1
    elif corruption == "request_argument":
        record["requests"][-1]["template"] = 9
    elif corruption == "missing_transition":
        record["requests"] = []
    elif corruption == "owner":
        final = Snapshot.decode(bytes.fromhex(record["final_snapshot"]))
        record["final_snapshot"] = replace(final, vendor=601).encode().hex()
    else:
        record.update(schema_version=1, operation="prepare_recipe")
    with pytest.raises(ValueError):
        validate_completed_menu(json.dumps(record).encode())
    assert session.calls == ["order_quantity"]


def test_order_spec_preserves_legacy_recipe_and_cannot_be_downgraded(tmp_path):
    saved = RandomRecipeSpec(25860, 16)
    assert saved.as_dict()["quantity"] == 1 and saved.as_dict()["multiple"] is False
    assert RandomOrderSpec.from_dict(SPEC.as_dict()) == SPEC
    assert SPEC.canonical_digest != saved.canonical_digest
    with pytest.raises(ValueError):
        RandomRecipeSpec.from_dict(SPEC.as_dict())
    with pytest.raises(ValueError):
        RandomOrderSpec.from_dict(saved.as_dict())
    with pytest.raises(FrozenInstanceError):
        SPEC.quantity = 1
    session = OrderSession(tmp_path / "prepare.json", ready())
    run(session)
    with pytest.raises(ValueError):
        validate_recipe_preparation(session.path.read_bytes(), saved, session.snapshot,
                                    process_id=1234, process_creation_filetime_utc=5678, window=999)


@pytest.mark.parametrize("quantity", [0, 11, True, 1.5, -1])
def test_invalid_order_quantity_never_opens_a_journal(tmp_path, quantity):
    with pytest.raises(ValueError):
        RandomOrderSpec(RandomRecipeSpec(25860, 16), quantity)
    session = OrderSession(tmp_path / "prepare.json")
    with pytest.raises(ValueError):
        run(session, RandomRecipeSpec(25860, 16))
    assert not session.path.exists() and not session.calls
