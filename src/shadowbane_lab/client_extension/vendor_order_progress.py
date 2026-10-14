"""Pure reconciliation of quantity orders, copied replies and inventory presence.

Order ancestry needs an observed slot transition. A copied reply alone cannot
adopt an unrelated item, and inventory absence can never authorize a retry.
"""
from __future__ import annotations

import json

from .vendor_batch import VendorBatchStopped, _items, _owner
from .vendor_order_batch import _counts, validate_queued_orders
from .vendor_recipe import RandomOrderSpec
from .vendor_wire import Snapshot


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class OrderProgress:
    def __init__(self, admission_raw: bytes, character: tuple[int, int]):
        self.admission, self.initial = validate_queued_orders(admission_raw)
        if (type(character) is not tuple or len(character) != 2
                or type(character[0]) is not int or not 0 < character[0] < 2**32
                or type(character[1]) is not int or character[1] != 53):
            raise ValueError("quantity progress requires the exact character key")
        self.character = character
        self.spec = RandomOrderSpec.from_dict(self.admission["recipe_spec"])
        self.baseline = _items(self.initial)
        self.items, self.orders, self.rolls, self.lineage = {}, [], {}, {}
        self.inventory_confirmed = set()
        self.capacity = self.admission["capacity"]
        self.revision = self.initial.revision
        self.visible = set(self.admission["initial_items"])
        self.sequence = self.admission["production_bookmark"]["cursor"]["sequence"]
        self.bookmark = self.sequence
        request = self.admission["requests"][0]
        state = Snapshot.decode(bytes.fromhex(request["observed_snapshot"]))
        for item in self.admission["initial_items"]:
            entry = next(slot.entry for slot in state.slots if slot.item == item)
            order = dict(entry=entry, current=item, remaining=self.spec.quantity - 1,
                         path=[item], finished=False)
            self.orders.append(order)
            self.items[item] = dict(order=len(self.orders) - 1,
                                    remaining=self.spec.quantity - 1)
        self.receive(self.admission["production_records"])
        if self.sequence != self.admission["production_cursor"]["sequence"]:
            raise ValueError("quantity admission history has a gap")

    def _ours(self, record, payload):
        return (record["scene_epoch"] == self.initial.scene
                and tuple(record["local"]) == self.character
                and tuple(payload["building"]) == (self.initial.building, 8)
                and tuple(payload["vendor"]) == (self.initial.vendor, 42))

    def receive(self, records):
        if type(records) is not list or len(records) > 4096:
            raise VendorBatchStopped("production receive evidence exceeds its bound")
        for record in records:
            if (type(record["sequence"]) is not int
                    or record["sequence"] != self.sequence + 1):
                raise VendorBatchStopped("production receive history is discontinuous")
            self.sequence = record["sequence"]
            payload, stage = record["payload"], record["stage"]
            if payload is None or not self._ours(record, payload):
                continue
            decode = record["decode_sequence"]
            # A callback decoded before the pre-Create bookmark is old history.
            if decode <= self.bookmark:
                continue
            if stage == "decoded":
                if record["flags"] != 3 or decode != self.sequence:
                    raise VendorBatchStopped("unqualified production decode")
                self.lineage[decode] = [record, "decoded"]
                continue
            previous = self.lineage.get(decode)
            if (record["flags"] != 7 or previous is None
                    or stage not in ("processing", "returned")
                    or previous[1] != ("decoded" if stage == "processing" else "processing")
                    or any(_canonical(record[key]) != _canonical(previous[0][key])
                           for key in ("payload", "scene_epoch", "local"))
                    or stage == "returned" and record["thread_id"] != previous[0]["thread_id"]):
                raise VendorBatchStopped("production reply lacks exact single-use lineage")
            previous[0] = record
            previous[1] = stage
            if stage != "returned":
                continue
            self.lineage.pop(decode)
            if payload["error"]:
                raise VendorBatchStopped("the vendor returned a production error")
            if payload["action"] != 8:
                continue
            if "stack_count_raw" in payload:
                # V3 corrects the old interpretation: this is an item stack,
                # not a future-roll counter. Legacy ancestry cannot adopt it.
                raise VendorBatchStopped(
                    "automatic quantity ancestry requires verified order receipts")
            item, kind = payload["item"]
            if item in self.baseline:
                continue
            physical_count = payload["remaining_count_raw"]
            if (type(item) is not int or not 0 < item < 2**32 or kind != 40
                    or payload["template"] != self.spec.template
                    or type(physical_count) is not int
                    or not 0 < physical_count <= self.spec.quantity):
                raise VendorBatchStopped("production reply changed the item or quantity")
            remaining = physical_count - 1
            old = self.rolls.get(item)
            if old and old["future_items"] != remaining:
                raise VendorBatchStopped("a produced item changed its remaining count")
            self.rolls[item] = dict(payload, future_items=remaining)
            if len(self.rolls) > self.admission["planned_items"]:
                raise VendorBatchStopped("production exceeded the funded item quota")
        if len(self.lineage) > 64:
            raise VendorBatchStopped("production decode tickets exceed their bound")

    def observe(self, state: Snapshot, counts, *, kept_item: int = 0):
        state.encode()
        if (_owner(state) != _owner(self.initial) or len(state.slots) < self.capacity
                or state.revision < self.revision or not _counts(counts, state)
                or not self.baseline <= _items(state)):
            raise VendorBatchStopped("quantity production ownership or capacity changed")
        if any(slot.item and count < 1 for slot, count in zip(state.slots, counts, strict=True)):
            raise VendorBatchStopped("occupied production slot lacks its current item count")
        # Both the slot and V2 reply count include the current item. Internal
        # ancestry tracks future items; retain the raw evidence unchanged.
        slots = {slot.item: (slot, count - 1) for slot, count in
                 zip(state.slots, counts, strict=True) if slot.item}
        if any(item in slots for order in self.orders for item in order["path"][:-1]):
            raise VendorBatchStopped("an earlier quantity item reappeared in production")
        if any(order["finished"] and order["current"] in slots for order in self.orders):
            raise VendorBatchStopped("a finished quantity order reappeared")
        additions = _items(state) - self.baseline - set(self.items)
        missing = [order for order in self.orders
                   if not order["finished"] and order["current"] not in slots]
        assignments = []
        for item in additions:
            slot, count = slots[item]
            roll = self.rolls.get(item)
            candidates = [order for order in missing if order["remaining"] == count + 1
                          and (order["entry"] == slot.entry
                               or kept_item == order["current"] and len(missing) == 1)]
            if (len(candidates) != 1 or roll is None
                    or roll["future_items"] != count):
                raise VendorBatchStopped("a new order item lacks observed batch ancestry")
            order = candidates[0]
            if any(assigned is order for assigned, _, _, _ in assignments):
                raise VendorBatchStopped("multiple arrivals claim the same quantity order")
            assignments.append((order, item, slot.entry, count))
        for order, item, entry, count in assignments:
            self.items[item] = dict(order=self.orders.index(order), remaining=count)
            order.update(current=item, entry=entry, remaining=count)
            order["path"].append(item)
        for order in self.orders:
            if order["finished"]:
                continue
            item = order["current"]
            if item in slots:
                slot, count = slots[item]
                if count != order["remaining"]:
                    raise VendorBatchStopped("remaining count changed without a new item")
                order["entry"] = slot.entry
                roll = self.rolls.get(item)
                if roll is not None and roll["future_items"] != count:
                    raise VendorBatchStopped("queue and received order counts disagree")
            elif order["remaining"] == 0 and item in self.inventory_confirmed:
                order["finished"] = True
            elif order["remaining"] > 0 and item in self.inventory_confirmed:
                # A Keep may be followed by a separate arrival callback. Wait;
                # an empty slot never authorizes replacement crafting.
                continue
            else:
                # Automatic movement may precede the displayed Inventory refresh.
                # Preserve the missing item until positive inventory proof arrives.
                continue
        if len(self.items) > self.admission["planned_items"]:
            raise VendorBatchStopped("quantity production exceeded its immutable quota")
        self.capacity, self.revision = len(state.slots), state.revision
        self.visible = _items(state) - self.baseline

    def confirm_inventory(self, items):
        if (type(items) is not list or len(items) > 512
                or any(type(item) is not int or not 0 < item < 2**32 for item in items)
                or len(set(items)) != len(items)):
            raise VendorBatchStopped("invalid positive inventory evidence")
        self.inventory_confirmed.update(set(items) & set(self.items))

    def keep_candidate(self, state):
        for slot in state.slots:
            if (slot.item in self.items and slot.state == 2
                    and slot.item not in self.inventory_confirmed and slot.item in self.rolls):
                return slot.item
        return None

    @property
    def complete(self):
        return (len(self.items) == self.admission["planned_items"]
                and set(self.items) <= self.inventory_confirmed
                and not self.visible
                and all(order["finished"] and len(order["path"]) == self.spec.quantity
                        for order in self.orders))

    def summary(self):
        return dict(generated=len(self.items), kept=len(self.inventory_confirmed),
                    planned_items=self.admission["planned_items"], capacity=self.capacity,
                    complete=self.complete)
