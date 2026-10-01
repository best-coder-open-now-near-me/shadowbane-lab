"""Version 4 actor-owner and target-context fences, with exact producer ACLs.

Actor preparation has no context fence. Target authority is a separate immutable
child of one actor owner; neither codec creates native action permission.
"""

from __future__ import annotations

import ctypes as c
import hashlib
import struct
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
from threading import Lock

from .combat_fence_windows import FenceError, Windows

SIZE = 320
STATE_OFFSET = 16
_PARENT = struct.Struct("<8s6I5Q16s4I32s32s32s32s88s")
# The fourth integer is reserved; normalized state is the sole mutable field.
_CONTEXT = struct.Struct("<8s4I32s16s4IQ32s32s32s128s")
assert _PARENT.size == _CONTEXT.size == SIZE


class State(IntEnum):
    REGISTERING = 0
    PENDING = 1
    ENTERED = 2
    REVOKED = 3
    ENTERED_REVOKED = 4


class Authority(IntEnum):
    MANUAL_PLAYER = 1
    NPC = 2


def uint(value, bits=32, *, positive=False):
    if type(value) is not int or not (1 if positive else 0) <= value < 2**bits:
        raise ValueError(f"invalid uint{bits}")


def digest(value, *, zero=False):
    if type(value) is not bytes or len(value) != 32 or (any(value) if zero else not any(value)):
        raise ValueError("invalid SHA256 identity")


def address(value):
    uint(value, positive=True)
    if not 0x10000 <= value <= 0x7FFEFFFC or value % 4:
        raise ValueError("invalid native address hint")


def key(value, kind=None):
    if type(value) is not tuple or len(value) != 2:
        raise ValueError("native key must be immutable")
    for word in value:
        uint(word, positive=True)
    if kind is not None and value[1] != kind:
        raise ValueError("native key type mismatch")


@dataclass(frozen=True, slots=True, order=True)
class Ordinal:
    value: int

    def __post_init__(self):
        uint(self.value, 128, positive=True)

    def encode(self):
        return self.value.to_bytes(16, "big")

    @classmethod
    def decode(cls, data):
        if type(data) is not bytes or len(data) != 16:
            raise ValueError("invalid ordinal bytes")
        return cls(int.from_bytes(data, "big"))


class OwnerId(Ordinal):
    __slots__ = ()


class ContextId(Ordinal):
    __slots__ = ()


class RequestId(Ordinal):
    __slots__ = ()


class Ordinals:
    """Retained for the exact Host/Grant namespace; never reset on child closure."""

    def __init__(self):
        self._lock = Lock()
        self._values = dict.fromkeys((OwnerId, ContextId, RequestId), 0)

    def next(self, kind):
        if kind not in self._values:
            raise ValueError("unknown ordinal kind")
        with self._lock:
            result = kind(self._values[kind] + 1)
            self._values[kind] = result.value
            return result


