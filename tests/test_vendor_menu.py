import json
import uuid
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.movement_wire import Host
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_menu import (
    open_inventory,
    prepare_recipe,
    validate_completed_menu,
)
from shadowbane_lab.client_extension.vendor_menu_wire import (
    IN_FLIGHT,
    READY,
    Outcome,
    Receipt,
    Snapshot,
)

HOST = Host(123, 7, 456)
KEY = "11111111-2222-4333-8444-555555555555"


def state(**kwargs):
    return replace(Snapshot(scene=9, revision=1, root=100, manager=200,
                            front_hud=300, menu=300, hireling=400, building=500, vendor=600),
                   **kwargs)


def recipe(**kwargs):
    return state(recipe=700, front_hud=700, recipe_list=710, sentinel=3362971591,
                 **kwargs)


class Session:
    identity = NativeClientProcessIdentity(1234, 5678)

    def __init__(self, path, initial=None, mode="normal"):
        self.path = path
        self.snapshot = initial or state()
        self.mode = mode
        self.transition = None
        self.calls = []
        self.time = 0
        self.after_send = None

    def inspect(self):
        return Receipt(str(uuid.uuid4()), HOST, 999, Outcome.OBSERVED,
                       READY, self.snapshot, self.transition)

    def sleep(self, seconds):
        self.time += seconds

    def send(self, name, expected, key, template=0):
        saved = json.loads(self.path.read_text())
        assert saved["requests"][-1]["state"] == "prepared"
        assert saved["requests"][-1]["request_key"] == key
        assert saved["requests"][-1]["expected_snapshot"] == expected.encode().hex()
        assert expected == self.snapshot
        self.calls.append(name)
        if self.mode == "lost":
            raise TimeoutError("lost submission acknowledgement")
        if name == "open_recipe":
            self.snapshot = recipe()
        elif name == "select_recipe":
            self.snapshot = replace(expected, item_template=template,
                                    selected_template=template, activated_template=template)
        elif name == "random_mode":
            self.snapshot = replace(expected, mode=1, table=16, quantity=1,
                                    prefix=3362971591, suffix=3362971591)
        elif name == "open_inventory":
            self.snapshot = state(inventory=800, front_hud=800)
        else:
            self.snapshot = state()
        self.snapshot = replace(self.snapshot, revision=expected.revision + 1)
        self.transition = KEY if self.mode == "wrong_correlation" else key
        if self.mode == "owner_changed":
            self.snapshot = replace(self.snapshot, scene=99)
        if self.mode == "bad_result":
            self.snapshot = state(revision=expected.revision + 1)
        if self.after_send:
            self.after_send()
        return Receipt(key, HOST, 999, Outcome.SUBMITTED, IN_FLIGHT, expected)

    def open_recipe(self, expected, key):
        return self.send("open_recipe", expected, key)

    def select_recipe(self, expected, template, key):
        return self.send("select_recipe", expected, key, template)

    def random_mode(self, expected, key):
        return self.send("random_mode", expected, key)

    def close_recipe(self, expected, key):
        return self.send("close_recipe", expected, key)

    def open_inventory(self, expected, key):
        return self.send("open_inventory", expected, key)

    def close_inventory(self, expected, key):
        return self.send("close_inventory", expected, key)


def run(session, **kwargs):
    return prepare_recipe(session, session.path, state(), 25860, clock=lambda: session.time,
                          sleeper=session.sleep, **kwargs)


def test_prepare_records_exact_recipe_and_each_correlated_transition(tmp_path):
    session = Session(tmp_path / "menu.json", state(inventory=800, front_hud=800))
    result = run(session, table=16)
    assert result["state"] == "complete"
    assert session.calls == ["close_inventory", "open_recipe", "select_recipe", "random_mode"]
    assert result["requested_recipe"]["template"] == {"object_id": 25860, "object_type": 0}
    assert result["requested_recipe"]["table"] == 16
    assert Snapshot.decode(bytes.fromhex(result["final_snapshot"])).random_recipe(25860, 16)
    assert all(r["state"] == "observed" and r["request_key"] == r["transition_request"]
               for r in result["requests"])
    with pytest.raises(VendorBatchStopped, match="never replay"):
        run(session)
    assert len(session.calls) == 4


