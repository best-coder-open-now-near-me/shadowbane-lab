import copy
import json
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_order_progress import OrderProgress
from shadowbane_lab.client_extension.vendor_wire import Slot
from tests.test_vendor_order_batch import Session, run

CHARACTER = (123, 53)


def replies(progress, item, remaining, **changes):
    body = dict(action=8, error=0, building=[progress.initial.building, 8],
                vendor=[progress.initial.vendor, 42], item=[item, 40],
                template=progress.spec.template, remaining_count_raw=remaining + 1)
    body.update(changes)
    first = progress.sequence + 1
    return [dict(sequence=first + i, stage=stage, decode_sequence=first,
                 flags=3 if i == 0 else 7, scene_epoch=progress.initial.scene,
                 local=list(CHARACTER), thread_id=20 if i == 0 else 10,
                 payload=copy.deepcopy(body))
            for i, stage in enumerate(("decoded", "processing", "returned"))]


def setup(tmp_path, capacity=2):
    session = Session(tmp_path / "create.json", capacity=capacity)
    run(session)
    progress = OrderProgress(session.path.read_bytes(), CHARACTER)
    for slot in session.state.slots:
        progress.receive(replies(progress, slot.item, 9))
    return session, progress


def test_v3_queue_count_cannot_be_adopted_as_legacy_remaining_quota(tmp_path):
    session = Session(tmp_path / "create.json", capacity=1)
    run(session)
    progress = OrderProgress(session.path.read_bytes(), CHARACTER)
    records = replies(progress, session.state.slots[0].item, 9, queue_count_raw=1)
    for record in records:
        del record["payload"]["remaining_count_raw"]
    with pytest.raises(VendorBatchStopped, match="verified order receipts"):
        progress.receive(records)


def test_full_seventy_item_batch_needs_every_distinct_id_in_inventory(tmp_path):
    session, progress = setup(tmp_path, 7)
    progress.observe(session.state, session.counts)
    for remaining in range(8, -1, -1):
        slots = []
        for slot in session.state.slots:
            progress.confirm_inventory([slot.item])
            session.next_item += 1
            progress.receive(replies(progress, session.next_item, remaining))
            slots.append(replace(slot, item=session.next_item))
        session.state = replace(session.state, revision=session.state.revision + 1,
                                slots=tuple(slots))
        progress.observe(session.state, (remaining + 1,) * 7)
    assert len(progress.items) == 70 and not progress.complete
    last = [slot.item for slot in session.state.slots]
    progress.confirm_inventory(last[:-1])
    empty = replace(session.state, revision=session.state.revision + 1,
                    slots=tuple(Slot(slot.entry) for slot in session.state.slots))
    progress.observe(empty, (0,) * 7)
    assert not progress.complete
    progress.confirm_inventory(last[-1:])
    progress.observe(empty, (0,) * 7)
    assert progress.complete and progress.summary()["kept"] == 70


def test_keep_transition_can_prove_one_reallocated_slot_successor(tmp_path):
    session, progress = setup(tmp_path, 1)
    old = session.state.slots[0].item
    progress.confirm_inventory([old])
    new = old + 1
    progress.receive(replies(progress, new, 8))
    state = replace(session.state, revision=session.state.revision + 1,
                    slots=(Slot(999, new, 1),))
    progress.observe(state, (9,), kept_item=old)
    assert progress.orders[0]["path"] == [old, new]


@pytest.mark.parametrize("change", ["skipped", "same_id", "no_reply", "unrelated_slot"])
def test_unexplained_quantity_transition_cannot_adopt_an_item(tmp_path, change):
    session, progress = setup(tmp_path, 1)
    old = session.state.slots[0]
    item = old.item if change == "same_id" else old.item + 1
    count = 7 if change == "skipped" else 8
    state = replace(session.state, revision=session.state.revision + 1,
                    slots=(Slot(999 if change == "unrelated_slot" else old.entry, item, 1),))
    with pytest.raises(VendorBatchStopped):
        if change != "no_reply":
            progress.receive(replies(progress, item, count))
        progress.observe(state, (count + 1,))
    assert len(progress.items) == 1


@pytest.mark.parametrize("change", ["gap", "payload", "lineage", "local", "scene"])
def test_qualified_reply_requires_contiguous_same_character_lineage(tmp_path, change):
    session, progress = setup(tmp_path, 1)
    raw = replies(progress, session.next_item + 1, 8)
    if change == "gap":
        raw[1]["sequence"] += 1
    elif change == "payload":
        raw[2]["payload"]["template"] += 1
    elif change == "lineage":
        raw[2]["decode_sequence"] += 1
    elif change == "local":
        raw[0]["local"] = [999, 53]
    else:
        raw[0]["scene_epoch"] += 1
    with pytest.raises(VendorBatchStopped):
        progress.receive(raw)


def test_other_vendor_replies_are_recorded_but_cannot_claim_batch_items(tmp_path):
    session, progress = setup(tmp_path, 1)
    raw = replies(progress, session.next_item + 1, 8, vendor=[999, 42])
    progress.receive(raw)
    assert len(progress.rolls) == 1 and progress.sequence == raw[-1]["sequence"]


def test_decode_can_handoff_threads_but_processing_and_return_must_match(tmp_path):
    session, progress = setup(tmp_path, 1)
    raw = replies(progress, session.next_item + 1, 8)
    assert raw[0]["thread_id"] != raw[1]["thread_id"]
    raw[2]["thread_id"] += 1
    with pytest.raises(VendorBatchStopped, match="lineage"):
        progress.receive(raw)


def test_positive_inventory_presence_cannot_adopt_unknowns_or_complete_queue(tmp_path):
    session, progress = setup(tmp_path, 1)
    progress.confirm_inventory([session.next_item, 999])
    assert progress.inventory_confirmed == {session.next_item}
    assert not progress.complete
    completed = replace(session.state, slots=(replace(session.state.slots[0], state=2),))
    assert progress.keep_candidate(completed) is None


def test_old_item_cannot_reappear_after_successor_was_observed(tmp_path):
    session, progress = setup(tmp_path, 1)
    old = session.state.slots[0]
    progress.receive(replies(progress, old.item + 1, 8))
    state = replace(session.state, revision=session.state.revision + 1,
                    slots=(replace(old, item=old.item + 1),))
    progress.observe(state, (9,))
    with pytest.raises(VendorBatchStopped, match="reappeared"):
        progress.observe(replace(state, slots=(old,)), (10,))


def test_admission_cursor_cannot_claim_missing_receive_records(tmp_path):
    session, _ = setup(tmp_path)
    raw = json.loads(session.path.read_bytes())
    raw["production_cursor"]["sequence"] = 1
    with pytest.raises(ValueError, match="gap"):
        OrderProgress(json.dumps(raw).encode(), CHARACTER)
