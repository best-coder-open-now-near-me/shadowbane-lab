"""Exact building/hireling window commands and correlated native observations."""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass, fields
from enum import IntEnum

from .movement_wire import Host, request_bytes
from .vendor_wire import Outcome, uint

MAGIC, READY, IN_FLIGHT, UNRESOLVED = 0x57424E33, 1, 2, 4
# The native controller waits 60 seconds; allow its terminal receipt to arrive.
RESPONSE_WAIT_SECONDS = 65
_SNAPSHOT = struct.Struct("<QQ20I")
_COMMAND = struct.Struct("<16sQ16s96s4I424s")
_RECEIPT = struct.Struct("<16s16sQII96s16sI220s")


class Verb(IntEnum):
    INSPECT = 13
    BUILDING = 14
    VENDOR = 15
    GUARD = 16
    WAREHOUSE = 22


@dataclass(frozen=True, slots=True)
class Snapshot:
    scene: int = 0
    revision: int = 0
    root: int = 0
    manager: int = 0
    front_hud: int = 0
    mode: int = 0
    building_hud: int = 0
    vendor_hud: int = 0
    selected_entry: int = 0
    visible: int = 0
    building_id: int = 0
    building_type: int = 0
    vendor_id: int = 0
    vendor_type: int = 0
    initialized: int = 0
    capacity: int = 0
    occupied: int = 0
    offline: int = 0
    warehouse_hud: int = 0
    warehouse_object: int = 0
    warehouse_id: int = 0
    warehouse_type: int = 0

    @property
    def empty(self) -> bool:
        return self == Snapshot()

    def owns_building(self, building_id: int) -> bool:
        return bool(not self.offline and self.building_id == building_id
                    and self.building_type == 8 and self.visible & 1)

    def opened(self, building_id: int, vendor_id: int = 0, *, hireling_type: int = 42) -> bool:
        return bool(
            not self.offline
            and self.building_id == building_id
            and self.building_type == 8
            and (
                self.visible & 2
                and self.front_hud == self.vendor_hud
                and self.vendor_id == vendor_id
                and self.vendor_type == hireling_type
                and hireling_type in (37, 42)
                if vendor_id
                else self.visible & 1 and self.front_hud == self.building_hud
            )
        )

    def warehouse_opened(self, building_id: int, source_id: int) -> bool:
        return bool(
            not self.offline and self.building_id == building_id and self.building_type == 8
            and self.front_hud == self.warehouse_hud
            and self.warehouse_hud and self.warehouse_object
            and self.warehouse_id == source_id and source_id and self.warehouse_type == 42
        )

    def encode(self) -> bytes:
        values = [getattr(self, field.name) for field in fields(self)]
        for index, value in enumerate(values):
            uint(value, 64 if index < 2 else 32, "navigation field")
        if self.empty:
            return bytes(96)
        if (
            not all((self.scene, self.revision, self.root, self.manager))
            or self.mode > 64
            or self.visible > 3
            or self.initialized > 1
            or self.offline > 1
            or not 0 <= self.occupied <= self.capacity <= 128
            or (self.building_id, self.building_type) != (0, 0)
            and not (self.building_id and self.building_type == 8)
            or (self.vendor_id, self.vendor_type) != (0, 0)
            and not (self.vendor_id and self.vendor_type in (37, 42))
            or self.vendor_id
            and not self.selected_entry
            or bool(
                self.warehouse_hud or self.warehouse_object
                or self.warehouse_id or self.warehouse_type
            )
            and not (
                self.warehouse_hud and self.warehouse_object
                and self.warehouse_id and self.warehouse_type == 42
            )
            or self.visible & 1
            and not (self.building_hud and self.initialized and self.mode == 6 and self.building_id)
            or self.visible & 2
            and not (
                self.vendor_hud and self.selected_entry and self.vendor_id and self.building_id
            )
        ):
            raise ValueError("invalid vendor navigation snapshot")
        return _SNAPSHOT.pack(*values)

    @classmethod
    def decode(cls, data: bytes) -> Snapshot:
        if len(data) != 96:
            raise ValueError("invalid navigation snapshot size")
        values = _SNAPSHOT.unpack(data)
        result = cls(*values)
        result.encode()
        return result


