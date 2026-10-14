import copy
import json
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_order_progress import OrderProgress
from shadowbane_lab.client_extension.vendor_wire import Slot
from tests.test_vendor_automatic_replies import cooking, deposit, reply, send
from tests.test_vendor_order_batch import Session, run

CHARACTER = (123, 53)


def setup(tmp_path, capacity=2):
    session = Session(tmp_path / "create.json", capacity=capacity)
    run(session)
    return session, OrderProgress(session.path.read_bytes(), CHARACTER)


def turn(session, progress):
    slots = []
    for slot in session.state.slots:
        deposit(progress.replies, slot.item)
        progress.confirm_inventory([slot.item])
        session.next_item += 1
        progress.receive(cooking(progress.replies, session.next_item))
        slots.append(replace(slot, item=session.next_item))
    session.state = replace(session.state, revision=session.state.revision + 1, slots=tuple(slots))
    progress.observe(session.state, (1,) * len(slots))


def terminal(session, progress):
    for slot in session.state.slots:
        progress.receive(cooking(progress.replies, slot.item, complete=1,
                                 queue_ignored_raw=1, queue_count_raw=0))
    session.state = replace(session.state, revision=session.state.revision + 1,
                            slots=tuple(replace(slot, state=2) for slot in session.state.slots))
    progress.observe(session.state, (0,) * len(session.state.slots))


def test_full_seventy_item_batch_needs_receipts_and_every_id_in_inventory(tmp_path):
    session, progress = setup(tmp_path, 7)
    for _ in range(9):
        turn(session, progress)
    assert len(progress.items) == 70 and not progress.complete
    terminal(session, progress)
    assert progress.keep_candidate(session.state) in progress.items
    last = [slot.item for slot in session.state.slots]
    for item in last:
        progress.expect_keep(item)
        progress.receive(send(progress.replies, 4, reference=[item, 40]))
        deposit(progress.replies, item)
    progress.confirm_inventory(last[:-1])
    empty = replace(session.state, revision=session.state.revision + 1,
                    slots=tuple(Slot(slot.entry) for slot in session.state.slots))
    progress.observe(empty, (0,) * 7)
    assert not progress.complete
    progress.confirm_inventory(last[-1:])
    assert progress.complete and progress.summary()["kept"] == 70


def test_automatic_deposit_and_new_reply_allow_reallocated_queue_entries(tmp_path):
    session, progress = setup(tmp_path, 1)
    old = session.state.slots[0].item
    deposit(progress.replies, old)
    progress.confirm_inventory([old])
    new = old + 1
    progress.receive(cooking(progress.replies, new))
    state = replace(session.state, revision=session.state.revision + 1,
                    slots=(Slot(999, new, 1),))
    progress.observe(state, (1,))
    assert set(progress.items) == {old, new}


def test_no_keep_races_server_automatic_rolls_even_when_ui_says_complete(tmp_path):
    session, progress = setup(tmp_path, 1)
    session.state = replace(session.state, slots=(replace(session.state.slots[0], state=2),))
    assert progress.keep_candidate(session.state) is None
    assert not progress.complete


def test_short_batch_retains_server_terminal_items_without_filling_a_deficit(tmp_path):
    session, progress = setup(tmp_path, 1)
    for _ in range(8):
        turn(session, progress)
    terminal(session, progress)
    assert len(progress.items) == 9 and not progress.complete
    item = session.state.slots[0].item
    assert progress.keep_candidate(session.state) == item
    progress.expect_keep(item)
    progress.receive(send(progress.replies, 4, reference=[item, 40]))
    deposit(progress.replies, item)
    progress.confirm_inventory([item])
    progress.observe(replace(session.state, slots=(Slot(session.state.slots[0].entry),)), (0,))
    assert progress.complete and progress.summary()["shortfall"] == 1
    assert len(session.calls) == 1


