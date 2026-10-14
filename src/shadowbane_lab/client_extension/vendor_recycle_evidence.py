"""Exact-set, causal receipts for the qualified .19 batch Recycle workflow.

The client sends action 3 with an owned-item reference list. The server returns
action 7 with that same set and the refunded strongbox balance. Empty action-7
updates also occur and cannot acknowledge recycling. This observer grants no
dispatch, affix-policy or absence authority.
"""
from __future__ import annotations

import copy

from .vendor_automatic_replies import _canonical, _key, _payload
from .vendor_batch import VendorBatchStopped

IMAGE = "6bd0e391edc1c773b4c96d8a9801db45f96db9e34202afcfc8d383d4971fe5ad"
MAX_ITEMS = 256


def _uint(value, limit=2**32):
    return type(value) is int and 0 < value < limit


def _inventory(snapshot):
    if (type(snapshot) is not dict or snapshot.get("record_type") != "vendor_inventory_snapshot"
            or snapshot.get("schema_version") != 1 or snapshot.get("command_admitted") is not False
            or snapshot.get("executable_sha256") != IMAGE
            or not _uint(snapshot.get("process_id"))
            or not _uint(snapshot.get("process_creation_filetime_utc"), 2**64)
            or not all(_uint(snapshot.get(k)) for k in
                       ("native_window_address", "manager_address", "menu_address"))):
        raise ValueError("recycling requires a qualified owned inventory")
    for field, kind in (("building", 8), ("vendor", 42)):
        key = snapshot.get(field)
        if (type(key) is not dict or set(key) != {"object_id", "object_type"}
                or not _uint(key["object_id"]) or type(key["object_type"]) is not int
                or key["object_type"] != kind):
            raise ValueError("recycling inventory owner is invalid")
    stock = snapshot.get("inventory")
    if (type(stock) is not dict or stock.get("scope") != "displayed_entries"
            or stock.get("complete_inventory") is not False
            or not _uint(stock.get("window_address"))
            or type(stock.get("items")) is not list or len(stock["items"]) > 512):
        raise ValueError("recycling requires the current displayed inventory")
    items = {}
    for row in stock["items"]:
        key, template = row["item"], row["template"]
        if (type(key) is not dict or set(key) != {"object_id", "object_type"}
                or type(key.get("object_type")) is not int or key.get("object_type") != 40
                or not _uint(key.get("object_id")) or key["object_id"] in items
                or type(template) is not dict or set(template) != {"object_id", "object_type"}
                or type(template.get("object_type")) is not int or template.get("object_type") != 0
                or not _uint(template.get("object_id"))):
            raise ValueError("recycling inventory contains ambiguous item identities")
        items[key["object_id"]] = row
    return items


