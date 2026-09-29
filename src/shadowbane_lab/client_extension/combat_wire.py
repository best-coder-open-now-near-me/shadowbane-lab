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


class Outcome(IntEnum):
    OBSERVED = 0
    CLIENT_OUTBOUND_QUEUED = 1
    STALE = 2
    UNAVAILABLE = 3
    INVALID = 4
    PENDING = 5
    UNCERTAIN = 6
    EXHAUSTED = 7
    LOCAL_CANCELLED = 8
    NATIVE_REJECTED = 9


class Phase(IntEnum):
    IDLE = 0
    ENGAGED = 1
    CANCELLING = 2
    RETIRED = 3
    BLOCKED = 4


CLEANUP_REQUIRED = 1
OUTBOUND_QUEUED = 2
LOCAL_CANCELLED = 4
_RECEIPT = struct.Struct("<16s16sQII216sQ4I5I32s44s")
assert _RECEIPT.size == 384
_RECEIPT_SIGNATURE = 0x57424331


@dataclass(frozen=True, slots=True)
class Receipt:
    """Local native transaction evidence, never server acceptance or damage proof."""

    request: bytes
    host: Host
    window: int
    outcome: Outcome
    flags: int
    grant: Grant
    revision: int
    local_key: tuple[int, int]
    target_key: tuple[int, int]
    phase: Phase
    mode: int
    action_state: int
    combat_target_present: bool
    binding_digest: bytes

    def encode(self) -> bytes:
        if (len(self.request) != 16 or not any(self.request)
                or type(self.window) is not int or not 0 < self.window < 2**32
                or type(self.flags) is not int or self.flags & ~7
                or type(self.revision) is not int or not 0 <= self.revision < 2**64
                or len(self.binding_digest) != 32 or not any(self.binding_digest)
                or type(self.combat_target_present) is not bool):
            raise ValueError("invalid combat receipt identity or flags")
        if any(type(v) is not int or not 0 <= v < 2**32
               for v in (*self.local_key, *self.target_key, self.mode, self.action_state)):
            raise ValueError("invalid combat receipt scalar")
        if len(self.local_key) != 2 or len(self.target_key) != 2:
            raise ValueError("invalid combat receipt object key")
        outcome, phase = Outcome(self.outcome), Phase(self.phase)
        if outcome is Outcome.CLIENT_OUTBOUND_QUEUED and (
            not self.flags & OUTBOUND_QUEUED or phase is not Phase.ENGAGED
        ):
            raise ValueError("queued combat receipt requires engaged outbound evidence")
        if outcome is Outcome.LOCAL_CANCELLED and (
            not self.flags & LOCAL_CANCELLED or self.flags & CLEANUP_REQUIRED
            or phase is not Phase.IDLE
        ):
            raise ValueError("cancelled combat receipt requires completed cleanup")
        if phase is Phase.RETIRED and self.flags & CLEANUP_REQUIRED:
            raise ValueError("retired combat receipt cannot retain cleanup authority")
        return _RECEIPT.pack(
            self.request, self.host.encode(), self.window, outcome, self.flags,
            self.grant.encode(), self.revision, *self.local_key, *self.target_key,
            _RECEIPT_SIGNATURE, phase, self.mode, self.action_state,
            int(self.combat_target_present), self.binding_digest, bytes(44),
        )

    @classmethod
    def decode(cls, payload: bytes) -> Receipt:
        if len(payload) != _RECEIPT.size:
            raise ValueError("invalid combat receipt geometry")
        (request, host, window, outcome, flags, grant, revision,
         local_a, local_b, target_a, target_b, signature, phase, mode, action,
         present, digest, reserved) = _RECEIPT.unpack(payload)
        if signature != _RECEIPT_SIGNATURE or any(reserved) or present not in (0, 1):
            raise ValueError("invalid combat receipt signature or reserved data")
        result = cls(request, Host.decode(host), window, Outcome(outcome), flags,
                     Grant.decode(grant), revision, (local_a, local_b), (target_a, target_b),
                     Phase(phase), mode, action, bool(present), digest)
        result.encode()
        return result

    def require_command(self, command: Command) -> None:
        b = command.binding
        if (self.request != b.request or self.host != command.host
                or self.window != command.window or self.grant != command.grant
                or self.revision != b.revision or self.local_key != b.local_key
                or self.target_key != b.target_key
                or self.binding_digest != hashlib.sha256(b.encode()).digest()):
            raise ValueError("combat receipt does not match the immutable command")

    @property
    def cleanup_confirmed(self) -> bool:
        return self.phase is Phase.RETIRED or (
            self.outcome is Outcome.LOCAL_CANCELLED
            and bool(self.flags & LOCAL_CANCELLED)
            and not self.flags & CLEANUP_REQUIRED
        )


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
