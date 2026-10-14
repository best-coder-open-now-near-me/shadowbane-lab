"""Vendor payloads in the schema-3 transport envelope; no movement grants."""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass, fields
from enum import IntEnum

from .movement_wire import Host, request_bytes

MAGIC = 0x57425631
ORDERS_MAGIC = 0x57425632
RECYCLE_MAGIC = 0x57425231
READY, IN_FLIGHT, UNRESOLVED = 1, 2, 4
_SNAPSHOT = struct.Struct("<QQ16I")
_SLOT = struct.Struct("<III")
_COMMAND = struct.Struct("<16sQ16s288sI244s")
_RECEIPT = struct.Struct("<16s16sQII288sII16s24s")
_ORDER_BUDGET = struct.Struct("<6I")
_RECYCLE_BATCH = struct.Struct("<32sII48I12s")
_RECYCLE_COMPLETION = struct.Struct("<QQII")


class Verb(IntEnum):
    INSPECT = 8
    CREATE = 9
    KEEP = 10
    CREATE_RANDOM = 32
    INSPECT_RANDOM = 33
    INSPECT_ORDERS = 56
    CREATE_ORDERS = 61
    INSPECT_RECYCLE = 62
    RECYCLE = 63


class Outcome(IntEnum):
    OBSERVED = 0
    SUBMITTED = 1
    STALE = 2
    UNAVAILABLE = 3
    INVALID = 4
    PENDING = 5
    UNCERTAIN = 6
    EXHAUSTED = 7


def uint(value: int, bits: int, label: str) -> int:
    if type(value) is not int or not 0 <= value < 2**bits:
        raise ValueError(f"{label} must be uint{bits}")
    return value


@dataclass(frozen=True, slots=True)
class Slot:
    entry: int
    item: int = 0
    state: int = 0

    def encode(self) -> bytes:
        for value in (self.entry, self.item, self.state):
            uint(value, 32, "slot field")
        if not self.entry or self.state > 2 or ((self.state == 0) != (self.item == 0)):
            raise ValueError("invalid vendor slot")
        return _SLOT.pack(self.entry, self.item, self.state)


@dataclass(frozen=True, slots=True)
class Snapshot:
    scene: int = 0
    revision: int = 0
    root: int = 0
    manager: int = 0
    menu: int = 0
    recipe: int = 0
    inventory: int = 0
    hireling: int = 0
    building: int = 0
    vendor: int = 0
    item_template: int = 0
    prefix: int = 0
    suffix: int = 0
    mode: int = 0
    table: int = 0
    quantity: int = 0
    multiple: int = 0
    slots: tuple[Slot, ...] = ()

    @property
    def empty(self) -> bool:
        return self == Snapshot()

    @property
    def free_slots(self) -> int:
        return sum(slot.state == 0 for slot in self.slots)

    @property
    def random_scepter(self) -> bool:
        return bool(
            self.recipe and self.item_template == 26990
            and self.prefix == self.suffix == 3362971591 and self.mode == 1
            and self.table == 12 and self.quantity == 1 and self.multiple in (0, 1)
        )

    @property
    def random_single(self) -> bool:
        return bool(
            self.recipe and self.item_template and self.table and self.mode == 1
            and self.prefix == self.suffix == 3362971591
            and self.quantity == 1 and self.multiple == 0
        )

    @property
    def random_order(self) -> bool:
        return bool(self.recipe and self.item_template and self.table and self.mode == 1
                    and self.prefix == self.suffix == 3362971591
                    and 2 <= self.quantity <= 10 and self.multiple == 1)

    def encode(self) -> bytes:
        if type(self.slots) is not tuple or any(type(s) is not Slot for s in self.slots):
            raise ValueError("slots must be an immutable tuple of Slot values")
        values = [getattr(self, f.name) for f in fields(self) if f.name != "slots"]
        for i, value in enumerate(values):
            uint(value, 64 if i < 2 else 32, "snapshot field")
        if self.empty:
            return bytes(288)
        if (
            not all((self.scene, self.revision, self.root, self.manager, self.menu,
                     self.hireling, self.building, self.vendor))
            or not 1 <= len(self.slots) <= 16
            or len({slot.entry for slot in self.slots}) != len(self.slots)
            or len({s.item for s in self.slots if s.item}) != sum(bool(s.item) for s in self.slots)
        ):
            raise ValueError("invalid vendor snapshot")
        return (
            _SNAPSHOT.pack(*values, len(self.slots))
            + b"".join(slot.encode() for slot in self.slots)
            + bytes((16 - len(self.slots)) * 12 + 16)
        )

    @classmethod
    def decode(cls, data: bytes) -> Snapshot:
        if len(data) != 288:
            raise ValueError("invalid vendor snapshot size")
        if not any(data):
            return cls()
        values = _SNAPSHOT.unpack(data[:80])
        count = values[-1]
        if count > 16 or any(data[80 + count * 12:]):
            raise ValueError("invalid vendor slot count or padding")
        slots = tuple(Slot(*_SLOT.unpack_from(data, 80 + i * 12)) for i in range(count))
        out = cls(*values[:-1], slots)
        out.encode()
        return out


