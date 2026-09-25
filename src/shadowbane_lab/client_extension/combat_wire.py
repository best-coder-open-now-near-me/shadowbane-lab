"""Lossless explicit saved-player command binding; this module grants no action authority.

The native receiver reconstructs the complete mapping binding using its own process
lifetime and compares every immutable byte before checking live native admission.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from enum import IntEnum

from .combat_fence import Binding
from .movement_wire import Grant, Host, Owner

_COMMAND = struct.Struct("<16sQ216s16s32s32s32s32s4IQ32s32s32s32s40s")
assert _COMMAND.size == 576


class Verb(IntEnum):
    START = 34
    STATUS = 35
    CANCEL = 36


def identity_digest(value: str) -> bytes:
    """Hash complete native UTF-16 code units, without normalization or terminator."""
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("combat identity must be nonempty text without NUL")
    encoded = value.encode("utf-16-le", errors="strict")
    if len(encoded) > 128:
        raise ValueError("combat identity exceeds the native 64-code-unit bound")
    return hashlib.sha256(encoded).digest()


def operation_digest(grant: Grant) -> bytes:
    if grant.owner != Owner.AUTOMATION:
        raise ValueError("combat needs an automation Grant")
    return hashlib.sha256(grant.encode()[24:]).digest()


@dataclass(frozen=True, slots=True)
class Command:
    host: Host
    window: int
    grant: Grant
    binding: Binding
    local_name: bytes
    server: bytes
    target_name: bytes

    def encode(self) -> bytes:
        b = self.binding
        if type(self.window) is not int or not 0 < self.window < 2**32:
            raise ValueError("combat window must be a nonzero uint32")
        if ((self.host.process_id, self.host.creation_filetime, self.host.lease_generation)
                != (b.producer_pid, b.producer_creation, b.producer_generation)
                or (self.grant.generation, self.grant.scene)
                != (b.movement_generation, b.scene)
                or operation_digest(self.grant) != b.operation
                or self.target_name != b.target_name):
            raise ValueError("combat command and registered admission disagree")
        for digest in (self.local_name, self.server, self.target_name):
            if not isinstance(digest, bytes) or len(digest) != 32 or not any(digest):
                raise ValueError("combat identity requires a complete SHA-256 digest")
        return _COMMAND.pack(
            self.host.encode(), self.window, self.grant.encode(), b.request,
            hashlib.sha256(b.encode()).digest(), self.local_name, self.server, self.target_name,
            *b.local_key, *b.target_key, b.revision, b.store, b.owner, b.entry, b.operation,
            bytes(40),
        )

    @classmethod
    def decode(cls, data: bytes, *, client_pid: int, client_creation: int) -> Command:
        if len(data) != _COMMAND.size:
            raise ValueError("invalid combat command geometry")
        (host_bytes, window, grant_bytes, request, binding_digest, local_name, server,
         target_name, local_id, local_type, target_id, target_type, revision,
         store, owner, entry, operation, reserved) = _COMMAND.unpack(data)
        if any(reserved):
            raise ValueError("combat command reserved bytes must be zero")
        host, grant = Host.decode(host_bytes), Grant.decode(grant_bytes)
        binding = Binding(client_pid, host.process_id, client_creation, host.creation_filetime,
                          host.lease_generation, grant.generation, grant.scene, revision,
                          request, store, owner, entry, operation,
                          (local_id, local_type), (target_id, target_type), target_name)
        if hashlib.sha256(binding.encode()).digest() != binding_digest:
            raise ValueError("combat mapping reference does not match its complete binding")
        result = cls(host, window, grant, binding, local_name, server, target_name)
        result.encode()
        return result
