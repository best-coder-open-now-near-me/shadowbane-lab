"""Selection-independent engagement binding and monotonic identity codec.

This is authority serialization, not native permission. It never resolves a host
address hint or substitutes for exact native object/owner validation.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from enum import IntEnum
from threading import Lock

MAGIC = b"WBCFNC3\0"
SCHEMA = 3
SIZE = 320
STATE_OFFSET = 16
_WIRE = struct.Struct("<8s6I6Q16s32s32s32s32s4I32s3I36s")
assert _WIRE.size == SIZE


class Authority(IntEnum):
    MANUAL_PLAYER = 1
    NPC = 2


class State(IntEnum):
    REGISTERING = 0
    PENDING = 1
    ENTERED = 2
    REVOKED = 3
    ENTERED_REVOKED = 4


@dataclass(frozen=True, slots=True, order=True)
class EngagementId:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 < self.value < 2**128:
            raise ValueError("engagement ordinal must be a positive uint128")

    def encode(self) -> bytes:
        return self.value.to_bytes(16, "big")

    @classmethod
    def decode(cls, payload: bytes) -> EngagementId:
        if not isinstance(payload, bytes) or len(payload) != 16:
            raise ValueError("engagement ordinal requires exactly 16 bytes")
        return cls(int.from_bytes(payload, "big"))


@dataclass(frozen=True, slots=True, order=True)
class RequestId:
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 < self.value < 2**128:
            raise ValueError("request ordinal must be a positive uint128")

    def encode(self) -> bytes:
        return self.value.to_bytes(16, "big")

    @classmethod
    def decode(cls, payload: bytes) -> RequestId:
        if not isinstance(payload, bytes) or len(payload) != 16:
            raise ValueError("request ordinal requires exactly 16 bytes")
        return cls(int.from_bytes(payload, "big"))


class Ordinals:
    """One allocator per exact producer/Grant namespace; never reset or randomize.

    The operation owner retains this object. Beginning an engagement allocates
    its first control ID; subsequent actions and controls use next_request().
    Only the current engagement can allocate new request identities.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._engagement = 0
        self._request = 0

    def next_engagement(self) -> EngagementId:
        with self._lock:
            value = EngagementId(self._engagement + 1)
            self._engagement, self._request = value.value, 0
            return value

    def next_request(self, engagement: EngagementId) -> RequestId:
        with self._lock:
            if type(engagement) is not EngagementId or engagement.value != self._engagement:
                raise ValueError("cannot allocate an action for another engagement")
            value = RequestId(self._request + 1)
            self._request = value.value
            return value


def _digest(value: bytes, label: str, *, zero: bool = False) -> None:
    if (not isinstance(value, bytes) or len(value) != 32
            or (any(value) if zero else not any(value))):
        raise ValueError(f"invalid {label} digest")


def _address(value: int) -> None:
    if type(value) is not int or value % 4 or not 0x10000 <= value <= 0x7FFEFFFC:
        raise ValueError("address hint must be an aligned bounded uint32 pointer")


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
    engagement: EngagementId
    store: bytes
    owner: bytes
    entry: bytes
    operation: bytes
    local_key: tuple[int, int]
    target_key: tuple[int, int]
    target_name: bytes
    authority: Authority
    actor_address_hint: int
    target_address_hint: int

    def __post_init__(self) -> None:
        if type(self.engagement) is not EngagementId or not isinstance(self.authority, Authority):
            raise ValueError("engagement binding requires typed identity and authority")
        if (len(self.local_key) != 2 or len(self.target_key) != 2
                or self.local_key == self.target_key or self.local_key[1] != 53):
            raise ValueError("engagement requires distinct exact actor and target keys")
        for value in (self.client_pid, self.producer_pid, *self.local_key, *self.target_key):
            if type(value) is not int or not 0 < value < 2**32:
                raise ValueError("process IDs and object keys must be positive uint32")
        for value in (self.client_creation, self.producer_creation, self.producer_generation,
                      self.movement_generation, self.scene):
            if type(value) is not int or not 0 < value < 2**64:
                raise ValueError("lifetime and generations must be positive uint64")
        if type(self.revision) is not int or not 0 <= self.revision < 2**64:
            raise ValueError("revision must be uint64")
        _address(self.actor_address_hint)
        _address(self.target_address_hint)
        if self.actor_address_hint == self.target_address_hint:
            raise ValueError("actor and target address hints must differ")
        _digest(self.owner, "owner")
        _digest(self.operation, "operation")
        npc = self.authority is Authority.NPC
        if self.target_key[1] != (37 if npc else 53) or (self.revision == 0) != npc:
            raise ValueError("target type or revision contradicts engagement authority")
        for label in ("store", "entry", "target_name"):
            _digest(getattr(self, label), label, zero=npc)

    def encode(self, state: State = State.REGISTERING) -> bytes:
        if not isinstance(state, State):
            raise ValueError("fence state must be State")
        return _WIRE.pack(
            MAGIC, SCHEMA, SIZE, state, 0, self.client_pid, self.producer_pid,
            self.client_creation, self.producer_creation, self.producer_generation,
            self.movement_generation, self.scene, self.revision, self.engagement.encode(),
            self.store, self.owner, self.entry, self.operation, *self.local_key, *self.target_key,
            self.target_name, self.authority, self.actor_address_hint, self.target_address_hint,
            bytes(36),
        )

    @property
    def digest(self) -> bytes:
        return hashlib.sha256(self.encode()).digest()

    @property
    def name(self) -> str:
        return "Local\\WonderBane.CombatFence.v3." + self.digest.hex()

    @classmethod
    def decode(cls, data: bytes) -> tuple[Binding, State]:
        if not isinstance(data, bytes) or len(data) != SIZE:
            raise ValueError("wrong fence geometry")
        v = _WIRE.unpack(data)
        if v[:3] != (MAGIC, SCHEMA, SIZE) or v[4] or any(v[-1]):
            raise ValueError("invalid fence header or reserved bytes")
        binding = cls(*v[5:13], EngagementId.decode(v[13]), *v[14:18],
                      tuple(v[18:20]), tuple(v[20:22]), v[22], Authority(v[23]), v[24], v[25])
        return binding, State(v[3])