@dataclass(frozen=True, slots=True)
class NativeOrderBudget:
    orders: int
    resource: int
    cost_per_order: int

    def encode(self, quantity: int) -> bytes:
        if (type(self.orders) is not int or not 1 <= self.orders <= 16
                or not uint(self.resource, 32, "order resource")
                or type(self.cost_per_order) is not int or not 0 < self.cost_per_order <= 2**31 - 1
                or self.orders * self.cost_per_order > 2**31 - 1
                or type(quantity) is not int or not 2 <= quantity <= 10):
            raise ValueError("invalid native whole-batch order budget")
        return _ORDER_BUDGET.pack(1, self.orders, quantity, self.resource,
                                  self.cost_per_order, self.orders * self.cost_per_order)


@dataclass(frozen=True, slots=True)
class NativeRecycleBatch:
    items: tuple[int, ...]
    fingerprint: str
    gold_before: int
    refund: int

    def encode(self) -> bytes:
        if (type(self.items) is not tuple or not 0 < len(self.items) <= 48
                or any(type(item) is not int or not 0 < item < 2**32 for item in self.items)
                or tuple(sorted(set(self.items))) != self.items
                or type(self.fingerprint) is not str or len(self.fingerprint) != 64
                or type(self.gold_before) is not int or not 0 <= self.gold_before <= 2**31 - 1
                or type(self.refund) is not int or not 0 < self.refund <= 2**31 - 1
                or self.gold_before + self.refund > 2**31 - 1):
            raise ValueError("invalid native recycle batch")
        digest = bytes.fromhex(self.fingerprint)
        if len(digest) != 32 or not any(digest) or digest.hex() != self.fingerprint:
            raise ValueError("recycle fingerprint must be a canonical nonzero SHA-256")
        return _RECYCLE_BATCH.pack(digest, self.gold_before, self.refund,
                                   *self.items, *([0] * (48 - len(self.items))), bytes(12))


@dataclass(frozen=True, slots=True)
class NativeRecycleCompletion:
    floor: int
    sequence: int
    refund: int
    gold_after: int