def test_asymmetric_twelve_item_server_batch_keeps_exact_results_and_reports_eight_short(tmp_path):
    session, progress = setup(tmp_path, 2)
    turn(session, progress)
    for slot in session.state.slots:
        deposit(progress.replies, slot.item)
        progress.confirm_inventory([slot.item])
    session.next_item += 1
    progress.receive(cooking(progress.replies, session.next_item))
    session.state = replace(session.state, revision=session.state.revision + 1,
                            slots=(Slot(600, session.next_item, 1), Slot(700)))
    progress.observe(session.state, (1, 1))
    for _ in range(7):
        old = session.state.slots[0].item
        deposit(progress.replies, old)
        progress.confirm_inventory([old])
        session.next_item += 1
        progress.receive(cooking(progress.replies, session.next_item))
        session.state = replace(session.state, revision=session.state.revision + 1,
                                slots=(Slot(600, session.next_item, 1), Slot(700)))
        progress.observe(session.state, (1, 1))
    item = session.state.slots[0].item
    progress.receive(cooking(progress.replies, item, complete=1, queue_count_raw=0))
    session.state = replace(session.state, revision=session.state.revision + 1,
                            slots=(Slot(600, item, 2), Slot(700)))
    progress.observe(session.state, (0, 1))
    assert len(progress.items) == 12 and progress.keep_candidate(session.state) == item
    progress.expect_keep(item)
    progress.receive(send(progress.replies, 4, reference=[item, 40]))
    deposit(progress.replies, item)
    progress.confirm_inventory([item])
    progress.observe(replace(session.state, slots=(Slot(600), Slot(700))), (0, 1))
    assert progress.complete and progress.summary()["shortfall"] == 8
    assert progress.admission["planned_items"] == 20 and len(session.calls) == 1


def test_positive_inventory_does_not_replace_server_deposit_receipts(tmp_path):
    session, progress = setup(tmp_path, 1)
    for _ in range(9):
        turn(session, progress)
    terminal(session, progress)
    progress.confirm_inventory([slot.item for slot in session.state.slots])
    empty = replace(session.state, slots=(Slot(session.state.slots[0].entry),))
    progress.observe(empty, (0,))
    assert not progress.complete


@pytest.mark.parametrize("change", ["unreceived", "reappeared", "owner", "capacity", "revision"])
def test_unexplained_queue_change_cannot_adopt_items(tmp_path, change):
    session, progress = setup(tmp_path, 2)
    state = session.state
    if change == "unreceived":
        state = replace(state, slots=(replace(state.slots[0], item=999), state.slots[1]))
    elif change == "reappeared":
        deposit(progress.replies, state.slots[0].item)
    elif change == "owner":
        state = replace(state, vendor=999)
    elif change == "capacity":
        state = replace(state, slots=state.slots[:1])
    else:
        progress.revision = state.revision + 1
    with pytest.raises(VendorBatchStopped):
        progress.observe(state, (1,) * len(state.slots))


def test_raw_count_changes_do_not_create_item_ancestry_or_change_quota(tmp_path):
    session, progress = setup(tmp_path, 2)
    progress.observe(session.state, (0, 255))
    assert len(progress.items) == 2 and progress.admission["planned_items"] == 20
    assert not progress.complete


def test_admission_cursor_cannot_claim_missing_receive_records(tmp_path):
    session, _ = setup(tmp_path)
    raw = json.loads(session.path.read_bytes())
    raw["production_cursor"]["sequence"] += 1
    with pytest.raises(ValueError):
        OrderProgress(json.dumps(raw).encode(), CHARACTER)


def test_owner_and_serialized_request_are_required_during_reconstruction(tmp_path):
    session, _ = setup(tmp_path)
    raw = json.loads(session.path.read_bytes())
    raw["production_records"][0]["payload"]["quantity_raw"] = 9
    with pytest.raises(ValueError):
        OrderProgress(json.dumps(raw).encode(), CHARACTER)
    with pytest.raises(ValueError, match="character"):
        OrderProgress(session.path.read_bytes(), (999, 53))


def test_server_receipt_errors_and_malformed_data_remain_sticky(tmp_path):
    _, progress = setup(tmp_path, 1)
    records = copy.deepcopy(reply(progress.replies, error=1))
    with pytest.raises(VendorBatchStopped):
        progress.receive(records)
    with pytest.raises(VendorBatchStopped):
        progress.receive([])
