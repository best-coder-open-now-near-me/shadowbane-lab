import copy

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_recycle_evidence import IMAGE, RecycleEvidence
from tests.test_vendor_automatic_replies import CHARACTER, payload, reply, send
from tests.test_vendor_batch import snapshot


def inventory():
    return dict(schema_version=1, record_type="vendor_inventory_snapshot", process_id=1234,
                process_creation_filetime_utc=5678, executable_sha256=IMAGE,
                native_window_address=100, manager_address=200, menu_address=300,
                building=dict(object_id=2229645, object_type=8),
                vendor=dict(object_id=2517204, object_type=42), command_admitted=False,
                inventory=dict(window_address=400, scope="displayed_entries",
                               complete_inventory=False, items=[
                                   dict(item=dict(object_id=i, object_type=40),
                                        template=dict(object_id=26990, object_type=0),
                                        base_value=151, effects=[dict(token=i)])
                                   for i in range(1001, 1011)]))


class Fixture:
    initial = snapshot()
    sequence = 657


def setup():
    return RecycleEvidence(inventory(), scene=1, character=CHARACTER, sequence=657,
                           gold_before=205328, item_ids=list(range(1001, 1008)))


def request(p):
    f = Fixture()
    f.sequence = p.sequence
    return send(f, 3, reference_list_raw=[[i, 40] for i in sorted(p.items)])


def response(p, *, empty=False):
    f = Fixture()
    f.sequence = p.sequence
    return reply(f, 7, fields=4,
                 reference_list_raw=[] if empty else [[i, 40] for i in reversed(sorted(p.items))],
                 strongbox_gold=p.gold_before if empty else p.gold_before + p.refund)


def after():
    value = inventory()
    value["inventory"]["items"] = value["inventory"]["items"][7:]
    return value


def test_captured_batch_shape_with_empty_updates_interleaved_and_reordered_ack_set():
    p = setup()
    p.receive(request(p))
    for _ in range(7):
        p.receive(response(p, empty=True))
    records = response(p)
    for r in records:
        p.receive([r])
    assert p.server_verified and not p.inventory_corroborated
    p.corroborate_inventory(after())
    assert p.summary() == dict(items=list(range(1001, 1008)), refund=1057,
                              gold_before=205328, gold_after=206385, sequence=682,
                              server_verified=True, inventory_corroborated=True,
                              command_admitted=False, replay_authorized=False)


def test_ack_decode_and_processing_do_not_prove_completion():
    p = setup()
    p.receive(request(p))
    records = response(p)
    p.receive(records[:2])
    assert not p.server_verified
    p.receive(records[2:])
    assert p.server_verified


def test_real_interleaving_of_eight_decodes_and_callback_pairs():
    p = setup()
    p.receive(request(p))
    blocks = []
    for index in range(8):
        block = response(p, empty=index != 7)
        decode = 659 + index
        for i, row in enumerate(block):
            row.update(sequence=decode if i == 0 else 667 + index * 2 + i,
                       decode_sequence=decode)
        blocks.append(block)
    # Four decodes, their first callback pair, the remaining four decodes,
    # then seven more callback pairs: the observed live thread ordering.
    order = ([b[0] for b in blocks[:4]] + blocks[0][1:]
             + [b[0] for b in blocks[4:]] + [r for b in blocks[1:] for r in b[1:]])
    for sequence, row in enumerate(order, 659):
        original_decode = row["decode_sequence"]
        if row["stage"] == "decoded":
            for block in blocks:
                if block[0] is row:
                    for member in block:
                        member["decode_sequence"] = sequence
                    break
        row["sequence"] = sequence
        assert original_decode
    p.receive(order)
    p.corroborate_inventory(after())
    assert p.server_verified and p.sequence == 682


def test_empty_updates_and_missing_inventory_are_not_success():
    p = setup()
    p.receive(request(p))
    p.receive(response(p, empty=True))
    assert not p.server_verified
    with pytest.raises(VendorBatchStopped, match="positive server"):
        p.corroborate_inventory(after())


