"""Immutable buff selectors, keyed by exact client/producer and native actor names."""
from __future__ import annotations

import ctypes as c
import hashlib
import struct
from dataclasses import dataclass

from shadowbane_lab.pve.buff_intent import BuffSettings, CoverageKind

from .actor_action_fence import digest, uint
from .combat_fence_windows import FenceError, Windows
from .combat_wire_v2 import identity_digest

SIZE = 1152
_HEADER = struct.Struct("<8s6I3Q32s32s8s")
_RECORD = struct.Struct("<8I")
assert _HEADER.size == 128 and _RECORD.size == 32


@dataclass(frozen=True, slots=True)
class Selector:
    index: int
    group: int
    kind: int
    power_id: int
    template_id: int
    coverage_power_id: int
    coverage_kind: int

    def encode(self):
        for value in (self.index, self.group, self.kind, self.power_id, self.template_id,
                      self.coverage_power_id, self.coverage_kind):
            uint(value)
        if (self.index >= 32 or self.group >= 32 or self.kind not in (3, 4)
                or not self.coverage_power_id or self.coverage_kind not in (0, 1)
                or (self.kind == 3 and (not self.power_id or self.template_id
                                       or self.coverage_power_id != self.power_id))
                or (self.kind == 4 and (self.power_id or not self.template_id
                                       or self.coverage_kind))):
            raise ValueError("invalid native buff selector")
        return _RECORD.pack(self.index, self.group, self.kind, self.power_id,
                            self.template_id, 0, self.coverage_power_id, self.coverage_kind)


@dataclass(frozen=True, slots=True)
class Manifest:
    client_pid: int
    producer_pid: int
    client_creation: int
    producer_creation: int
    producer_generation: int
    local_name: bytes
    server: bytes
    group_count: int
    selectors: tuple[Selector, ...]

    def encode(self):
        uint(self.client_pid, positive=True)
        uint(self.producer_pid, positive=True)
        for value in (self.client_creation, self.producer_creation, self.producer_generation):
            uint(value, 64, positive=True)
        digest(self.local_name)
        digest(self.server)
        uint(self.group_count, positive=True)
        if (self.group_count > 32 or type(self.selectors) is not tuple
                or not 1 <= len(self.selectors) <= 32
                or not all(isinstance(s, Selector) for s in self.selectors)
                or tuple(s.index for s in self.selectors) != tuple(range(len(self.selectors)))
                or {s.group for s in self.selectors} != set(range(self.group_count))):
            raise ValueError("manifest selectors/groups must be bounded and dense")
        records = b"".join(s.encode() for s in self.selectors)
        if len({s.encode()[8:] for s in self.selectors}) != len(self.selectors):
            raise ValueError("duplicate native buff selector")
        return _HEADER.pack(b"WBABUF1\0", 1, SIZE, len(self.selectors), self.group_count,
            self.client_pid, self.producer_pid, self.client_creation, self.producer_creation,
            self.producer_generation, self.local_name, self.server, bytes(8)) + records + bytes(
                (32-len(self.selectors))*32)

    @classmethod
    def decode(cls, payload):
        if type(payload) is not bytes or len(payload) != SIZE:
            raise ValueError("invalid selector manifest size")
        v = _HEADER.unpack_from(payload)
        if v[:3] != (b"WBABUF1\0", 1, SIZE) or not 1 <= v[3] <= 32 or any(v[-1]):
            raise ValueError("invalid manifest header")
        selectors = []
        for i in range(v[3]):
            r = _RECORD.unpack_from(payload, 128+i*32)
            if r[5]:
                raise ValueError("template second word must be zero")
            selectors.append(Selector(*r[:5], *r[6:]))
        if any(payload[128+v[3]*32:]):
            raise ValueError("unused manifest records must be zero")
        result = cls(*v[5:12], v[4], tuple(selectors))
        result.encode()
        return result

    @classmethod
    def for_settings(cls, settings, *, client_pid, client_creation, host, identity):
        if not isinstance(settings, BuffSettings) or not settings.enabled:
            raise ValueError("manifest requires enabled typed buff intent")
        selectors = []
        for group_index, group in enumerate(settings.groups):
            for buff in group.alternatives:
                action = buff.action
                selectors.append(Selector(len(selectors), group_index,
                    3 if action.power_id else 4, action.power_id or 0,
                    0 if action.item_template is None else action.item_template[0],
                    buff.coverage_power_id,
                    int(buff.coverage_kind is CoverageKind.TRANSFORM_MARKER)))
        result = cls(client_pid, host.process_id, client_creation, host.creation_filetime,
            host.lease_generation, identity_digest(identity.character_name),
            identity_digest(identity.server_name), len(settings.groups), tuple(selectors))
        result.encode()
        return result

    @property
    def digest(self):
        return hashlib.sha256(self.encode()).digest()

    @property
    def name(self):
        return "Local\\WonderBane.ActorSelectors.v1." + self.digest.hex()

    def group_digest(self, index):
        uint(index)
        if index >= self.group_count:
            raise ValueError("invalid coverage group")
        # Stable across names, ordering, producer, parent Grant and policy rebuild.
        records = sorted(s.encode()[8:] for s in self.selectors if s.group == index)
        return hashlib.sha256(b"WBAGRP1\0" + b"".join(records)).digest()


class PublishedManifest:
    """Producer-owned immutable mapping; native opens read-only and verifies SHA256."""
    def __init__(self, manifest):
        if not isinstance(manifest, Manifest):
            raise ValueError("typed manifest required")
        payload = manifest.encode()
        self.manifest, self.api = manifest, Windows()
        self.mapping = self.view = 0
        try:
            if self.api.identity() != (manifest.producer_pid, manifest.producer_creation):
                raise FenceError("only the exact producer may publish selectors")
            if not self.api.alive(manifest.client_pid, manifest.client_creation):
                raise FenceError("client lifetime ended")
            with self.api.security() as security:
                self.mapping = self.api.checked(self.api.k.CreateFileMappingW(c.c_void_p(-1),
                    c.byref(security), 4, 0, SIZE, manifest.name), "CreateFileMappingW")
                if c.get_last_error() == 183:
                    raise FenceError("selector manifest already exists")
            self.view = self.api.checked(self.api.k.MapViewOfFile(self.mapping, 6, 0, 0, SIZE),
                                         "MapViewOfFile")
            c.memmove(self.view, payload, SIZE)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.view:
            self.api.k.UnmapViewOfFile(self.view)
            self.view = 0
        if self.mapping:
            self.api.k.CloseHandle(self.mapping)
            self.mapping = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
