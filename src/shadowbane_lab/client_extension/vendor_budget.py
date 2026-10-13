"""Immutable whole-batch cost/capacity boundary, separate from item identities."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .vendor_wire import NativeOrderBudget, Snapshot, uint


@dataclass(frozen=True, slots=True)
class VendorBatchBudget:
    owner: tuple[int, int, int, int]  # scene, root, building, vendor
    recipe: tuple[int, int, int, int]  # template, table, quantity per slot, multiple
    capacity: int
    occupied: tuple[int, ...]
    costs_per_slot: tuple[tuple[int, int], ...]

    def __post_init__(self):
        if (type(self.owner) is not tuple or len(self.owner) != 4
                or type(self.recipe) is not tuple or len(self.recipe) != 4
                or any(not uint(value, 64 if i == 0 else 32, "budget owner")
                       for i, value in enumerate(self.owner))
                or any(not uint(value, 32, "recipe key") for value in self.recipe[:2])
                or type(self.recipe[2]) is not int or not 1 <= self.recipe[2] <= 10
                or type(self.recipe[3]) is not int or self.recipe[3] not in (0, 1)
                or type(self.capacity) is not int or not 1 <= self.capacity <= 16
                or type(self.occupied) is not tuple
                or len(self.occupied) > self.capacity
                or any(not uint(value, 32, "occupied item") for value in self.occupied)
                or tuple(sorted(set(self.occupied))) != self.occupied
                or type(self.costs_per_slot) is not tuple or not self.costs_per_slot
                or len(self.costs_per_slot) > 32):
            raise ValueError("invalid vendor batch budget")
        for pair in self.costs_per_slot:
            if (type(pair) is not tuple or len(pair) != 2
                    or not uint(pair[0], 32, "resource")
                    or type(pair[1]) is not int or not 0 < pair[1] <= 2**31 - 1
                    or pair[1] * self.free_slots > 2**31 - 1):
                raise ValueError("invalid vendor batch resource requirement")
        if (tuple(sorted(self.costs_per_slot)) != self.costs_per_slot
                or len({pair[0] for pair in self.costs_per_slot}) != len(self.costs_per_slot)):
            raise ValueError("duplicate or noncanonical batch resources")

    @property
    def free_slots(self) -> int:
        return self.capacity - len(self.occupied)

    @property
    def total_items(self) -> int:
        return self.free_slots * self.recipe[2]

    @property
    def total_costs(self) -> dict[int, int]:
        # The owned recipe price already includes quantity and native rounding.
        return {key: amount * self.free_slots for key, amount in self.costs_per_slot}

    @property
    def native_budget(self) -> NativeOrderBudget:
        if len(self.costs_per_slot) != 1 or not self.free_slots:
            raise ValueError("native quantity orders require one funded resource")
        resource, cost = self.costs_per_slot[0]
        return NativeOrderBudget(self.free_slots, resource, cost)

    @classmethod
    def from_snapshot(cls, state: Snapshot, costs: dict[int, int]) -> VendorBatchBudget:
        state.encode()
        if (not state.recipe or state.mode != 1
                or state.prefix != 3362971591 or state.suffix != state.prefix
                or type(costs) is not dict):
            raise ValueError("an owned random recipe and displayed costs are required")
        return cls((state.scene, state.root, state.building, state.vendor),
                   (state.item_template, state.table, state.quantity, state.multiple),
                   len(state.slots), tuple(sorted(slot.item for slot in state.slots if slot.item)),
                   tuple(sorted(costs.items())))

    def matches(self, state: Snapshot) -> bool:
        state.encode()
        return bool(state.recipe and state.mode == 1
                    and state.prefix == state.suffix == 3362971591
                    and self.owner == (state.scene, state.root, state.building, state.vendor)
                    and self.recipe == (state.item_template, state.table,
                                        state.quantity, state.multiple)
                    and self.capacity == len(state.slots)
                    and self.occupied == tuple(sorted(s.item for s in state.slots if s.item)))

    def as_dict(self) -> dict:
        return dict(schema_version=1, owner=list(self.owner), recipe=list(self.recipe),
                    capacity=self.capacity, occupied=list(self.occupied),
                    costs_per_slot=[list(pair) for pair in self.costs_per_slot],
                    total_items=self.total_items,
                    total_costs={str(key): value for key, value in self.total_costs.items()})

    @classmethod
    def from_dict(cls, value: dict) -> VendorBatchBudget:
        try:
            result = cls(tuple(value["owner"]), tuple(value["recipe"]), value["capacity"],
                         tuple(value["occupied"]), tuple(tuple(p) for p in value["costs_per_slot"]))
            if json.dumps(value, sort_keys=True) != json.dumps(result.as_dict(), sort_keys=True):
                raise ValueError("noncanonical batch budget")
            return result
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("invalid saved vendor batch budget") from exc

    @property
    def canonical_digest(self) -> str:
        raw = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()