def test_existing_multiple_recipe_is_closed_before_single_preparation(tmp_path):
    session = Session(tmp_path / "menu.json", recipe(multiple=1))
    assert run(session)["state"] == "complete"
    assert session.calls[0:2] == ["close_recipe", "open_recipe"]


def test_already_prepared_recipe_requires_no_mutation(tmp_path):
    session = Session(tmp_path / "menu.json", recipe(
        item_template=25860, selected_template=25860, activated_template=25860,
        mode=1, table=16, quantity=1, prefix=3362971591, suffix=3362971591))
    assert run(session)["state"] == "complete"
    assert not session.calls


@pytest.mark.parametrize("mode", ["lost", "wrong_correlation", "owner_changed", "bad_result"])
def test_uncertain_or_mismatched_transition_is_durable_and_never_replayed(tmp_path, mode):
    session = Session(tmp_path / "menu.json", mode=mode)
    with pytest.raises((VendorBatchStopped, TimeoutError)):
        run(session)
    assert len(session.calls) == 1
    saved = json.loads(session.path.read_text())
    assert saved["state"] == "review"
    assert saved["requests"][0]["state"] in ("prepared", "submitted")
    with pytest.raises(VendorBatchStopped, match="never replay"):
        run(session)
    assert len(session.calls) == 1
    assert session.time < 6.1


def test_expected_table_mismatch_never_adopts_new_recipe(tmp_path):
    session = Session(tmp_path / "menu.json")
    with pytest.raises(VendorBatchStopped, match="requested table"):
        run(session, table=12)
    assert json.loads(session.path.read_text())["state"] == "review"


def test_cancellation_reconciles_sent_action_then_stops_before_next(tmp_path):
    session = Session(tmp_path / "menu.json")
    stopped = False

    def stop():
        nonlocal stopped
        stopped = True

    session.after_send = stop
    with pytest.raises(VendorBatchStopped, match="cancelled"):
        run(session, cancelled=lambda: stopped)
    saved = json.loads(session.path.read_text())
    assert session.calls == ["open_recipe"]
    assert saved["requests"][0]["state"] == "observed"


def test_early_owner_mismatch_is_saved_without_mutation(tmp_path):
    session = Session(tmp_path / "menu.json", state(vendor=777))
    with pytest.raises(VendorBatchStopped, match="ownership"):
        run(session)
    assert not session.calls
    assert json.loads(session.path.read_text())["state"] == "review"


def test_inventory_closes_recipe_and_only_claims_visible_inventory(tmp_path):
    session = Session(tmp_path / "menu.json", recipe())
    result = open_inventory(session, session.path, state())
    assert session.calls == ["close_recipe", "open_inventory"]
    final = Snapshot.decode(bytes.fromhex(result["final_snapshot"]))
    assert final.front_hud == final.inventory
    assert result["state"] == "complete"
    assert "complete_inventory" not in result


@pytest.mark.parametrize("template,table", [(0, None), (True, None), (25860, 0), (25860, True)])
def test_invalid_saved_recipe_fails_before_journal_or_dispatch(tmp_path, template, table):
    session = Session(tmp_path / "menu.json")
    with pytest.raises(ValueError):
        prepare_recipe(session, session.path, state(), template, table=table)
    assert not session.path.exists()
    assert not session.calls


@pytest.mark.parametrize("operation", ["prepare_recipe", "open_inventory"])
def test_completed_journal_validates_correlated_chain(tmp_path, operation):
    session = Session(tmp_path / "menu.json")
    result = (run(session) if operation == "prepare_recipe"
              else open_inventory(session, session.path, state()))
    record, initial, final = validate_completed_menu(session.path.read_bytes())
    assert record == result
    assert initial == state()
    assert final == session.snapshot


@pytest.mark.parametrize("mutation", ["partial", "schema", "window", "owner", "template",
    "final", "pending", "duplicate", "transition", "remove", "empty", "order", "result"])
