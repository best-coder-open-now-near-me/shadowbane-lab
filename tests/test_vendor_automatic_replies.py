import copy
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.vendor_automatic_replies import AutomaticReplies
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_recipe import RandomOrderSpec, RandomRecipeSpec
from shadowbane_lab.client_extension.vendor_wire import Slot
from tests.test_vendor_batch import snapshot

SPEC = RandomOrderSpec(RandomRecipeSpec(26990, 12), 10, True)
CHARACTER = (123, 53)


def setup(orders=2):
    state = replace(snapshot(tuple(Slot(600 + i * 100) for i in range(orders))),
                    quantity=10, multiple=1)
    return AutomaticReplies(state, SPEC, CHARACTER, orders, 0)


def payload(p, action, **changes):
    body = dict(action=action, error=0, fields=0, building=[p.initial.building, 8],
                vendor=[p.initial.vendor, 42], reference=[0, 0], quantity_raw=1,
                marker_raw=0, prefix=0, suffix=0, item=[0, 0], template=0,
                queue_count_raw=0, value=0, seconds=0, duration=0,
                queue_ignored_raw=0, complete=0, deposited_item=[0, 0],
                deposited_template=[0, 0], strongbox_gold=0, multiple_raw=0,
                template_type_raw=0, queue_flags_raw=0, reference_list_raw=[])
    body.update(changes)
    return body


def send(p, action=1, **changes):
    if action == 1:
        defaults = dict(reference=[SPEC.template, 0], quantity_raw=10,
                        multiple_raw=1, marker_raw=12)
        defaults.update(changes)
        changes = defaults
    return [dict(sequence=p.sequence + 1, stage="serialized", decode_sequence=0,
                 flags=3, scene_epoch=p.initial.scene, local=list(CHARACTER),
                 thread_id=10, payload=payload(p, action, **changes))]


def reply(p, action=8, **changes):
    first = p.sequence + 1
    body = payload(p, action, **changes)
    return [dict(sequence=first + i, stage=stage, decode_sequence=first,
                 flags=3 if i == 0 else 7, scene_epoch=p.initial.scene,
                 local=list(CHARACTER), thread_id=20 if i == 0 else 10,
                 payload=copy.deepcopy(body))
            for i, stage in enumerate(("decoded", "processing", "returned"))]


def cooking(p, item, **changes):
    return reply(p, item=[item, 40], template=changes.pop("template", SPEC.template),
                 queue_count_raw=changes.pop("queue_count_raw", 1), **changes)


def deposit(p, item):
    p.receive(reply(p, 9, reference=[item, 40]))
    p.receive(reply(p, 10, deposited_item=[item, 40],
                    deposited_template=[SPEC.template, 0]))


def test_one_send_admits_two_rows_with_count_one_and_zero():
    p = setup()
    p.receive(send(p))
    p.receive(cooking(p, 1001))
    assert p.admits([1001])
    p.receive(cooking(p, 1002, queue_count_raw=0))
    assert p.admits([1001, 1002])
    assert not p.admits([1001, 9999])


def test_twenty_distinct_items_follow_one_send_without_count_decrement():
    p = setup()
    p.receive(send(p))
    for item in range(1001, 1021):
        p.receive(cooking(p, item))
        if item <= 1018:
            deposit(p, item)
    for item in (1019, 1020):
        p.receive(cooking(p, item, complete=1, queue_ignored_raw=1, queue_count_raw=0))
    assert len(p.items) == 20 and len(p.removed & p.deposited) == 18
    assert p.admits([1001, 1002]) and not p.admits([1019, 1020])
    assert all(p.items[item]["complete"] for item in (1019, 1020))
    with pytest.raises(VendorBatchStopped, match="excess"):
        p.receive(cooking(p, 1021))


def test_decode_processing_and_return_can_span_drain_intervals():
    p = setup(1)
    p.receive(send(p))
    records = cooking(p, 1001)
    p.receive(records[:1])
    p.receive(records[1:2])
    assert not p.admits([1001])
    p.receive(records[2:])
    assert p.admits([1001])


@pytest.mark.parametrize("change", [
    "gap", "payload", "lineage", "local", "scene", "thread", "rejected",
])
def test_unqualified_receive_poison_is_sticky(change):
    p = setup(1)
    p.receive(send(p))
    records = cooking(p, 1001)
    if change == "gap":
        records[1]["sequence"] += 1
    elif change == "payload":
        records[2]["payload"]["template"] += 1
    elif change == "lineage":
        records[2]["decode_sequence"] += 1
    elif change == "local":
        records[0]["local"] = [999, 53]
    elif change == "scene":
        records[0]["scene_epoch"] += 1
    elif change == "thread":
        records[2]["thread_id"] += 1
    else:
        records[0]["flags"] |= 8
    with pytest.raises(VendorBatchStopped):
        p.receive(records)
    assert not p.admits([1001])
    with pytest.raises(VendorBatchStopped, match="already rejected"):
        p.receive([])


def test_second_matching_create_cannot_join_an_existing_batch():
    p = setup(1)
    p.receive(send(p))
    p.receive(cooking(p, 1001))
    with pytest.raises(VendorBatchStopped, match="repeated Create"):
        p.receive(send(p))


def test_old_decoder_handoff_and_other_vendor_cannot_adopt_items():
    p = setup(1)
    p.sequence = p.bookmark = 50
    p.receive(send(p))
    records = cooking(p, 1001)
    for r in records:
        r["decode_sequence"] = 40
    p.receive(records)
    p.receive(cooking(p, 1002, vendor=[999, 42]))
    assert not p.items


@pytest.mark.parametrize("action", [9, 10])
def test_inventory_reply_cannot_adopt_unknown_items(action):
    p = setup(1)
    p.receive(send(p))
    with pytest.raises(VendorBatchStopped, match="lacks a batch item"):
        p.receive(reply(p, action, reference=[999, 40], deposited_item=[999, 40]))


def test_only_journaled_terminal_keep_may_be_serialized():
    p = setup(1)
    p.receive(send(p))
    p.receive(cooking(p, 1001, complete=1))
    p.expect_keep(1001)
    p.receive(send(p, 4, reference=[1001, 40]))
    deposit(p, 1001)
    assert 1001 in p.keep_sends & p.removed & p.deposited
    with pytest.raises(VendorBatchStopped, match="unjournaled Keep"):
        p.receive(send(p, 4, reference=[1001, 40]))


def test_unrelated_outgoing_action_stops_the_batch():
    p = setup(1)
    p.receive(send(p))
    with pytest.raises(VendorBatchStopped, match="unrelated outgoing"):
        p.receive(send(p, 13))


@pytest.mark.parametrize("field,value", [
    ("local", [123.0, 53]), ("thread_id", True), ("scene_epoch", 1.0),
    ("complete", True), ("queue_count_raw", 1.0), ("quantity_raw", False),
])
def test_historical_numeric_coercion_cannot_grant_authority(field, value):
    p = setup(1)
    p.receive(send(p))
    records = cooking(p, 1001)
    if field in ("local", "thread_id", "scene_epoch"):
        records[0][field] = value
    else:
        records[0]["payload"][field] = value
    with pytest.raises(VendorBatchStopped):
        p.receive(records)
    with pytest.raises(VendorBatchStopped, match="already rejected"):
        p.expect_keep(1001)
