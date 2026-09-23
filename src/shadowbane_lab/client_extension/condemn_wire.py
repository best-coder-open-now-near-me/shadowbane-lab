"""Explicit scoped Condemn payloads; native layout never relies on C++ padding."""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass
from enum import IntEnum

from .condemn_evidence import key
from .movement_wire import Host, request_bytes
from .vendor_wire import Outcome, uint

MAGIC, READY, IN_FLIGHT, UNRESOLVED = 0x57424B31, 1, 2, 4
_TARGET = struct.Struct("<5I")
_SNAPSHOT = struct.Struct("<QQ29I")
_COMMAND = struct.Struct("<16sQ16s20s132s16s368s")
_RECEIPT = struct.Struct("<16s16sQII132s20s20s16sIIQQQ116s")


class Verb(IntEnum):
    INSPECT = 23
    ENSURE = 24


class Phase(IntEnum):
    IDLE = 0
    OPENING = 1
    ADDING = 2
    ENABLING = 3
    VERIFIED = 4
    UNCERTAIN = 5
    EXISTING = 6


@dataclass(frozen=True, slots=True)
class Target:
    building: tuple[int, int]
    identity: tuple[int, int]
    scope: int

    def __post_init__(self):
        object.__setattr__(self, "building", key(self.building, kind=8))
        object.__setattr__(self, "identity", key(self.identity, kind=23))
        if type(self.scope) is not int or self.scope not in (4, 5):
            raise ValueError("Condemn requires separate guild (4) or nation (5) scope")

    def encode(self):
        return _TARGET.pack(*self.building, *self.identity, self.scope)

    @classmethod
    def decode(cls, data):
        if len(data) != 20:
            raise ValueError("invalid Condemn payload size")
        values = _TARGET.unpack(data)
        return cls(values[:2], values[2:4], values[4])


@dataclass(frozen=True, slots=True)
class Snapshot:
    scene: int = 0
    revision: int = 0
    local: tuple[int, int] = (0, 0)
    root: int = 0
    manager: int = 0
    building_hud: int = 0
    front: int = 0
    open_button: int = 0
    building: tuple[int, int] = (0, 0)
    kos: int = 0
    list_control: int = 0
    selected: int = 0
    list_selected: int = 0
    count: int = 0
    context: tuple[int, int] = (0, 0)
    pending: tuple[tuple[int, int], ...] = ((0, 0), (0, 0), (0, 0))
    flags: int = 0
    row: int = 0
    entry: int = 0
    enabled: int = 0
    collision: int = 0
    entry_key: tuple[int, int] = (0, 0)

    def __post_init__(self):
        for name in ("local", "building", "context", "entry_key"):
            object.__setattr__(self, name, key(getattr(self, name), empty=True))
        if len(self.pending) != 3:
            raise ValueError("three separately scoped pending keys required")
        object.__setattr__(self, "pending", tuple(key(k, empty=True) for k in self.pending))

    @property
    def empty(self):
        return self == Snapshot()

    def owned(self, target: Target):
        return bool(
            self.scene
            and self.revision
            and self.local[0]
            and self.local[1] == 53
            and self.root
            and self.manager
            and self.building_hud
            and self.building == target.building
            and not self.collision
        )

    def owned_list(self, target: Target):
        return bool(
            self.owned(target)
            and self.kos
            and self.list_control
            and self.front == self.kos
            and self.context == target.building
            and not self.flags
        )

    def eligible(self, target: Target):
        return self.owned(target) and (
            self.front == self.building_hud
            and self.open_button != 0
            or self.owned_list(target)
            and (self.entry != 0 or self.count < 512)
        )

    def encode(self):
        values = (
            *self.local,
            self.root,
            self.manager,
            self.building_hud,
            self.front,
            self.open_button,
            *self.building,
            self.kos,
            self.list_control,
            self.selected,
            self.list_selected,
            self.count,
            *self.context,
            *(v for pair in self.pending for v in pair),
            self.flags,
            self.row,
            self.entry,
            self.enabled,
            self.collision,
            *self.entry_key,
        )
        uint(self.scene, 64, "scene")
        uint(self.revision, 64, "revision")
        for value in values:
            uint(value, 32, "Condemn snapshot field")
        if not self.empty:
            if (
                not all((self.scene, self.revision, self.root, self.manager, self.building_hud))
                or self.local[1] != 53
                or not self.local[0]
                or self.building[1] != 8
                or not self.building[0]
                or self.count > 512
                or self.enabled > 1
                or self.collision > 1
                or self.flags & ~0x101
                or bool(self.entry) != bool(self.row)
                or bool(self.entry) != bool(self.entry_key[0])
                or self.entry
                and self.entry_key[1] != 23
                or not self.entry
                and self.enabled
                or self.kos
                and not self.list_control
                or not self.kos
                and any(
                    (
                        self.list_control,
                        self.selected,
                        self.list_selected,
                        self.count,
                        *self.context,
                        self.flags,
                        self.row,
                        *(v for pair in self.pending for v in pair),
                    )
                )
            ):
                raise ValueError("invalid Condemn snapshot")
        return _SNAPSHOT.pack(self.scene, self.revision, *values)

    @classmethod
    def decode(cls, data):
        if len(data) != 132:
            raise ValueError("invalid Condemn payload size")
        scene, revision, *v = _SNAPSHOT.unpack(data)
        result = cls(
            scene,
            revision,
            tuple(v[:2]),
            *v[2:7],
            tuple(v[7:9]),
            *v[9:14],
            tuple(v[14:16]),
            tuple(tuple(v[i : i + 2]) for i in (16, 18, 20)),
            *v[22:27],
            tuple(v[27:29]),
        )
        result.encode()
        return result


