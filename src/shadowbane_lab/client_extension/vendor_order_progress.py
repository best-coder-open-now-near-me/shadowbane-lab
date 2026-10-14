"""Reconcile one server-driven quantity batch with positive inventory evidence."""
from __future__ import annotations

from .vendor_automatic_replies import AutomaticReplies
from .vendor_batch import VendorBatchStopped, _items, _owner
from .vendor_order_batch import _counts, validate_queued_orders
from .vendor_recipe import RandomOrderSpec
from .vendor_wire import Snapshot


class OrderProgress:
    def __init__(self, admission_raw: bytes, character: tuple[int, int]):
        self.admission, self.initial = validate_queued_orders(admission_raw)
        if list(character) != self.admission["character"]:
            raise ValueError("quantity progress changed the admitted character")
        self.spec = RandomOrderSpec.from_dict(self.admission["recipe_spec"])
        self.replies = AutomaticReplies(
            self.initial, self.spec, character, self.admission["planned_orders"],
            self.admission["production_bookmark"]["cursor"]["sequence"],
        )
        self.replies.receive(self.admission["production_records"])
        if self.sequence != self.admission["production_cursor"]["sequence"]:
            raise ValueError("quantity admission history has a gap")
        if not self.replies.admits(self.admission["initial_items"]):
            raise ValueError("quantity admission lacks qualified arrival receipts")
        self.baseline = _items(self.initial)
        self.items = self.rolls = self.replies.items
        self.inventory_confirmed = set()
        self.capacity = self.admission["capacity"]
        self.revision = self.initial.revision
        self.visible = set(self.admission["initial_items"])

    @property
    def sequence(self):
        return self.replies.sequence

    def receive(self, records):
        self.replies.receive(records)

    def expect_keep(self, item):
        self.replies.expect_keep(item)

    def observe(self, state: Snapshot, counts, *, kept_item: int = 0):
        state.encode()
        if (_owner(state) != _owner(self.initial) or len(state.slots) < self.capacity
                or state.revision < self.revision or not _counts(counts, state)
                or not self.baseline <= _items(state)):
            raise VendorBatchStopped("quantity production ownership or capacity changed")
        visible = _items(state) - self.baseline
        if not visible <= set(self.items):
            raise VendorBatchStopped("a visible item lacks a qualified batch receipt")
        if visible & (self.inventory_confirmed | self.replies.removed):
            raise VendorBatchStopped("an earlier automatic production item reappeared")
        if kept_item and kept_item not in self.replies.keep_intents:
            raise VendorBatchStopped("quantity queue carries an unrelated Keep")
        self.capacity, self.revision, self.visible = len(state.slots), state.revision, visible

    def confirm_inventory(self, items):
        if (type(items) is not list or len(items) > 512
                or any(type(item) is not int or not 0 < item < 2**32 for item in items)
                or len(set(items)) != len(items)):
            raise VendorBatchStopped("invalid positive inventory evidence")
        self.inventory_confirmed.update(set(items) & set(self.items))

    def keep_candidate(self, state):
        # The server automatically retains intermediate items. Never race that
        # workflow with Keep; finish only after the full fixed quota is observed
        # and every remaining batch item has both UI and server terminal proof.
        current = [slot for slot in state.slots if slot.item in self.items]
        if (self.replies.failed or len(self.items) != self.admission["planned_items"] or not current
                or any(slot.state != 2 or not self.items[slot.item]["complete"]
                       for slot in current)):
            return None
        return next((slot.item for slot in current
                     if slot.item not in self.inventory_confirmed), None)

    @property
    def complete(self):
        return (not self.replies.failed
                and len(self.items) == self.admission["planned_items"]
                and set(self.items) <= self.inventory_confirmed
                and set(self.items) <= self.replies.removed & self.replies.deposited
                and not self.visible and not self.replies.lineage)

    def summary(self):
        return dict(generated=len(self.items), kept=len(self.inventory_confirmed),
                    planned_items=self.admission["planned_items"], capacity=self.capacity,
                    complete=self.complete)