@dataclass(frozen=True, slots=True)
class ActorBinding:
    client_pid: int
    producer_pid: int
    client_creation: int
    producer_creation: int
    producer_generation: int
    movement_generation: int
    scene: int
    owner_id: OwnerId
    actor_key: tuple[int, int]
    actor_hint: int
    local_name: bytes
    server: bytes
    owner: bytes
    operation: bytes

    def __post_init__(self):
        if type(self.owner_id) is not OwnerId:
            raise ValueError("actor binding requires owner ordinal")
        uint(self.client_pid, positive=True)
        uint(self.producer_pid, positive=True)
        for value in (
            self.client_creation,
            self.producer_creation,
            self.producer_generation,
            self.movement_generation,
            self.scene,
        ):
            uint(value, 64, positive=True)
        key(self.actor_key, 53)
        address(self.actor_hint)
        for value in (self.local_name, self.server, self.owner, self.operation):
            digest(value)

    def encode(self, state=State.REGISTERING):
        if not isinstance(state, State):
            raise ValueError("invalid fence state")
        return _PARENT.pack(
            b"WBAOWN4\0",
            4,
            SIZE,
            state,
            0,
            self.client_pid,
            self.producer_pid,
            self.client_creation,
            self.producer_creation,
            self.producer_generation,
            self.movement_generation,
            self.scene,
            self.owner_id.encode(),
            *self.actor_key,
            self.actor_hint,
            0,
            self.local_name,
            self.server,
            self.owner,
            self.operation,
            bytes(88),
        )

    @classmethod
    def decode(cls, data):
        if type(data) is not bytes or len(data) != SIZE:
            raise ValueError("invalid actor fence geometry")
        v = _PARENT.unpack(data)
        if v[:3] != (b"WBAOWN4\0", 4, SIZE) or v[4] or v[16] or any(v[-1]):
            raise ValueError("invalid actor fence header/reserved")
        return cls(*v[5:12], OwnerId.decode(v[12]), tuple(v[13:15]), v[15], *v[17:21]), State(v[3])

    @property
    def digest(self):
        return hashlib.sha256(self.encode()).digest()

    @property
    def name(self):
        return "Local\\WonderBane.ActorOwner.v4." + self.digest.hex()


@dataclass(frozen=True, slots=True)
class ContextBinding:
    parent_digest: bytes
    context_id: ContextId
    authority: Authority
    target_hint: int
    target_key: tuple[int, int]
    revision: int
    store: bytes
    entry: bytes
    target_name: bytes

    def __post_init__(self):
        digest(self.parent_digest)
        if type(self.context_id) is not ContextId or not isinstance(self.authority, Authority):
            raise ValueError("context requires typed identity and authority")
        npc = self.authority is Authority.NPC
        key(self.target_key, 37 if npc else 53)
        address(self.target_hint)
        uint(self.revision, 64, positive=not npc)
        if npc and self.revision:
            raise ValueError("NPC context has no list revision")
        for value in (self.store, self.entry, self.target_name):
            digest(value, zero=npc)

    def require_parent(self, parent):
        if (
            not isinstance(parent, ActorBinding)
            or self.parent_digest != parent.digest
            or self.target_key == parent.actor_key
            or self.target_hint == parent.actor_hint
        ):
            raise ValueError("context differs from exact parent or aliases actor")

    def encode(self, state=State.REGISTERING):
        if not isinstance(state, State):
            raise ValueError("invalid fence state")
        return _CONTEXT.pack(
            b"WBACXT4\0",
            4,
            SIZE,
            state,
            0,
            self.parent_digest,
            self.context_id.encode(),
            self.authority,
            self.target_hint,
            *self.target_key,
            self.revision,
            self.store,
            self.entry,
            self.target_name,
            bytes(128),
        )

    @classmethod
    def decode(cls, data):
        if type(data) is not bytes or len(data) != SIZE:
            raise ValueError("invalid context fence geometry")
        v = _CONTEXT.unpack(data)
        if v[:3] != (b"WBACXT4\0", 4, SIZE) or v[4] or any(v[-1]):
            raise ValueError("invalid context fence header/reserved")
        return cls(
            v[5], ContextId.decode(v[6]), Authority(v[7]), v[8], tuple(v[9:11]), v[11], *v[12:15]
        ), State(v[3])

    @property
    def digest(self):
        return hashlib.sha256(self.encode()).digest()

    @property
    def name(self):
        return "Local\\WonderBane.ActorContext.v4." + self.digest.hex()


