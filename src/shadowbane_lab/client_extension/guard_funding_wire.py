"""Typed warehouse withdrawals and structure deposits with two-sided receipts."""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass, fields
from enum import IntEnum

from .movement_wire import Host, request_bytes
from .vendor_wire import Outcome, uint

MAGIC, READY, IN_FLIGHT, UNRESOLVED = 0x57424631, 1, 2, 4
_SNAPSHOT = struct.Struct("<QQ20I")
_COMMAND = struct.Struct("<16sQ16s96sII432s")
_RECEIPT = struct.Struct("<16s16sQII96s16sI220s")


class Verb(IntEnum):
    INSPECT = 19
    TRANSFER = 20


class Direction(IntEnum):
    WAREHOUSE = 1
    STRUCTURE = 2


@dataclass(frozen=True, slots=True)
class Snapshot:
    scene: int = 0
    revision: int = 0
    root: int = 0
    actor: int = 0
    character_id: int = 0
    character_type: int = 0
    manager: int = 0
    hud: int = 0
    source_object: int = 0
    source_id: int = 0
    source_type: int = 0
    direction: int = 0
    resource: int = 0
    balance: int = 0
    reserve: int = 0
    purse: int = 0
    quote: int = 0
    limit: int = 0
    entered: int = 0
    accept: int = 0
    cancel: int = 0
    helper: int = 0

    @property
    def empty(self) -> bool:
        return self == Snapshot()

    def eligible(self, amount: int) -> bool:
        self.encode()
        uint(amount, 32, "transfer amount")
        return bool(
            not self.empty
            and self.quote
            and 0 < amount <= self.limit
            and amount <= 2**31 - 1 - (self.purse if self.direction == 1 else self.balance)
        )

    def encode(self) -> bytes:
        values = [getattr(self, field.name) for field in fields(self)]
        for i, value in enumerate(values):
            uint(value, 64 if i < 2 else 32, "funding snapshot field")
        if self.empty:
            return bytes(96)
        if (
            not all(
                (
                    self.scene,
                    self.revision,
                    self.root,
                    self.actor,
                    self.character_id,
                    self.character_type,
                    self.manager,
                    self.hud,
                    self.source_id,
                )
            )
            or self.direction not in (1, 2)
            or max(self.balance, self.reserve, self.purse) > 2**31 - 1
        ):
            raise ValueError("invalid funding ownership or balance")
        if self.direction == 1:
            if not self.source_object or self.source_type != 42 or not self.resource:
                raise ValueError("invalid warehouse source")
        elif self.source_object or self.source_type != 8 or self.resource or self.reserve:
            raise ValueError("invalid structure destination")
        if not self.quote:
            if any((self.limit, self.entered, self.accept, self.cancel, self.helper)):
                raise ValueError("closed quote retains controls")
        else:
            if (
                self.quote == self.hud
                or not all((self.accept, self.cancel, self.helper))
                or len({self.accept, self.cancel, self.helper}) != 3
                or self.limit > 2**31 - 1
                or self.entered > self.limit
            ):
                raise ValueError("invalid funding quote")
            limit = max(0, self.balance - self.reserve) if self.direction == 1 else self.purse
            if self.limit != limit:
                raise ValueError("stale funding quote")
        return _SNAPSHOT.pack(*values)

    @classmethod
    def decode(cls, data: bytes) -> Snapshot:
        if len(data) != 96:
            raise ValueError("invalid funding snapshot size")
        result = cls(*_SNAPSHOT.unpack(data))
        result.encode()
        return result

    def same_owner(self, other: Snapshot) -> bool:
        return all(
            getattr(self, name) == getattr(other, name)
            for name in (
                "scene",
                "root",
                "actor",
                "character_id",
                "character_type",
                "manager",
                "hud",
                "source_object",
                "source_id",
                "source_type",
                "direction",
                "resource",
            )
        )


@dataclass(frozen=True, slots=True)
class Command:
    host: Host
    window: int
    request_key: str
    expected: Snapshot = Snapshot()
    direction: int = 0
    amount: int = 0

    def encode(self, verb: Verb) -> bytes:
        verb = Verb(verb)
        if not uint(self.window, 32, "window"):
            raise ValueError("window is required")
        uint(self.direction, 32, "funding direction")
        Direction(self.direction)
        uint(self.amount, 32, "funding amount")
        state = self.expected.encode()
        if (verb == Verb.INSPECT and (not self.expected.empty or self.amount)) or (
            verb == Verb.TRANSFER
            and (
                self.direction != self.expected.direction or not self.expected.eligible(self.amount)
            )
        ):
            raise ValueError("funding command requires an eligible quote and amount")
        return _COMMAND.pack(
            self.host.encode(),
            self.window,
            request_bytes(self.request_key),
            state,
            self.direction,
            self.amount,
            bytes(432),
        )

    @classmethod
    def decode(cls, data: bytes, verb: Verb) -> Command:
        if len(data) != 576:
            raise ValueError("invalid funding command size")
        host, window, key, state, direction, amount, padding = _COMMAND.unpack(data)
        if any(padding):
            raise ValueError("nonzero funding command padding")
        result = cls(
            Host.decode(host),
            window,
            str(uuid.UUID(bytes=key)),
            Snapshot.decode(state),
            direction,
            amount,
        )
        if result.encode(verb) != data:
            raise ValueError("noncanonical funding command")
        return result

    def confirmed(self, state: Snapshot) -> bool:
        self.encode(Verb.TRANSFER)
        state.encode()
        before = self.expected
        if (
            state.empty
            or not before.same_owner(state)
            or state.reserve != before.reserve
            or state.quote
        ):
            return False
        delta = -self.amount if self.direction == 1 else self.amount
        return state.balance == before.balance + delta and state.purse == before.purse - delta


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
            request_bytes(self.request_key),
            self.host.encode(),
            self.window,
            self.outcome,
            self.flags,
            self.snapshot.encode(),
            request_bytes(self.transition_request) if self.transition_request else bytes(16),
            MAGIC,
            bytes(220),
        )
        if type(self).decode(data) != self:
            raise ValueError("noncanonical funding receipt")
        return data

    @classmethod
    def decode(cls, data: bytes) -> Receipt:
        if len(data) != 384:
            raise ValueError("invalid funding receipt size")
        key, host, window, outcome, flags, state, transition, magic, padding = _RECEIPT.unpack(data)
        if magic != MAGIC or flags & ~7 or any(padding) or not 0 < window < 2**32:
            raise ValueError("invalid funding receipt")
        key = str(uuid.UUID(bytes=key))
        request_bytes(key)
        snapshot = Snapshot.decode(state)
        if flags & READY and (flags & (IN_FLIGHT | UNRESOLVED) or snapshot.empty):
            raise ValueError("contradictory funding readiness")
        return cls(
            key,
            Host.decode(host),
            window,
            Outcome(outcome),
            flags,
            snapshot,
            str(uuid.UUID(bytes=transition)) if any(transition) else None,
        )