def _optional_request(value):
    return request_bytes(value) if value is not None else bytes(16)


def _decoded_request(value):
    return str(uuid.UUID(bytes=value)) if any(value) else None


@dataclass(frozen=True, slots=True)
class Command:
    host: Host
    window: int
    request_key: str
    target: Target
    expected: Snapshot = Snapshot()
    transition_request: str | None = None

    def encode(self, verb):
        verb = Verb(verb)
        if not uint(self.window, 32, "window"):
            raise ValueError("exact client HWND required")
        state = self.expected.encode()
        if (
            verb == Verb.INSPECT
            and not self.expected.empty
            or verb == Verb.ENSURE
            and (self.transition_request is not None or not self.expected.eligible(self.target))
        ):
            raise ValueError("invalid Condemn action arguments")
        return _COMMAND.pack(
            self.host.encode(),
            self.window,
            request_bytes(self.request_key),
            self.target.encode(),
            state,
            _optional_request(self.transition_request),
            bytes(368),
        )

    @classmethod
    def decode(cls, data, verb):
        if len(data) != 576:
            raise ValueError("invalid Condemn payload size")
        host, window, request, target, snapshot, transition, padding = _COMMAND.unpack(data)
        if any(padding):
            raise ValueError("nonzero Condemn command padding")
        result = cls(
            Host.decode(host),
            window,
            str(uuid.UUID(bytes=request)),
            Target.decode(target),
            Snapshot.decode(snapshot),
            _decoded_request(transition),
        )
        if result.encode(verb) != data:
            raise ValueError("noncanonical Condemn command")
        return result


@dataclass(frozen=True, slots=True)
class Receipt:
    request_key: str
    host: Host
    window: int
    outcome: Outcome
    flags: int
    snapshot: Snapshot
    target: Target | None = None
    transition_target: Target | None = None
    transition_request: str | None = None
    phase: Phase = Phase.IDLE
    action_tick: int = 0
    response_floor: int = 0
    completion_sequence: int = 0

    def encode(self):
        if isinstance(self.outcome, bool) or isinstance(self.phase, bool):
            raise ValueError("typed Condemn outcome and phase required")
        for value in (self.action_tick, self.response_floor, self.completion_sequence):
            uint(value, 64, "Condemn receipt counter")
        uint(self.flags, 32, "receipt flags")
        uint(self.window, 32, "window")
        raw = _RECEIPT.pack(
            request_bytes(self.request_key),
            self.host.encode(),
            self.window,
            Outcome(self.outcome),
            self.flags,
            self.snapshot.encode(),
            self.target.encode() if self.target else bytes(20),
            self.transition_target.encode() if self.transition_target else bytes(20),
            _optional_request(self.transition_request),
            Phase(self.phase),
            MAGIC,
            self.action_tick,
            self.response_floor,
            self.completion_sequence,
            bytes(116),
        )
        if type(self).decode(raw) != self:
            raise ValueError("noncanonical Condemn receipt")
        return raw

    @classmethod
    def decode(cls, data):
        if len(data) != 384:
            raise ValueError("invalid Condemn payload size")
        (
            request,
            host,
            window,
            outcome,
            flags,
            state,
            target,
            transition_target,
            transition,
            phase,
            magic,
            tick,
            floor,
            complete,
            padding,
        ) = _RECEIPT.unpack(data)
        if magic != MAGIC or flags & ~7 or any(padding) or not 0 < window < 2**32:
            raise ValueError("invalid Condemn receipt")
        snapshot = Snapshot.decode(state)
        target = Target.decode(target) if any(target) else None
        transition_target = Target.decode(transition_target) if any(transition_target) else None
        transition = _decoded_request(transition)
        phase = Phase(phase)
        if (
            not snapshot.empty
            and (target is None or snapshot.building != target.building)
            or flags & IN_FLIGHT
            and (not transition or target != transition_target)
            or bool(flags & UNRESOLVED) != (phase == Phase.UNCERTAIN)
            or complete
            and phase not in (Phase.ENABLING, Phase.VERIFIED, Phase.UNCERTAIN)
            or not tick
            and (floor or complete)
            or flags & READY
            and (
                flags & (IN_FLIGHT | UNRESOLVED) or target is None or not snapshot.eligible(target)
            )
            or bool(transition) != bool(transition_target)
            or phase in (Phase.OPENING, Phase.ADDING, Phase.ENABLING)
            and (not flags & IN_FLIGHT or flags & UNRESOLVED or not transition or not tick)
            or phase == Phase.UNCERTAIN
            and not flags & UNRESOLVED
            or phase in (Phase.VERIFIED, Phase.EXISTING)
            and (flags & (IN_FLIGHT | UNRESOLVED) or not transition)
            or phase == Phase.VERIFIED
            and (not complete or complete <= floor or not tick)
            or phase == Phase.EXISTING
            and complete
            or (floor >= 2**63 or complete >= 2**63)
        ):
            raise ValueError("contradictory Condemn receipt ownership")
        request = str(uuid.UUID(bytes=request))
        request_bytes(request)
        return cls(
            request,
            Host.decode(host),
            window,
            Outcome(outcome),
            flags,
            snapshot,
            target,
            transition_target,
            transition,
            phase,
            tick,
            floor,
            complete,
        )