@dataclass(frozen=True, slots=True)
class Command:
    host: Host
    window: int
    request_key: str
    expected: Snapshot = Snapshot()
    item: int = 0
    batch_key: str | None = None
    order_budget: NativeOrderBudget | None = None
    recycle_batch: NativeRecycleBatch | None = None

    def encode(self, verb: Verb) -> bytes:
        verb = Verb(verb)
        if not uint(self.window, 32, "window"):
            raise ValueError("window is required")
        uint(self.item, 32, "item")
        if verb in (Verb.INSPECT, Verb.INSPECT_RANDOM, Verb.INSPECT_ORDERS, Verb.INSPECT_RECYCLE):
            if not self.expected.empty or self.item:
                raise ValueError("inspect cannot carry action arguments")
        elif self.expected.empty or (
            verb == Verb.CREATE and (self.item or not self.expected.random_scepter)
        ) or (
            verb == Verb.CREATE_RANDOM and (self.item or not self.expected.random_single)
        ) or (
            verb == Verb.CREATE_ORDERS and (self.item or not self.expected.random_order)
        ) or (verb == Verb.KEEP and not self.item) or (
            verb == Verb.RECYCLE and (
                not self.expected.inventory
                or any(slot.item or slot.state for slot in self.expected.slots))
        ):
            raise ValueError("invalid vendor action arguments")
        if verb == Verb.CREATE_ORDERS:
            if (type(self.batch_key) is not str or type(self.order_budget) is not NativeOrderBudget
                    or self.recycle_batch is not None):
                raise ValueError("quantity-order Create requires a canonical batch identity")
            padding = (request_bytes(self.batch_key)
                       + self.order_budget.encode(self.expected.quantity)
                       + bytes(204))
        elif verb == Verb.RECYCLE:
            if (type(self.recycle_batch) is not NativeRecycleBatch
                    or self.batch_key is not None or self.order_budget is not None
                    or self.item != len(self.recycle_batch.items)):
                raise ValueError("Recycle requires one exact native batch")
            padding = self.recycle_batch.encode()
        else:
            if (self.batch_key is not None or self.order_budget is not None
                    or self.recycle_batch is not None):
                raise ValueError("batch identity is only valid for quantity-order Create")
            padding = bytes(244)
        return _COMMAND.pack(
            self.host.encode(), self.window, request_bytes(self.request_key),
            self.expected.encode(), self.item, padding,
        )


@dataclass(frozen=True, slots=True)
class Receipt:
    request_key: str
    host: Host
    window: int
    outcome: Outcome
    flags: int
    snapshot: Snapshot
    transition_item: int = 0
    transition_request: str | None = None
    # None identifies a historical v1 receipt; zero raw counts are real values.
    remaining_counts: tuple[int, ...] | None = None
    recycle_completion: NativeRecycleCompletion | None = None

    @classmethod
    def decode(cls, data: bytes) -> Receipt:
        request, host, window, outcome, flags, snapshot, magic, item, transition, pad = (
            _RECEIPT.unpack(data)
        )
        if (magic not in (MAGIC, ORDERS_MAGIC, RECYCLE_MAGIC)
                or flags & ~7 or not window or window >= 2**32):
            raise ValueError("invalid vendor receipt")
        key = str(uuid.UUID(bytes=request))
        request_bytes(key)
        state = Snapshot.decode(snapshot)
        if ((magic == MAGIC and any(pad)) or (magic == ORDERS_MAGIC
                and any(pad[len(state.slots):]))):
            raise ValueError("invalid vendor receipt extension")
        counts = tuple(pad[:len(state.slots)]) if magic == ORDERS_MAGIC else None
        if flags & READY and (state.empty or flags & (IN_FLIGHT | UNRESOLVED)):
            raise ValueError("contradictory vendor readiness")
        transition_key = str(uuid.UUID(bytes=transition)) if any(transition) else None
        if bool(item) != bool(transition_key):
            raise ValueError("incomplete vendor transition identity")
        recycling = NativeRecycleCompletion(*_RECYCLE_COMPLETION.unpack(pad)) if (
            magic == RECYCLE_MAGIC) else None
        if recycling is not None:
            if transition_key is None:
                if any(_RECYCLE_COMPLETION.unpack(pad)):
                    raise ValueError("recycle completion lacks a request identity")
            elif (not 0 < item <= 48 or not recycling.floor < recycling.sequence < 2**63
                    or not 0 < recycling.refund <= recycling.gold_after <= 2**31 - 1):
                raise ValueError("invalid native recycle completion")
        return cls(key, Host.decode(host), window, Outcome(outcome), flags, state,
                   item, transition_key, counts, recycling)