class RecycleEvidence:
    """Single request, exact item set, complete callback lineage; never a sender.

    A fresh native admission must separately bind these identities to current
    ownership and the durable exclusion policy. A manual capture is evidence of
    that manual operation only, never permission to repeat it.
    """

    def __init__(self, inventory, *, scene, character, sequence, gold_before, item_ids):
        items = _inventory(inventory)
        if (not _uint(scene, 2**64) or not _key(character)
                or not _uint(character[0]) or character[1] != 53
                or type(sequence) is not int or not 0 <= sequence < 2**63
                or type(gold_before) is not int or not 0 <= gold_before <= 2**31 - 1
                or type(item_ids) is not list or not 0 < len(item_ids) <= MAX_ITEMS
                or any(not _uint(item) for item in item_ids)
                or len(set(item_ids)) != len(item_ids) or not set(item_ids) <= items.keys()):
            raise ValueError("recycling requires a bounded exact owned-item batch")
        values = [items[item].get("base_value") for item in item_ids]
        if any(not _uint(value, 2**31) for value in values):
            raise ValueError("recycling refund requires qualified base values")
        self.refund = sum(values)
        if gold_before + self.refund > 2**31 - 1:
            raise ValueError("recycling refund exceeds the strongbox balance bound")
        self.initial = copy.deepcopy(inventory)
        self.scene, self.character = scene, tuple(character)
        self.sequence = self.bookmark = sequence
        self.items, self.gold_before = frozenset(item_ids), gold_before
        self.sent = self.acknowledgment = None
        self.lineage = {}
        self.failed = self.inventory_corroborated = False

    def _stop(self, detail):
        self.failed = True
        raise VendorBatchStopped(detail)

    def _body(self, payload, *, sent):
        refs = payload["reference_list_raw"]
        if (len(refs) != len(self.items) or any(key[1] != 40 for key in refs)
                or {key[0] for key in refs} != self.items
                or payload["fields"] != (0 if sent else 4)
                or payload["quantity_raw"] != 1
                or payload["strongbox_gold"] != (
                    0 if sent else self.gold_before + self.refund)
                or any(payload[k] for k in (
                    "marker_raw", "prefix", "suffix", "template", "queue_count_raw", "value",
                    "seconds", "duration", "queue_ignored_raw", "complete", "multiple_raw",
                    "template_type_raw", "queue_flags_raw"))
                or any(tuple(payload[k]) != (0, 0) for k in
                       ("reference", "item", "deposited_item", "deposited_template"))):
            self._stop("recycling request or acknowledgment changed the exact batch")

    def receive(self, records):
        if self.failed:
            self._stop("recycling evidence was already rejected")
        try:
            if type(records) is not list or len(records) > 4096:
                self._stop("recycling evidence exceeds its bound")
            for record in records:
                if (type(record["sequence"]) is not int
                        or record["sequence"] != self.sequence + 1
                        or self.sequence - self.bookmark >= 4096):
                    self._stop("recycling history is discontinuous or exhausted")
                self.sequence = record["sequence"]
                if (record.get("diagnostic") is not None or record["flags"] not in (3, 7)
                        or type(record["flags"]) is not int
                        or type(record["scene_epoch"]) is not int
                        or record["scene_epoch"] != self.scene
                        or not _key(record["local"]) or tuple(record["local"]) != self.character
                        or not _uint(record["thread_id"])):
                    self._stop("recycling observation changed owner or was rejected")
                payload = record["payload"]
                if not _payload(payload):
                    self._stop("malformed recycling payload")
                if (tuple(payload["building"]) != (self.initial["building"]["object_id"], 8)
                        or tuple(payload["vendor"]) != (self.initial["vendor"]["object_id"], 42)):
                    self._stop("another vendor operation overlaps recycling")
                if payload["error"]:
                    self._stop("server returned a recycling error")
                stage, decode = record["stage"], record["decode_sequence"]
                if stage == "serialized":
                    if (record["flags"] != 3 or decode != 0 or type(decode) is not int
                            or self.sent is not None or payload["action"] != 3):
                        self._stop("recycling has an unrelated or repeated outgoing action")
                    self._body(payload, sent=True)
                    self.sent = copy.deepcopy(record)
                    continue
                if (self.sent is None or type(decode) is not int
                        or decode <= self.sent["sequence"] or payload["action"] != 7):
                    self._stop("recycling reply lacks a preceding qualified request")
                if stage == "decoded":
                    if (record["flags"] != 3 or decode != self.sequence
                            or decode in self.lineage or len(self.lineage) >= 64):
                        self._stop("recycling decode is not qualified")
                    self.lineage[decode] = (copy.deepcopy(record), "decoded")
                    continue
                previous = self.lineage.get(decode)
                if (record["flags"] != 7 or previous is None
                        or stage not in ("processing", "returned")
                        or previous[1] != ("decoded" if stage == "processing" else "processing")
                        or any(_canonical(record[k]) != _canonical(previous[0][k])
                               for k in ("payload", "scene_epoch", "local"))
                        or stage == "returned" and record["thread_id"] != previous[0]["thread_id"]):
                    self._stop("recycling reply lacks exact single-use callback lineage")
                self.lineage[decode] = (copy.deepcopy(record), stage)
                if stage == "returned":
                    del self.lineage[decode]
                    if payload["reference_list_raw"]:
                        if self.acknowledgment is not None:
                            self._stop("recycling has duplicate acknowledgments")
                        self._body(payload, sent=False)
                        self.acknowledgment = copy.deepcopy(record)
                    elif (payload["fields"] != 4
                          or payload["strongbox_gold"] != self.gold_before):
                        self._stop("recycling has an unexplained balance update")
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
            self.failed = True
            raise VendorBatchStopped("malformed recycling evidence") from exc

    @property
    def server_verified(self):
        return not self.failed and self.acknowledgment is not None and not self.lineage

    def corroborate_inventory(self, inventory):
        """Corroborate a positive server receipt; displayed absence alone proves nothing."""
        if not self.server_verified:
            self._stop("recycling inventory lacks a completed positive server receipt")
        try:
            after = _inventory(inventory)
            before = _inventory(self.initial)
            fields = ("process_id", "process_creation_filetime_utc", "executable_sha256",
                      "native_window_address", "manager_address", "menu_address",
                      "building", "vendor")
            if (any(inventory[k] != self.initial[k] for k in fields)
                    or inventory["inventory"]["window_address"]
                    != self.initial["inventory"]["window_address"]
                    or after.keys() != before.keys() - self.items
                    or any(after[k] != before[k] for k in after)):
                self._stop("recycling inventory changed owner or unrelated stock")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            self.failed = True
            raise VendorBatchStopped("invalid recycling inventory corroboration") from exc
        self.inventory_corroborated = True

    def summary(self):
        return dict(items=sorted(self.items), refund=self.refund,
                    gold_before=self.gold_before, gold_after=self.gold_before + self.refund,
                    sequence=self.sequence, server_verified=self.server_verified,
                    inventory_corroborated=self.inventory_corroborated and not self.failed,
                    command_admitted=False, replay_authorized=False)
