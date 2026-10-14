"""Causal evidence for one server-driven production batch; no queue-count quotas."""
from __future__ import annotations

import json

from .vendor_batch import VendorBatchStopped, _items


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _key(value):
    return (type(value) in (tuple, list) and len(value) == 2
            and all(type(word) is int and 0 <= word < 2**32 for word in value))


def _payload(value):
    words = ("action", "error", "fields", "quantity_raw", "marker_raw", "prefix", "suffix",
             "template", "queue_count_raw", "value", "seconds", "duration", "queue_ignored_raw",
             "complete", "strongbox_gold", "multiple_raw", "template_type_raw", "queue_flags_raw")
    keys = ("building", "vendor", "reference", "item", "deposited_item", "deposited_template")
    return (type(value) is dict
            and all(type(value[word]) is int and 0 <= value[word] < 2**32 for word in words)
            and all(_key(value[key]) for key in keys)
            and value["action"] <= 13 and value["fields"] <= 15
            and all(value[word] <= 1 for word in ("queue_ignored_raw", "complete", "multiple_raw"))
            and type(value["reference_list_raw"]) is list
            and len(value["reference_list_raw"]) <= 256
            and all(_key(key) for key in value["reference_list_raw"]))


class AutomaticReplies:
    def __init__(self, initial, specification, character, orders, sequence):
        initial.encode()
        if (type(character) is not tuple or len(character) != 2
                or type(character[0]) is not int or not 0 < character[0] < 2**32
                or type(character[1]) is not int or character[1] != 53
                or type(orders) is not int or not 0 < orders == initial.free_slots
                or not specification.matches(initial)
                or any(slot.state == 1 for slot in initial.slots)
                or type(sequence) is not int or not 0 <= sequence < 2**63):
            raise ValueError("automatic production requires an exact owner and batch bound")
        self.initial, self.spec, self.character = initial, specification, character
        self.orders, self.limit = orders, orders * specification.quantity
        self.sequence = self.bookmark = sequence
        self.baseline = _items(initial)
        self.sent = None
        self.lineage, self.items = {}, {}
        self.first_items = []
        self.removed, self.deposited = set(), set()
        self.keep_intents, self.keep_sends = set(), set()
        self.failed = False

    def _stop(self, detail):
        self.failed = True
        raise VendorBatchStopped(detail)

    def expect_keep(self, item):
        if self.failed:
            self._stop("automatic production evidence was already rejected")
        if (item not in self.items or not self.items[item]["complete"]
                or item in self.keep_intents or item in self.deposited):
            self._stop("automatic batch Keep lacks a terminal item")
        self.keep_intents.add(item)

    def receive(self, records):
        if self.failed:
            self._stop("automatic production evidence was already rejected")
        try:
            if type(records) is not list or len(records) > 4096:
                self._stop("automatic production evidence exceeds its bound")
            for record in records:
                if (type(record["sequence"]) is not int
                        or record["sequence"] != self.sequence + 1):
                    self._stop("automatic production history is discontinuous")
                self.sequence = record["sequence"]
                if (type(record["flags"]) is not int or not 0 <= record["flags"] <= 15
                        or type(record["scene_epoch"]) is not int
                        or not 0 <= record["scene_epoch"] < 2**64
                        or not _key(record["local"])
                        or type(record["thread_id"]) is not int or record["thread_id"] <= 0
                        or record.get("diagnostic") is not None or record["flags"] & 8):
                    self._stop("automatic production contains a rejected observation")
                payload = record["payload"]
                if payload is None:
                    continue
                if not _payload(payload):
                    self._stop("malformed automatic production payload")
                if (tuple(payload["building"]) != (self.initial.building, 8)
                        or tuple(payload["vendor"]) != (self.initial.vendor, 42)):
                    continue
                if (record["scene_epoch"] != self.initial.scene
                        or tuple(record["local"]) != self.character or payload["error"]):
                    self._stop("automatic production reply changed owner or returned an error")
                stage, decode = record["stage"], record["decode_sequence"]
                if stage == "serialized":
                    if record["flags"] != 3 or decode:
                        self._stop("automatic production send is not qualified")
                    if payload["action"] == 1:
                        if (self.sent is not None
                                or tuple(payload["reference"]) != (self.spec.template, 0)
                                or payload["quantity_raw"] != self.spec.quantity
                                or payload["multiple_raw"] != 1
                                or payload["marker_raw"] != self.spec.table
                                or payload["prefix"] or payload["suffix"]
                                or payload["reference_list_raw"]):
                            self._stop("automatic production has an unrelated or repeated Create")
                        self.sent = record
                    elif payload["action"] == 4:
                        item, kind = payload["reference"]
                        if (kind != 40 or item not in self.keep_intents
                                or item in self.keep_sends):
                            self._stop("automatic production has an unjournaled Keep")
                        self.keep_sends.add(item)
                    else:
                        self._stop("automatic production has an unrelated outgoing action")
                    continue
                if type(decode) is not int or decode <= self.bookmark:
                    continue
                if self.sent is None:
                    self._stop("automatic production reply precedes its batch request")
                if stage == "decoded":
                    if (record["flags"] != 3 or decode != self.sequence
                            or decode in self.lineage or len(self.lineage) >= 64):
                        self._stop("automatic production decode is not qualified")
                    self.lineage[decode] = (record, "decoded")
                    continue
                previous = self.lineage.get(decode)
                if (record["flags"] != 7 or previous is None
                        or stage not in ("processing", "returned")
                        or previous[1] != ("decoded" if stage == "processing" else "processing")
                        or any(_canonical(record[key]) != _canonical(previous[0][key])
                               for key in ("payload", "scene_epoch", "local"))
                        or stage == "returned" and record["thread_id"] != previous[0]["thread_id"]):
                    self._stop("automatic production reply lacks exact single-use lineage")
                self.lineage[decode] = (record, stage)
                if stage != "returned":
                    continue
                del self.lineage[decode]
                self._returned(payload)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
            self.failed = True
            raise VendorBatchStopped("malformed automatic production evidence") from exc

    def _returned(self, payload):
        action = payload["action"]
        if action == 8:
            item, kind = payload["item"]
            if (type(item) is not int or not 0 < item < 2**32 or kind != 40
                    or payload["template"] != self.spec.template
                    or payload["template_type_raw"] != 0
                    or type(payload["queue_count_raw"]) is not int
                    or not 0 <= payload["queue_count_raw"] < 2**32
                    or payload["complete"] not in (0, 1)
                    or payload["queue_ignored_raw"] not in (0, 1)
                    or item in self.baseline):
                self._stop("automatic production changed item identity or template")
            old = self.items.get(item)
            if old is None:
                if payload["queue_ignored_raw"] or len(self.items) >= self.limit:
                    self._stop("automatic production has an unqualified or excess item")
                if len(self.first_items) < self.orders:
                    self.first_items.append(item)
            elif item in self.removed or old["complete"] and not payload["complete"]:
                self._stop("an earlier automatic production item reappeared")
            self.items[item] = dict(payload)
        elif action in (9, 10):
            key = payload["reference"] if action == 9 else payload["deposited_item"]
            item, kind = key
            if kind != 40 or item not in self.items:
                self._stop("automatic deposit lacks a batch item receipt")
            if action == 10 and tuple(payload["deposited_template"]) != (self.spec.template, 0):
                self._stop("automatic deposit changed the item template")
            target = self.removed if action == 9 else self.deposited
            if item in target:
                self._stop("automatic production repeated a removal or deposit")
            target.add(item)
        else:
            self._stop("automatic production returned an unqualified action")

    def admits(self, items):
        return (not self.failed and self.sent is not None and len(items) == self.orders
                and len(set(items)) == self.orders and set(items) == set(self.first_items))
