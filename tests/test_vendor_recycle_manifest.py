import copy
import os
import re
import subprocess
from pathlib import Path

import pytest

from shadowbane_lab.client_extension.vendor_recycle_evidence import IMAGE
from shadowbane_lab.client_extension.vendor_recycle_manifest import (
    batch_fingerprint,
    plan_exclusions,
)


def item(index=0, base=0x10000000, tiers=(0, 2)):
    entry = base + 0x101000 + index * 0x20000
    row = dict(item=dict(object_id=4294904956 + index, object_type=40),
               template=dict(object_id=26990, object_type=0), entry_address=entry,
               instance_address=entry + 0x1000, native_item_address=entry + 0x2000,
               has_item_data=True, name="", base_value=151, value=5201, quantity_raw=0,
               durability=dict(full=30.0, current=30.0),
               effects=[dict(token=123, trains=0, source_type=1)])
    return dict(item=row["item"], template=row["template"], inventory_row=row,
                display_name="Gilded Scepter of Frost",
                assessment=dict(disposition="exclude", reason="confirmed_low_tier",
                                prefix_tier=tiers[0], suffix_tier=tiers[1]))


def assessment(count=70):
    return dict(schema_version=1, record_type="owned_vendor_affix_assessment",
                executable_sha256=IMAGE, scope="displayed_entries", complete_inventory=False,
                command_admitted=False, strongbox_gold=205328,
                items=[item(i) for i in range(count)])


def eligible(value):
    return [row["item"]["object_id"] for row in value["items"]]


def test_whole_completed_batch_splits_at_native_bound_and_reserves_each_full_refund():
    value = assessment()
    result = plan_exclusions(value, eligible(value))
    assert [len(batch["items"]) for batch in result] == [48, 22]
    assert [batch["refund"] for batch in result] == [7248, 3322]
    assert result[0]["gold_after"] == result[1]["gold_before"] == 212576
    assert result[1]["gold_after"] == 215898
    assert result[0]["fingerprint"] == batch_fingerprint(value["items"][:48])
    assert value["strongbox_gold"] == 205328


@pytest.mark.parametrize("tiers", [(1, None), (None, 2), (3, 3), (0, 0), (True, 2), (1, 99)])
def test_unknowns_retained_tiers_and_unqualified_tiers_are_protected(tiers):
    value = assessment(1)
    value["items"][0] = item(tiers=tiers)
    assert plan_exclusions(value, eligible(value)) == []


def test_unrelated_old_stock_is_never_adopted_and_missing_current_items_stay_protected():
    value = assessment(4)
    ids = [value["items"][1]["item"]["object_id"], 4294906000]
    result = plan_exclusions(value, ids)
    assert len(result) == 1 and result[0]["items"] == ids[:1]
    assert plan_exclusions(value, []) == []


@pytest.mark.parametrize("change", ["disposition", "reason"])
def test_policy_verdict_cannot_be_inferred_from_tiers_alone(change):
    value = assessment(1)
    value["items"][0]["assessment"][change] = "unknown_affix_preserved"
    assert plan_exclusions(value, eligible(value)) == []


@pytest.mark.parametrize("change", ["token", "address", "template", "name", "label", "value",
                                   "durability", "quantity"])
def test_manifest_binds_current_identity_contents_and_addresses(change):
    rows = [item()]
    original = batch_fingerprint(rows)
    row = rows[0]["inventory_row"]
    if change == "token":
        row["effects"][0]["token"] += 1
    elif change == "address":
        row["instance_address"] += 4
    elif change == "template":
        row["template"]["object_id"] += 1
    elif change == "name":
        row["name"] = "custom"
    elif change == "label":
        rows[0]["display_name"] = "Gilded Scepter of Unknown"
    elif change == "value":
        row["base_value"] += 1
    elif change == "durability":
        row["durability"]["current"] -= 1
    elif change == "quantity":
        row["quantity_raw"] += 1
    if change in ("template", "name"):
        with pytest.raises(ValueError):
            batch_fingerprint(rows)
    else:
        assert batch_fingerprint(rows) != original


@pytest.mark.parametrize("change", ["trained", "unclassified", "duplicate_effect", "bad_pointer",
                                   "missing_data", "boolean_value", "invalid_durability"])
def test_unqualified_owned_contents_cannot_enter_a_manifest(change):
    rows = [item()]
    row = rows[0]["inventory_row"]
    if change == "trained":
        row["effects"][0]["trains"] = 1
    elif change == "unclassified":
        row["effects"][0]["source_type"] = 2
    elif change == "duplicate_effect":
        row["effects"].append(copy.deepcopy(row["effects"][0]))
    elif change == "bad_pointer":
        row["entry_address"] = 0
    elif change == "missing_data":
        row["has_item_data"] = False
    elif change == "boolean_value":
        row["base_value"] = True
    elif change == "invalid_durability":
        row["durability"]["current"] = float("nan")
    with pytest.raises(ValueError):
        batch_fingerprint(rows)


def test_batch_order_uniqueness_and_limits_are_not_silently_normalized():
    for rows in ([], [item()] * 2, [item(1), item(0)], [item(i) for i in range(49)]):
        with pytest.raises(ValueError):
            batch_fingerprint(rows)


def test_plan_refund_and_job_identity_bounds():
    value = assessment(1)
    ids = eligible(value)
    with pytest.raises(ValueError):
        plan_exclusions(value, ids * 2)
    value["strongbox_gold"] = 2**31 - 1
    with pytest.raises(ValueError):
        plan_exclusions(value, ids)
    value["strongbox_gold"] = 1
    value["items"] *= 2
    with pytest.raises(ValueError):
        plan_exclusions(value, ids)


@pytest.mark.skipif(not os.environ.get("SHADOWBANE_RECYCLE_NATIVE_TEST"),
                    reason="compiled x86 native recycle test not supplied")
def test_host_digest_matches_actual_compiled_x86_native_capture():
    binary = Path(os.environ["SHADOWBANE_RECYCLE_NATIVE_TEST"])
    completed = subprocess.run([str(binary)], check=True, capture_output=True,
                               text=True, timeout=20)
    match = re.search(r"base=(\d+) digest=([0-9a-f]{64})", completed.stdout)
    assert match, completed.stdout
    base = int(match.group(1))
    assert batch_fingerprint([item(i, base) for i in range(7)]) == match.group(2)
