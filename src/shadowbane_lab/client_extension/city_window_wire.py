"""Typed City Command window operations; local opening is not a town roster receipt."""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass, fields
from enum import IntEnum

from .movement_wire import Host, request_bytes
from .vendor_wire import Outcome, uint

MAGIC, READY = 0x57424331, 1
_SNAPSHOT = struct.Struct("<QQ8I16s")
_COMMAND = struct.Struct("<16sQ16s64s472s")
_RECEIPT = struct.Struct("<16s16sQII64sI268s")


class Verb(IntEnum):
    INSPECT = 11
    OPEN = 12


@dataclass(frozen=True, slots=True)
class Snapshot:
    scene: int = 0
    revision: int = 0
    root: int = 0
    manager: int = 0
    hud: int = 0
    active_manager: int = 0
    mode: int = 0
    loading: int = 0
    building_count: int = 0
    visible: int = 0

    @property
    def empty(self) -> bool:
        return self == Snapshot()

    @property
    def opened(self) -> bool:
        return bool(self.visible and self.active_manager == self.manager)

    def encode(self) -> bytes:
        values = [getattr(self, f.name) for f in fields(self)]
        for i, value in enumerate(values):
            uint(value, 64 if i < 2 else 32, "city window field")
        if self.empty:
            return bytes(64)
        if (
            not all((self.scene, self.revision, self.root, self.manager))
            or self.mode > 2 or self.loading > 1 or self.visible > 1
            or self.building_count > 512
            or self.visible and not (self.hud and self.mode)
            or not self.hud and (self.visible or self.loading)
        ):
            raise ValueError("invalid city window snapshot")
        return _SNAPSHOT.pack(*values, bytes(16))

    @classmethod
    def decode(cls, data: bytes) -> Snapshot:
        if len(data) != 64:
            raise ValueError("invalid city window snapshot size")
        *values, padding = _SNAPSHOT.unpack(data)
        if any(padding):
            raise ValueError("nonzero city window snapshot padding")
        result = cls(*values)
        result.encode()
        return result


@dataclass(frozen=True, slots=True)
class Command:
    host: Host
    window: int
    request_key: str
    expected: Snapshot = Snapshot()

    def encode(self, verb: Verb) -> bytes:
        verb = Verb(verb)
        if not uint(self.window, 32, "window"):
            raise ValueError("window is required")
        if verb == Verb.INSPECT and not self.expected.empty:
            raise ValueError("city inspection cannot carry action state")
        if verb == Verb.OPEN and (self.expected.empty or self.expected.loading):
            raise ValueError("opening needs a current idle city window snapshot")
        return _COMMAND.pack(
            self.host.encode(), self.window, request_bytes(self.request_key),
            self.expected.encode(), bytes(472),
        )


@dataclass(frozen=True, slots=True)
class Receipt:
    request_key: str
    host: Host
    window: int
    outcome: Outcome
    flags: int
    snapshot: Snapshot

    @classmethod
    def decode(cls, data: bytes) -> Receipt:
        if len(data) != 384:
            raise ValueError("invalid city window receipt size")
        key, host, window, outcome, flags, state, magic, padding = _RECEIPT.unpack(data)
        if magic != MAGIC or flags & ~READY or any(padding) or not 0 < window < 2**32:
            raise ValueError("invalid city window receipt")
        request = str(uuid.UUID(bytes=key))
        request_bytes(request)
        snapshot = Snapshot.decode(state)
        if flags & READY and (snapshot.empty or snapshot.loading):
            raise ValueError("contradictory city window readiness")
        return cls(request, Host.decode(host), window, Outcome(outcome), flags, snapshot)
