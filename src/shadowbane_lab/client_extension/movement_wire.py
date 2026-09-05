"""Lossless schema-2 movement payloads; observations never grant ownership.

All integers have fixed little-endian widths. UUIDs use RFC canonical byte order.
The action channel prefix supplies command sequence, ID, deadline and verb.
"""

from __future__ import annotations

import math
import struct
import uuid
from dataclasses import dataclass
from enum import IntEnum

SCHEMA = 2
COMMAND_SIZE, RESULT_SIZE, STATUS_SIZE = 768, 512, 512
COMMAND_PREFIX, RESULT_PREFIX = 192, 128
_HOST = struct.Struct("<IIQ")
_GRANT = struct.Struct("<QQII96s96s")
_SETTINGS = struct.Struct("<8I4fI")
_COMMAND = struct.Struct("<16sQ216s16s3f52sQ192s56s")
_RECEIPT = struct.Struct("<216s16s16sQQ52sII60s")
_STATUS = struct.Struct("<qIIQQ216s52sQQ196s")
assert _COMMAND.size == COMMAND_SIZE - COMMAND_PREFIX
assert _RECEIPT.size == RESULT_SIZE - RESULT_PREFIX and _STATUS.size == STATUS_SIZE


class Verb(IntEnum):
    ACQUIRE = 3
    DESTINATION = 4
    STOP = 5
    CONFIGURE = 6


class Outcome(IntEnum):
    ACCEPTED = 0
    STALE = 1
    UNAVAILABLE = 2
    INHIBITED = 3
    STOP_FAILED = 4
    INVALID = 5


class Owner(IntEnum):
    NONE = 0
    AUTOMATION = 1
    MANUAL = 2


