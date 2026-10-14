"""Owned-item manifests for native batch admission; no command submission.

WBRC1 binds exact current inventory addresses, identities, values, durability,
custom/displayed names and every effect word. The native owner reconstructs this
digest from its own inventory before selection and immediately before sending.
"""
from __future__ import annotations

import hashlib
import math
import struct

from shadowbane_lab.equipment.rolling_policy import evaluate_roll_tiers

from .vendor_recycle_evidence import IMAGE

MAX_ITEMS = 48


def _uint(value, *, nonzero=False):
    if type(value) is not int or not (1 if nonzero else 0) <= value < 2**32:
        raise ValueError("recycle manifest word is invalid")
    return value


def _address(value):
    value = _uint(value, nonzero=True)
    if not 0x10000 <= value < 0x80000000 or value % 4:
        raise ValueError("recycle manifest address is invalid")
    return value


def _text(value):
    if type(value) is not str:
        raise ValueError("recycle manifest name is invalid")
    raw = value.encode("utf-16-le")
    if len(raw) > 8192:
        raise ValueError("recycle manifest name exceeds its bound")
    return struct.pack("<I", len(raw)) + raw


def item_bytes(row, display_name):
    if (row["item"] != dict(object_id=row["item"]["object_id"], object_type=40)
            or row["template"] != dict(object_id=26990, object_type=0)
            or row["has_item_data"] is not True or row["name"] != ""
            or type(row["effects"]) is not list or len(row["effects"]) > 64
            or not 0 < _uint(row["base_value"]) <= 2**31 - 1):
        raise ValueError("recycle manifest requires an owned unrenamed Gilded Scepter")
    durability = row["durability"]
    values = [durability["full"], durability["current"]]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("recycle manifest durability is invalid")
    effects, tokens = [], set()
    for effect in row["effects"]:
        token = _uint(effect["token"], nonzero=True)
        if (token in tokens or type(effect["trains"]) is not int or effect["trains"] != 0
                or type(effect["source_type"]) is not int or effect["source_type"] != 1):
            raise ValueError("recycle manifest contains unqualified effects")
        tokens.add(token)
        effects.append(struct.pack("<III", token, 0, 1))
    words = (_uint(row["item"]["object_id"], nonzero=True), 26990,
             _address(row["entry_address"]), _address(row["instance_address"]),
             _address(row["native_item_address"]), row["base_value"],
             _uint(row["value"]), _uint(row["quantity_raw"]), 0x101, len(effects))
    return (struct.pack("<10I2f", *words, *values) + _text(row["name"])
            + _text(display_name) + b"".join(effects))


def batch_fingerprint(items):
    if type(items) is not list or not 0 < len(items) <= MAX_ITEMS:
        raise ValueError("recycle manifest requires one bounded batch")
    digest = hashlib.sha256(b"WBRC1\0" + struct.pack("<I", len(items)))
    previous = 0
    for item in items:
        row = item["inventory_row"]
        identity = _uint(row["item"]["object_id"], nonzero=True)
        if (identity <= previous or item["item"] != row["item"]
                or item["template"] != row["template"]):
            raise ValueError("recycle manifest identities are not unique and ordered")
        previous = identity
        digest.update(item_bytes(row, item["display_name"]))
    return digest.hexdigest()


def plan_exclusions(assessment, eligible_ids):
    """Exclude only confirmed low tiers among this job's inventory-confirmed items.

    All other stock, missing observations and unknowns remain protected. Each
    manifest is independently admitted natively; this function never dispatches.
    Historical completed jobs must not be automatically adopted as eligible IDs.
    """
    if (type(assessment) is not dict
            or assessment.get("schema_version") != 1
            or assessment.get("record_type") != "owned_vendor_affix_assessment"
            or assessment.get("executable_sha256") != IMAGE
            or assessment.get("scope") != "displayed_entries"
            or assessment.get("complete_inventory") is not False
            or assessment.get("command_admitted") is not False
            or type(assessment.get("items")) is not list or len(assessment["items"]) > 512
            or type(eligible_ids) is not list or len(eligible_ids) > 160
            or any(not _uint(i, nonzero=True) for i in eligible_ids)
            or len(set(eligible_ids)) != len(eligible_ids)):
        raise ValueError("exclusion planning requires a fresh owned assessment and exact job items")
    gold = _uint(assessment["strongbox_gold"])
    if gold > 2**31 - 1:
        raise ValueError("exclusion strongbox balance is invalid")
    seen, excluded = set(), []
    eligible = set(eligible_ids)
    for item in assessment["items"]:
        identity = _uint(item["item"]["object_id"], nonzero=True)
        if identity in seen:
            raise ValueError("exclusion assessment contains duplicate items")
        seen.add(identity)
        decision = item["assessment"]
        tiers = [decision.get(k) for k in ("prefix_tier", "suffix_tier")]
        # Reject invented/boolean tiers; unknowns always win over low tiers.
        confirmed = all(type(tier) is int and 0 <= tier <= 3 for tier in tiers)
        if (identity not in eligible or not confirmed
                or decision.get("disposition") != "exclude"
                or decision.get("reason") != "confirmed_low_tier"
                or evaluate_roll_tiers(*tiers, completed=True) != "exclude"):
            continue
        item_bytes(item["inventory_row"], item["display_name"])
        excluded.append(item)
    excluded.sort(key=lambda item: item["item"]["object_id"])
    batches = []
    for offset in range(0, len(excluded), MAX_ITEMS):
        rows = excluded[offset:offset + MAX_ITEMS]
        refund = sum(item["inventory_row"]["base_value"] for item in rows)
        if gold + refund > 2**31 - 1:
            raise ValueError("exclusion refund exceeds the strongbox bound")
        batches.append(dict(items=[item["item"]["object_id"] for item in rows],
                            fingerprint=batch_fingerprint(rows), gold_before=gold,
                            refund=refund, gold_after=gold + refund))
        gold += refund
    return batches