def test_recovery_rejects_incomplete_tampered_or_uncorrelated_evidence(tmp_path, mutation):
    session = Session(tmp_path / "menu.json")
    record = run(session)
    if mutation == "partial":
        record["state"] = "review"
    elif mutation == "schema":
        record["schema_version"] = True
    elif mutation == "window":
        record["window"] = 0
    elif mutation == "owner":
        record["expected_owner"] = state(vendor=999).encode().hex()
    elif mutation == "template":
        record["requested_recipe"]["template"]["object_type"] = False
    elif mutation == "final":
        record["final_snapshot"] = state().encode().hex()
    elif mutation == "pending":
        record["requests"][0]["state"] = "submitted"
    elif mutation == "duplicate":
        record["requests"][1]["request_key"] = record["requests"][0]["request_key"]
    elif mutation == "transition":
        record["requests"][0]["transition_request"] = KEY
    elif mutation == "remove":
        del record["requests"][1]
    elif mutation == "empty":
        record["requests"] = []
    elif mutation == "order":
        record["requests"].reverse()
    elif mutation == "result":
        record["requests"][0]["observed_snapshot"] = state().encode().hex()
    with pytest.raises(ValueError, match="complete, correlated"):
        validate_completed_menu(json.dumps(record).encode())


def test_already_open_inventory_journal_validates_without_fabricated_transition(tmp_path):
    session = Session(tmp_path / "menu.json", state(inventory=800, front_hud=800))
    result = open_inventory(session, session.path, state())
    assert not result["requests"]
    assert validate_completed_menu(session.path.read_bytes())[0] == result


def test_recovery_read_is_bounded():
    with pytest.raises(ValueError, match="bound"):
        validate_completed_menu(bytes(256 * 1024 + 1))


def test_external_menu_change_before_next_send_stops_with_durable_review(tmp_path):
    session = Session(tmp_path / "menu.json")

    def interfere():
        session.snapshot = recipe()

    with pytest.raises(VendorBatchStopped, match="outside this operation"):
        run(session, before_action=interfere)
    assert not session.calls
    assert json.loads(session.path.read_text())["state"] == "review"


@pytest.mark.parametrize("verb", ["select_recipe", "random_mode"])
@pytest.mark.parametrize("field", ["recipe", "recipe_list"])
def test_replaced_recipe_window_or_list_is_not_a_correlated_transition(tmp_path, verb, field):
    session = Session(tmp_path / "menu.json")
    original = session.send

    def replace_after_send(name, expected, key, template=0):
        result = original(name, expected, key, template)
        if name == verb:
            changes = {field: 9999}
            if field == "recipe":
                changes["front_hud"] = 9999
            session.snapshot = replace(session.snapshot, **changes)
        return result

    session.send = replace_after_send
    with pytest.raises(VendorBatchStopped, match="window or list changed"):
        run(session)
    saved = json.loads(session.path.read_text())
    assert saved["state"] == "review"
    assert saved["requests"][-1]["state"] == "submitted"
    assert session.snapshot.selected(25860)
    if verb == "random_mode":
        assert session.snapshot.random_recipe(25860)


@pytest.mark.parametrize("verb", ["select_recipe", "random_mode"])
@pytest.mark.parametrize("field", ["recipe", "recipe_list"])
def test_recovery_rejects_replaced_recipe_even_with_desired_template_and_continuity(
    tmp_path, verb, field,
):
    session = Session(tmp_path / "menu.json")
    record = run(session)
    start = next(i for i, request in enumerate(record["requests"]) if request["verb"] == verb)

    def substituted(raw):
        snapshot = Snapshot.decode(bytes.fromhex(raw))
        changes = {field: 9999}
        if field == "recipe":
            changes["front_hud"] = 9999
        return replace(snapshot, **changes).encode().hex()

    for index in range(start, len(record["requests"])):
        request = record["requests"][index]
        request["observed_snapshot"] = substituted(request["observed_snapshot"])
        if index > start:
            request["expected_snapshot"] = substituted(request["expected_snapshot"])
    record["final_snapshot"] = substituted(record["final_snapshot"])
    assert Snapshot.decode(bytes.fromhex(record["final_snapshot"])).random_recipe(25860)
    with pytest.raises(ValueError, match="complete, correlated"):
        validate_completed_menu(json.dumps(record).encode())