def _uint(value: int, bits: int, name: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value < 2**bits:
        raise ValueError(f"{name} must be an unsigned {bits}-bit integer >= {minimum}")
    return value


def _text(value: str, required: bool) -> bytes:
    if not isinstance(value, str):
        raise ValueError("token must be text")
    data = value.encode("ascii")
    if len(data) > 95 or (required and not data) or any(c < 32 or c > 126 for c in data):
        raise ValueError("token must contain 1–95 printable ASCII characters")
    return data.ljust(96, b"\0")


def _untext(value: bytes) -> str:
    head, zero, tail = value.partition(b"\0")
    if not zero or any(tail):
        raise ValueError("token must have canonical zero padding")
    result = head.decode("ascii")
    _text(result, False)
    return result


def request_bytes(value: str) -> bytes:
    parsed = uuid.UUID(value)
    if str(parsed) != value or parsed.int == 0:
        raise ValueError("request key must be a nonzero canonical UUID")
    return parsed.bytes


@dataclass(frozen=True, slots=True)
class Host:
    process_id: int
    lease_generation: int
    creation_filetime: int

    def encode(self) -> bytes:
        return _HOST.pack(
            _uint(self.process_id, 31, "host PID", 1),
            _uint(self.lease_generation, 31, "lease generation", 1),
            _uint(self.creation_filetime, 64, "host creation", 1),
        )

    @classmethod
    def decode(cls, data: bytes) -> Host:
        result = cls(*_HOST.unpack(data))
        result.encode()
        return result


@dataclass(frozen=True, slots=True)
class Grant:
    generation: int
    scene: int
    owner: Owner = Owner.NONE
    worker_id: str = ""
    operation_id: str = ""

    def encode(self) -> bytes:
        owner = Owner(self.owner)
        required = owner == Owner.AUTOMATION
        if owner != Owner.NONE and not self.scene:
            raise ValueError("owned grant needs a scene")
        if not required and (self.worker_id or self.operation_id):
            raise ValueError("only automation grants carry a token")
        return _GRANT.pack(
            _uint(self.generation, 64, "generation", 1),
            _uint(self.scene, 64, "scene"),
            owner,
            0,
            _text(self.worker_id, required),
            _text(self.operation_id, required),
        )

    @classmethod
    def decode(cls, data: bytes) -> Grant:
        generation, scene, owner, reserved, worker, operation = _GRANT.unpack(data)
        if reserved:
            raise ValueError("grant reserved field is nonzero")
        result = cls(generation, scene, Owner(owner), _untext(worker), _untext(operation))
        result.encode()
        return result


@dataclass(frozen=True, slots=True)
class Settings:
    enabled: bool = False
    keyboard: bool = True
    controller: bool = False
    drag: bool = True
    keys: tuple[int, int, int, int] = (0x57, 0x53, 0x41, 0x44)
    controller_slot: int = 0
    movement_dead_zone: float = 0.20
    camera_dead_zone: float = 0.15
    camera_radians_per_second: float = 2.0
    drag_threshold_pixels: float = 6.0
    drag_button: int = 5
    invert_camera_x: bool = False
    invert_camera_y: bool = False

    def encode(self) -> bytes:
        toggles = (
            self.enabled,
            self.keyboard,
            self.controller,
            self.drag,
            self.invert_camera_x,
            self.invert_camera_y,
        )
        if any(type(v) is not bool for v in toggles):
            raise ValueError("settings toggles must be bool")
        if (
            len(self.keys) != 4
            or len(set(self.keys)) != 4
            or any(type(k) is not int or not 8 <= k <= 254 for k in self.keys)
        ):
            raise ValueError("four distinct supported virtual keys required")
        _uint(self.controller_slot, 2, "controller slot")
        values = (
            self.movement_dead_zone,
            self.camera_dead_zone,
            self.camera_radians_per_second,
            self.drag_threshold_pixels,
        )
        if any(isinstance(v, bool) or not math.isfinite(v) for v in values):
            raise ValueError("settings numbers must be finite")
        if not (
            0.05 <= values[0] < 0.95
            and 0.05 <= values[1] < 0.95
            and 0 < values[2] <= 10
            and 2 <= values[3] <= 64
        ):
            raise ValueError("settings number outside native supported range")
        if type(self.drag_button) is not int or self.drag_button not in (1, 4, 5, 6):
            raise ValueError("drag button conflicts with native camera or is unsupported")
        flags = sum(int(value) << n for n, value in enumerate(toggles))
        return _SETTINGS.pack(
            0x57424D43, 1, flags, *self.keys, self.controller_slot, *values, self.drag_button
        )

    @classmethod
    def decode(cls, data: bytes) -> Settings:
        magic, version, flags, *values = _SETTINGS.unpack(data)
        if magic != 0x57424D43 or version != 1 or flags & ~63:
            raise ValueError("unsupported settings format")
        result = cls(
            bool(flags & 1),
            bool(flags & 2),
            bool(flags & 4),
            bool(flags & 8),
            tuple(values[:4]),
            values[4],
            *values[5:9],
            values[9],
            bool(flags & 16),
            bool(flags & 32),
        )
        result.encode()
        return result


@dataclass(frozen=True, slots=True)
class Command:
    host: Host
    window: int
    expected: Grant
    request_key: str
    destination: tuple[float, float, float] = (0.0, 0.0, 0.0)
    settings: Settings = Settings()
    revision: int = 0
    worker_id: str = ""
    operation_id: str = ""

    def encode(self, verb: Verb) -> bytes:
        verb = Verb(verb)
        if len(self.destination) != 3 or any(not math.isfinite(v) for v in self.destination):
            raise ValueError("native destination must be finite XYZ")
        if verb in (Verb.DESTINATION, Verb.STOP) and self.expected.owner != Owner.AUTOMATION:
            raise ValueError("movement/stop requires an automation grant")
        if verb != Verb.ACQUIRE and (self.worker_id or self.operation_id):
            raise ValueError("requested token is only valid for acquisition")
        if verb == Verb.CONFIGURE and not self.revision:
            raise ValueError("configure requires the observed settings revision")
        return _COMMAND.pack(
            self.host.encode(),
            _uint(self.window, 32, "client HWND", 1),
            self.expected.encode(),
            request_bytes(self.request_key),
            *self.destination,
            self.settings.encode(),
            _uint(self.revision, 64, "settings revision"),
            _text(self.worker_id, verb == Verb.ACQUIRE)
            + _text(self.operation_id, verb == Verb.ACQUIRE),
            bytes(56),
        )

    @classmethod
    def decode(cls, data: bytes, verb: Verb) -> Command:
        host, window, grant, key, x, y, z, settings, revision, token, reserved = _COMMAND.unpack(
            data
        )
        if any(reserved):
            raise ValueError("command reserved bytes are nonzero")
        result = cls(
            Host.decode(host),
            window,
            Grant.decode(grant),
            str(uuid.UUID(bytes=key)),
            (x, y, z),
            Settings.decode(settings),
            revision,
            _untext(token[:96]),
            _untext(token[96:]),
        )
        result.encode(verb)
        return result


@dataclass(frozen=True, slots=True)
class Receipt:
    grant: Grant
    request_key: str
    host: Host
    window: int
    revision: int
    settings: Settings
    outcome: Outcome
    flags: int

    def encode(self) -> bytes:
        if self.flags & ~63:
            raise ValueError("unknown status flags")
        return _RECEIPT.pack(
            self.grant.encode(),
            request_bytes(self.request_key),
            self.host.encode(),
            _uint(self.window, 32, "client HWND", 1),
            _uint(self.revision, 64, "settings revision", 1),
            self.settings.encode(),
            Outcome(self.outcome),
            self.flags,
            bytes(60),
        )

    @classmethod
    def decode(cls, data: bytes) -> Receipt:
        grant, key, host, window, revision, settings, outcome, flags, reserved = _RECEIPT.unpack(
            data
        )
        if any(reserved):
            raise ValueError("receipt reserved bytes are nonzero")
        result = cls(
            Grant.decode(grant),
            str(uuid.UUID(bytes=key)),
            Host.decode(host),
            window,
            revision,
            Settings.decode(settings),
            Outcome(outcome),
            flags,
        )
        result.encode()
        return result


@dataclass(frozen=True, slots=True)
class Snapshot:
    sequence: int
    process_id: int
    flags: int
    creation_filetime: int
    window: int
    grant: Grant
    settings: Settings
    revision: int
    tick: int

    def encode(self) -> bytes:
        if self.sequence & 1 or self.flags & ~63:
            raise ValueError("snapshot is unpublished/in progress or has unknown flags")
        return _STATUS.pack(
            _uint(self.sequence, 63, "snapshot sequence", 2),
            _uint(self.process_id, 32, "client PID", 1),
            self.flags,
            _uint(self.creation_filetime, 64, "client creation", 1),
            _uint(self.window, 32, "client HWND"),
            self.grant.encode(),
            self.settings.encode(),
            _uint(self.revision, 64, "settings revision", 1),
            _uint(self.tick, 64, "snapshot tick"),
            bytes(196),
        )

    @classmethod
    def decode(cls, data: bytes) -> Snapshot:
        seq, pid, flags, creation, window, grant, settings, revision, tick, reserved = (
            _STATUS.unpack(data)
        )
        if any(reserved):
            raise ValueError("snapshot reserved bytes are nonzero")
        result = cls(
            seq,
            pid,
            flags,
            creation,
            window,
            Grant.decode(grant),
            Settings.decode(settings),
            revision,
            tick,
        )
        result.encode()
        return result