class Ticket:
    """Producer creates only; retain handles if revocation cannot be confirmed.

    Reuses the existing protected current-user-only Windows security primitive,
    never the old combat binding or old admission path. Context consumers must
    inspect BOTH parent and child; child entry alone grants no actor permission.
    """

    def __init__(self, binding, *, parent=None, create=False):
        if isinstance(binding, ActorBinding):
            if parent is not None:
                raise ValueError("actor fence cannot have another parent")
            identity = binding
        elif isinstance(binding, ContextBinding) and isinstance(parent, ActorBinding):
            binding.require_parent(parent)
            identity = parent
        else:
            raise ValueError("invalid typed actor/context fence")
        self.binding, self.identity, self.api = binding, identity, Windows()
        self.mutex = self.mapping = self.view = 0
        k = self.api.k
        try:
            if create:
                if self.api.identity() != (identity.producer_pid, identity.producer_creation):
                    raise FenceError("only the exact producer can create a fence")
                if not self.api.alive(identity.client_pid, identity.client_creation):
                    raise FenceError("client lifetime ended")
                with self.api.security() as security:
                    self.mutex = self.api.checked(
                        k.CreateMutexW(c.byref(security), False, binding.name + ".lock"),
                        "CreateMutexW",
                    )
                    if c.get_last_error() == 183:
                        raise FenceError("fence mutex already exists")
                    self.mapping = self.api.checked(
                        k.CreateFileMappingW(
                            c.c_void_p(-1), c.byref(security), 4, 0, SIZE, binding.name
                        ),
                        "CreateFileMappingW",
                    )
                    if c.get_last_error() == 183:
                        raise FenceError("fence mapping already exists")
            else:
                self.mutex = self.api.checked(
                    k.OpenMutexW(0x100001, False, binding.name + ".lock"), "OpenMutexW"
                )
                self.mapping = self.api.checked(
                    k.OpenFileMappingW(6, False, binding.name), "OpenFileMappingW"
                )
            self.view = self.api.checked(
                k.MapViewOfFile(self.mapping, 6, 0, 0, SIZE), "MapViewOfFile"
            )
            if create:
                c.memmove(self.view, binding.encode(), SIZE)
        except BaseException:
            self.close(revoke=False)
            raise

    @contextmanager
    def locked(self, timeout_ms=5000):
        uint(timeout_ms)
        if not self.view or not self.mutex:
            raise FenceError("fence is closed")
        result = self.api.k.WaitForSingleObject(self.mutex, timeout_ms)
        if result not in (0, 128):
            raise FenceError("fence busy or unavailable")
        try:
            observed, state = type(self.binding).decode(c.string_at(self.view, SIZE))
            if observed != self.binding:
                raise FenceError("immutable fence changed")
            if result == 128 or not self.api.alive(
                self.identity.producer_pid, self.identity.producer_creation
            ):
                state = (
                    State.ENTERED_REVOKED
                    if state in (State.ENTERED, State.ENTERED_REVOKED)
                    else State.REVOKED
                )
                self._state(state)
            yield state
        finally:
            self.api.checked(self.api.k.ReleaseMutex(self.mutex), "ReleaseMutex")

    def _state(self, state):
        c.c_uint32.from_address(self.view + STATE_OFFSET).value = int(state)

    def arm(self):
        with self.locked() as state:
            if state is not State.REGISTERING or self.api.identity() != (
                self.identity.producer_pid,
                self.identity.producer_creation,
            ):
                raise FenceError("fence cannot arm")
            self._state(State.PENDING)

    def state(self):
        with self.locked() as state:
            return state

    def revoke(self, *, timeout_ms=5000):
        with self.locked(timeout_ms) as state:
            state = (
                State.ENTERED_REVOKED
                if state in (State.ENTERED, State.ENTERED_REVOKED)
                else State.REVOKED
            )
            self._state(state)
            return state

    def close(self, *, revoke=True, timeout_ms=5000):
        if revoke and self.view:
            self.revoke(timeout_ms=timeout_ms)
        if self.view:
            self.api.k.UnmapViewOfFile(self.view)
            self.view = 0
        for name in ("mapping", "mutex"):
            handle = getattr(self, name)
            if handle:
                self.api.k.CloseHandle(handle)
                setattr(self, name, 0)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
