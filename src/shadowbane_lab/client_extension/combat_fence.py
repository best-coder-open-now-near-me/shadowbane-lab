"""Immutable, single-use attack-list admission tickets (Windows local session).

This is intent serialization, not native combat permission. The owner thread must
independently revalidate its lease, movement Grant, scene, target and party before
attempting entry. A named mutex supplies a linearizable transition, not hardware CAS.
"""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass
from enum import IntEnum

MAGIC = b"WBCFNC1\0"
SCHEMA = 1
SIZE = 320
STATE_OFFSET = 16
_WIRE = struct.Struct("<8s6I6Q16s32s32s32s32s4I80s")
assert _WIRE.size == SIZE


class State(IntEnum):
    REGISTERING = 0
    PENDING = 1
    ENTERED = 2
    REVOKED = 3
    ENTERED_REVOKED = 4


@dataclass(frozen=True, slots=True)
class Binding:
    client_pid: int
    producer_pid: int
    client_creation: int
    producer_creation: int
    producer_generation: int
    movement_generation: int
    scene: int
    revision: int
    request: bytes
    store: bytes
    owner: bytes
    entry: bytes
    operation: bytes
    local_key: tuple[int, int]
    target_key: tuple[int, int]

    def __post_init__(self) -> None:
        for value in (self.client_pid, self.producer_pid, *self.local_key, *self.target_key):
            if type(value) is not int or not 0 < value < 2**32:
                raise ValueError("fence process IDs and keys must be positive uint32")
        for value in (self.client_creation, self.producer_creation, self.producer_generation,
                      self.movement_generation, self.scene, self.revision):
            if type(value) is not int or not 0 < value < 2**64:
                raise ValueError("fence lifetime, generation and revision must be positive uint64")
        for value, size in ((self.request, 16), (self.store, 32), (self.owner, 32),
                            (self.entry, 32), (self.operation, 32)):
            if not isinstance(value, bytes) or len(value) != size or not any(value):
                raise ValueError("invalid fence digest or request")
        if self.local_key == self.target_key or self.target_key[1] != 53:
            raise ValueError("fence target must be a distinct calibrated player")

    @property
    def name(self) -> str:
        return "Local\\WonderBane.CombatFence.v1." + self.request.hex()

    def encode(self, state: State = State.REGISTERING) -> bytes:
        return _WIRE.pack(
            MAGIC, SCHEMA, SIZE, int(State(state)), 0, self.client_pid, self.producer_pid,
            self.client_creation, self.producer_creation, self.producer_generation,
            self.movement_generation, self.scene, self.revision, self.request,
            self.store, self.owner, self.entry, self.operation,
            *self.local_key, *self.target_key, bytes(80),
        )

    @classmethod
    def decode(cls, data: bytes) -> tuple[Binding, State]:
        if len(data) != SIZE:
            raise ValueError("wrong fence geometry")
        values = _WIRE.unpack(data)
        if values[:3] != (MAGIC, SCHEMA, SIZE) or values[4] or any(values[-1]):
            raise ValueError("invalid fence header or reserved bytes")
        state = State(values[3])
        return cls(*values[5:18], tuple(values[18:20]), tuple(values[20:22])), state


def new_request() -> bytes:
    return uuid.uuid4().bytes