@pytest.mark.parametrize("change", [
    "gap", "wrong_scene", "wrong_character", "wrong_vendor", "error", "duplicate_item",
    "extra_item", "missing_item", "wrong_type", "wrong_gold", "wrong_action", "wrong_fields",
    "changed_payload", "wrong_decode", "wrong_thread", "duplicate_return", "repeated_send",
    "reply_before_send", "diagnostic", "bad_flags", "partial_item", "unrelated_send",
])
def test_bad_causality_or_exact_set_is_sticky(change):
    p = setup()
    if change != "reply_before_send":
        p.receive(request(p))
    r = response(p)
    body = r[0]["payload"]
    if change == "gap":
        r[0]["sequence"] += 1
    elif change == "wrong_scene":
        r[0]["scene_epoch"] += 1
    elif change == "wrong_character":
        r[0]["local"][0] += 1
    elif change == "wrong_vendor":
        body["vendor"][0] += 1
    elif change == "error":
        body["error"] = 1
    elif change == "duplicate_item":
        body["reference_list_raw"][0] = body["reference_list_raw"][1]
    elif change == "extra_item":
        body["reference_list_raw"].append([9999, 40])
    elif change == "missing_item":
        body["reference_list_raw"].pop()
    elif change == "wrong_type":
        body["reference_list_raw"][0][1] = 0
    elif change == "wrong_gold":
        body["strongbox_gold"] += 1
    elif change == "wrong_action":
        body["action"] = 11
    elif change == "wrong_fields":
        body["fields"] = 0
    elif change == "changed_payload":
        r[2]["payload"]["strongbox_gold"] += 1
    elif change == "wrong_decode":
        r[1]["decode_sequence"] += 1
    elif change == "wrong_thread":
        r[2]["thread_id"] += 1
    elif change == "duplicate_return":
        r.append(copy.deepcopy(r[2]))
        r[-1]["sequence"] += 1
    elif change in ("repeated_send", "unrelated_send"):
        r = request(p)
        if change == "unrelated_send":
            r[0]["payload"]["action"] = 4
    elif change == "diagnostic":
        r[0]["diagnostic"] = {}
    elif change == "bad_flags":
        r[0]["flags"] = 1
    elif change == "partial_item":
        body["reference"] = [1001, 40]
    with pytest.raises(VendorBatchStopped):
        p.receive(r)
    assert not p.server_verified
    with pytest.raises(VendorBatchStopped, match="already rejected"):
        p.receive([])


def test_duplicate_acknowledgment_revokes_the_proof():
    p = setup()
    p.receive(request(p))
    p.receive(response(p))
    with pytest.raises(VendorBatchStopped, match="duplicate"):
        p.receive(response(p))
    assert not p.server_verified


@pytest.mark.parametrize("change", ["lifetime", "owner", "window", "still_present",
                                   "extra_removed", "extra_added", "survivor_changed"])
def test_unrelated_inventory_change_cannot_corroborate(change):
    p = setup()
    p.receive(request(p))
    p.receive(response(p))
    value = after()
    if change == "lifetime":
        value["process_creation_filetime_utc"] += 1
    elif change == "owner":
        value["manager_address"] += 4
    elif change == "window":
        value["inventory"]["window_address"] += 4
    elif change == "still_present":
        value["inventory"]["items"].append(inventory()["inventory"]["items"][0])
    elif change == "extra_removed":
        value["inventory"]["items"].pop()
    elif change == "extra_added":
        row = copy.deepcopy(value["inventory"]["items"][0])
        row["item"]["object_id"] = 9999
        value["inventory"]["items"].append(row)
    elif change == "survivor_changed":
        value["inventory"]["items"][0]["effects"][0]["token"] += 1
    with pytest.raises(VendorBatchStopped):
        p.corroborate_inventory(value)
    assert not p.server_verified


@pytest.mark.parametrize("change", ["image", "missing_stock", "duplicate_stock", "bad_value",
                                   "zero_value", "missing_item", "duplicate_batch", "overflow"])
def test_bad_admission_never_creates_an_observer(change):
    value = inventory()
    ids, gold = list(range(1001, 1008)), 205328
    if change == "image":
        value["executable_sha256"] = "0" * 64
    elif change == "missing_stock":
        value["inventory"] = None
    elif change == "duplicate_stock":
        value["inventory"]["items"].append(value["inventory"]["items"][0])
    elif change == "bad_value":
        value["inventory"]["items"][0]["base_value"] = True
    elif change == "zero_value":
        value["inventory"]["items"][0]["base_value"] = 0
    elif change == "missing_item":
        ids[0] = 9999
    elif change == "duplicate_batch":
        ids[0] = ids[1]
    elif change == "overflow":
        gold = 2**31 - 1
    with pytest.raises(ValueError):
        RecycleEvidence(value, scene=1, character=CHARACTER, sequence=657,
                        gold_before=gold, item_ids=ids)


def test_initial_and_received_evidence_cannot_be_mutated_by_caller():
    value = inventory()
    p = RecycleEvidence(value, scene=1, character=CHARACTER, sequence=657,
                        gold_before=205328, item_ids=list(range(1001, 1008)))
    value["vendor"]["object_id"] = 9999
    r = request(p)
    p.receive(r)
    r[0]["payload"] = payload(Fixture(), 1)
    p.receive(response(p))
    p.corroborate_inventory(after())
    assert p.server_verified
