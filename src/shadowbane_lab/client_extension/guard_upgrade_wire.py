"""Exact funded guard upgrades; submission and observed acceptance stay distinct."""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass
from enum import IntEnum

from .movement_wire import Host, request_bytes
from .vendor_navigation_wire import Snapshot as Navigation
from .vendor_wire import Outcome, uint

MAGIC, READY, IN_FLIGHT, UNRESOLVED, REOPENED = 0x57424733, 1, 2, 4, 8
_FIELDS = struct.Struct("<8I")
_COMMAND = struct.Struct("<16sQ16s128s408s")
_RECEIPT = struct.Struct("<16s16sQII128s16sI188s")


class Verb(IntEnum):
    INSPECT = 17
    UPGRADE = 18


@dataclass(frozen=True, slots=True)
class Snapshot:
    navigation: Navigation = Navigation()
    rank: int = 0
    cost: int = 0
    funds: int = 0
    upgrading: int = 0
    can_upgrade: int = 0
    control_flags: int = 0
    upgrade_control: int = 0
    progress_control: int = 0

    @property
    def empty(self) -> bool:
        return self == Snapshot()

    @property
    def eligible(self) -> bool:
        return bool(
            not self.empty
            and not self.upgrading
            and self.can_upgrade
            and self.cost > 0
            and self.funds >= self.cost
            and self.control_flags == 3
        )

    def encode(self) -> bytes:
        values = (
            self.rank,
            self.cost,
            self.funds,
            self.upgrading,
            self.can_upgrade,
            self.control_flags,
            self.upgrade_control,
            self.progress_control,
        )
        for value in values:
            uint(value, 32, "guard field")
        navigation = self.navigation.encode()
        if self.empty:
            return bytes(128)
        n = self.navigation
        if (
            n.empty
            or n.offline
            or n.visible != 3
            or n.vendor_type != 37
            or not 0 < self.rank < 2**32 - 1
            or self.cost > 2**31 - 1
            or self.funds > 2**31 - 1
            or self.upgrading > 1
            or self.can_upgrade > 1
            or self.control_flags > 7
            or not self.upgrade_control
            or not self.progress_control
            or self.upgrade_control == self.progress_control
        ):
            raise ValueError("invalid guard upgrade snapshot")
        return navigation + _FIELDS.pack(*values)

    @classmethod
    def decode(cls, data: bytes) -> Snapshot:
        if len(data) != 128:
            raise ValueError("invalid guard snapshot size")
        result = cls(Navigation.decode(data[:96]), *_FIELDS.unpack(data[96:]))
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
        state = self.expected.encode()
        if (verb == Verb.INSPECT and not self.expected.empty) or (
            verb == Verb.UPGRADE and not self.expected.eligible
        ):
            raise ValueError("guard command needs an eligible funded snapshot")
        return _COMMAND.pack(
            self.host.encode(), self.window, request_bytes(self.request_key), state, bytes(408)
        )

    @classmethod
    def decode(cls, data: bytes, verb: Verb) -> Command:
        if len(data) != 576:
            raise ValueError("invalid guard command size")
        host, window, request, state, padding = _COMMAND.unpack(data)
        if any(padding):
            raise ValueError("nonzero guard command padding")
        result = cls(
            Host.decode(host), window, str(uuid.UUID(bytes=request)), Snapshot.decode(state)
        )
        if result.encode(verb) != data:
            raise ValueError("noncanonical guard command")
        return result


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
        raw = _RECEIPT.pack(
            request_bytes(self.request_key),
            self.host.encode(),
            self.window,
            self.outcome,
            self.flags,
            self.snapshot.encode(),
            request_bytes(self.transition_request) if self.transition_request else bytes(16),
            MAGIC,
            bytes(188),
        )
        if type(self).decode(raw) != self:
            raise ValueError("noncanonical guard receipt")
        return raw

    @classmethod
    def decode(cls, data: bytes) -> Receipt:
        if len(data) != 384:
            raise ValueError("invalid guard receipt size")
        key, host, window, outcome, flags, state, transition, magic, padding = _RECEIPT.unpack(data)
        if magic != MAGIC or flags & ~15 or any(padding) or not 0 < window < 2**32:
            raise ValueError("invalid guard receipt")
        if flags & REOPENED and not any(transition):
            raise ValueError("guard revisit lacks transaction identity")
        request = str(uuid.UUID(bytes=key))
        request_bytes(request)
        snapshot = Snapshot.decode(state)
        if flags & READY and (flags & (IN_FLIGHT | UNRESOLVED) or snapshot.empty):
            raise ValueError("contradictory guard readiness")
        return cls(
            request,
            Host.decode(host),
            window,
            Outcome(outcome),
            flags,
            snapshot,
            str(uuid.UUID(bytes=transition)) if any(transition) else None,
        )
