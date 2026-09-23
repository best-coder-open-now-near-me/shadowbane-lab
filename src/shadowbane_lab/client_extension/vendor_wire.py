"""Vendor payloads in the schema-3 transport envelope; no movement grants."""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass, fields
from enum import IntEnum

from .movement_wire import Host, request_bytes

MAGIC = 0x57425631
READY, IN_FLIGHT, UNRESOLVED = 1, 2, 4
_SNAPSHOT = struct.Struct("<QQ16I")
_SLOT = struct.Struct("<III")
_COMMAND = struct.Struct("<16sQ16s288sI244s")
_RECEIPT = struct.Struct("<16s16sQII288sII16s24s")


class Verb(IntEnum):
    INSPECT = 8
    CREATE = 9
    KEEP = 10


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
class Command:
    host: Host
    window: int
    request_key: str
    expected: Snapshot = Snapshot()
    item: int = 0

    def encode(self, verb: Verb) -> bytes:
        verb = Verb(verb)
        if not uint(self.window, 32, "window"):
            raise ValueError("window is required")
        uint(self.item, 32, "item")
        if verb == Verb.INSPECT:
            if not self.expected.empty or self.item:
                raise ValueError("inspect cannot carry action arguments")
        elif self.expected.empty or (
            verb == Verb.CREATE and (self.item or not self.expected.random_scepter)
        ) or (verb == Verb.KEEP and not self.item):
            raise ValueError("invalid vendor action arguments")
        return _COMMAND.pack(
            self.host.encode(), self.window, request_bytes(self.request_key),
            self.expected.encode(), self.item, bytes(244),
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

    @classmethod
    def decode(cls, data: bytes) -> Receipt:
        request, host, window, outcome, flags, snapshot, magic, item, transition, pad = (
            _RECEIPT.unpack(data)
        )
        if magic != MAGIC or flags & ~7 or any(pad) or not window or window >= 2**32:
            raise ValueError("invalid vendor receipt")
        key = str(uuid.UUID(bytes=request))
        request_bytes(key)
        state = Snapshot.decode(snapshot)
        if flags & READY and (state.empty or flags & (IN_FLIGHT | UNRESOLVED)):
            raise ValueError("contradictory vendor readiness")
        transition_key = str(uuid.UUID(bytes=transition)) if any(transition) else None
        if bool(item) != bool(transition_key):
            raise ValueError("incomplete vendor transition identity")
        return cls(key, Host.decode(host), window, Outcome(outcome), flags, state,
                   item, transition_key)