@dataclass(frozen=True, slots=True)
class Command:
    host: Host
    window: int
    request_key: str
    expected: Snapshot = Snapshot()
    building_id: int = 0
    vendor_id: int = 0

    def encode(self, verb: Verb) -> bytes:
        verb = Verb(verb)
        if not uint(self.window, 32, "window"):
            raise ValueError("window is required")
        uint(self.building_id, 32, "building")
        uint(self.vendor_id, 32, "vendor")
        if verb == Verb.INSPECT:
            if not self.expected.empty or self.building_id or self.vendor_id:
                raise ValueError("inspection cannot carry action state")
        elif self.expected.empty or self.expected.offline or not self.building_id:
            raise ValueError("opening needs an online navigation snapshot and building")
        elif verb == Verb.BUILDING and self.vendor_id:
            raise ValueError("building opening cannot carry a vendor")
        elif verb in (Verb.VENDOR, Verb.GUARD, Verb.WAREHOUSE) and (
            not self.vendor_id or not self.expected.owns_building(self.building_id)
        ):
            raise ValueError("hireling opening needs its active building window")
        return _COMMAND.pack(
            self.host.encode(),
            self.window,
            request_bytes(self.request_key),
            self.expected.encode(),
            self.building_id,
            8 if self.building_id else 0,
            self.vendor_id,
            (37 if verb == Verb.GUARD else 42) if self.vendor_id else 0,
            bytes(424),
        )

    @classmethod
    def decode(cls, data: bytes, verb: Verb) -> Command:
        if len(data) != 576:
            raise ValueError("invalid navigation command size")
        host, window, key, state, building, building_type, target, target_type, padding = (
            _COMMAND.unpack(data)
        )
        if any(padding):
            raise ValueError("nonzero navigation command padding")
        result = cls(Host.decode(host), window, str(uuid.UUID(bytes=key)),
                     Snapshot.decode(state), building, target)
        # Re-encoding also checks both key types against the requested verb.
        if result.encode(verb) != data:
            raise ValueError("noncanonical navigation command")
        return result

    def opened(self, verb: Verb, state: Snapshot) -> bool:
        self.encode(verb)
        state.encode()
        before = self.expected
        if state.empty or (state.scene, state.root, state.manager) != (
            before.scene, before.root, before.manager
        ):
            return False
        if verb == Verb.WAREHOUSE:
            return state.warehouse_opened(self.building_id, self.vendor_id)
        return verb in (Verb.BUILDING, Verb.GUARD, Verb.VENDOR) and state.opened(
            self.building_id, self.vendor_id, hireling_type=37 if verb == Verb.GUARD else 42
        )


@dataclass(frozen=True, slots=True)
class Receipt:
    request_key: str
    host: Host
    window: int
    outcome: Outcome
    flags: int
    snapshot: Snapshot
    transition_request: str | None = None

    def encode(self) -> bytes:
        data = _RECEIPT.pack(
            request_bytes(self.request_key), self.host.encode(), self.window,
            self.outcome, self.flags, self.snapshot.encode(),
            request_bytes(self.transition_request) if self.transition_request else bytes(16),
            MAGIC, bytes(220),
        )
        if type(self).decode(data) != self:
            raise ValueError("noncanonical navigation receipt")
        return data

    @classmethod
    def decode(cls, data: bytes) -> Receipt:
        if len(data) != 384:
            raise ValueError("invalid navigation receipt size")
        key, host, window, outcome, flags, state, transition, magic, padding = _RECEIPT.unpack(data)
        if magic != MAGIC or flags & ~7 or any(padding) or not 0 < window < 2**32:
            raise ValueError("invalid navigation receipt")
        request = str(uuid.UUID(bytes=key))
        request_bytes(request)
        snapshot = Snapshot.decode(state)
        if flags & READY and (
            flags & (IN_FLIGHT | UNRESOLVED) or snapshot.empty or snapshot.offline
        ):
            raise ValueError("contradictory navigation readiness")
        return cls(
            request,
            Host.decode(host),
            window,
            Outcome(outcome),
            flags,
            snapshot,
            str(uuid.UUID(bytes=transition)) if any(transition) else None,
        )
