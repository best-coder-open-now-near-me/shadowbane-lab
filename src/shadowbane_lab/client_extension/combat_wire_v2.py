"""Version 2 native object-action commands and correlated engagement receipts.

No GUI selection, host pointer dereference, hotbar mapping or legacy fallback is
part of this protocol. Diagnostic strings live outside the wire receipt.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from enum import IntEnum

from .combat_fence_v3 import Authority, Binding, EngagementId, RequestId
from .movement_wire import Grant, Host, Owner

VERSION = 2
_COMMAND = struct.Struct("<16sQ216s16s32s32s32s32s4IQ32s32s32s32s6I16s")
_RECEIPT = struct.Struct("<16s16sQII216sQ4I5I32s4I16s3I")
assert _COMMAND.size == 576 and _RECEIPT.size == 384
_RECEIPT_SIGNATURE = 0x57424331


class Verb(IntEnum):
    BIND_ENGAGEMENT = 37
    SUBMIT = 38
    ACTION_STATUS = 39
    CANCEL_ACTION = 40
    ENGAGEMENT_STATUS = 41
    STOP_ENGAGEMENT = 42


class Action(IntEnum):
    NONE = 0
    ATTACK = 1
    CAST = 2
    SELF_POWER = 3


class Outcome(IntEnum):
    OBSERVED = 0
    CLIENT_OUTBOUND_QUEUED = 1
    STALE = 2
    UNAVAILABLE = 3
    INVALID = 4
    PENDING = 5
    UNCERTAIN = 6
    EXHAUSTED = 7
    ENGAGEMENT_CLOSED = 8
    NATIVE_REJECTED = 9
    BOUND = 10
    ACTION_CANCELLED = 11
    DEFERRED = 12
    HISTORY_EXPIRED = 13
    POWER_REUSE_BLOCKED = 14


class Phase(IntEnum):
    UNKNOWN = 0
    BOUND = 1
    STOPPING = 2
    CLOSED = 3
    RETIRED = 4
    BLOCKED = 5


class EntryState(IntEnum):
    UNKNOWN = 0
    NEVER_ENTERED = 1
    ENTERED = 2


class ClosureProof(IntEnum):
    NONE = 0
    NEVER_BOUND = 1
    NATIVE_STOPPED = 2
    SCENE_RETIRED = 3
    HISTORY_EXPIRED = 4


CLEANUP_REQUIRED = 1
OUTBOUND_QUEUED = 2
UNCERTAIN_HISTORY = 4


def identity_digest(value: str) -> bytes:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("combat identity must be nonempty text without NUL")
    encoded = value.encode("utf-16-le", errors="strict")
    if len(encoded) > 128:
        raise ValueError("combat identity exceeds the native 64-code-unit bound")
    return hashlib.sha256(encoded).digest()


def operation_digest(grant: Grant) -> bytes:
    if grant.owner != Owner.AUTOMATION:
        raise ValueError("combat requires an automation Grant")
    return hashlib.sha256(grant.encode()[24:]).digest()


def _action_power(action: Action, power_id: int) -> None:
    if (not isinstance(action, Action) or type(power_id) is not int
            or not 0 <= power_id < 2**32
            or (power_id != 0) != (action in (Action.CAST, Action.SELF_POWER))):
        raise ValueError("action and power ID disagree")


def _verb_action(verb: Verb, action: Action) -> None:
    if not isinstance(verb, Verb):
        raise ValueError("verb must be a version 2 Verb")
    control = verb in (Verb.BIND_ENGAGEMENT, Verb.ENGAGEMENT_STATUS, Verb.STOP_ENGAGEMENT)
    if control != (action is Action.NONE):
        raise ValueError("verb and action kind disagree")


@dataclass(frozen=True, slots=True)
class Command:
    host: Host
    window: int
    grant: Grant
    binding: Binding
    request: RequestId
    action: Action
    power_id: int
    local_name: bytes
    server: bytes

    def encode(self) -> bytes:
        b = self.binding
        if not isinstance(b, Binding) or type(self.request) is not RequestId:
            raise ValueError("combat requires versioned binding and request ordinal")
        _action_power(self.action, self.power_id)
        if type(self.window) is not int or not 0 < self.window < 2**32:
            raise ValueError("combat window must be nonzero uint32")
        if ((self.host.process_id, self.host.creation_filetime, self.host.lease_generation)
                != (b.producer_pid, b.producer_creation, b.producer_generation)
                or (self.grant.generation, self.grant.scene)
                != (b.movement_generation, b.scene) or operation_digest(self.grant) != b.operation):
            raise ValueError("combat command and engagement ownership disagree")
        for digest in (self.local_name, self.server):
            if not isinstance(digest, bytes) or len(digest) != 32 or not any(digest):
                raise ValueError("native actor identity requires complete SHA-256 digests")
        return _COMMAND.pack(
            self.host.encode(), self.window, self.grant.encode(), self.request.encode(),
            b.digest, self.local_name, self.server, b.target_name, *b.local_key, *b.target_key,
            b.revision, b.store, b.owner, b.entry, b.operation, VERSION, b.authority,
            self.action, self.power_id, b.actor_address_hint, b.target_address_hint,
            b.engagement.encode(),
        )

    def require_verb(self, verb: Verb) -> None:
        self.encode()
        _verb_action(verb, self.action)

    @classmethod
    def decode(cls, data: bytes, *, client_pid: int, client_creation: int) -> Command:
        if not isinstance(data, bytes) or len(data) != _COMMAND.size:
            raise ValueError("invalid combat command geometry")
        (host_bytes, window, grant_bytes, request, digest, local_name, server, target_name,
         local_a, local_b, target_a, target_b, revision, store, owner, entry, operation,
         version, authority, action, power, actor_hint, target_hint, engagement) = (
            _COMMAND.unpack(data)
        )
        if version != VERSION:
            raise ValueError("unsupported combat command version")
        host, grant = Host.decode(host_bytes), Grant.decode(grant_bytes)
        binding = Binding(client_pid, host.process_id, client_creation, host.creation_filetime,
                          host.lease_generation, grant.generation, grant.scene, revision,
                          EngagementId.decode(engagement), store, owner, entry, operation,
                          (local_a, local_b), (target_a, target_b), target_name,
                          Authority(authority), actor_hint, target_hint)
        if binding.digest != digest:
            raise ValueError("combat mapping reference differs from complete engagement binding")
        result = cls(host, window, grant, binding, RequestId.decode(request), Action(action),
                     power, local_name, server)
        result.encode()
        return result


@dataclass(frozen=True, slots=True)
class Receipt:
    request: RequestId
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
    authority: Authority
    action: Action
    power_id: int
    engagement: EngagementId
    entry_state: EntryState
    verb: Verb
    closure: ClosureProof

    def encode(self) -> bytes:
        if (type(self.request) is not RequestId or type(self.engagement) is not EngagementId
                or not isinstance(self.authority, Authority)
                or not isinstance(self.outcome, Outcome) or not isinstance(self.phase, Phase)
                or not isinstance(self.entry_state, EntryState)
                or not isinstance(self.closure, ClosureProof)):
            raise ValueError("invalid typed combat receipt identity or state")
        _action_power(self.action, self.power_id)
        _verb_action(self.verb, self.action)
        if (type(self.window) is not int or not 0 < self.window < 2**32
                or type(self.flags) is not int or self.flags & ~7 or self.flags < 0
                or type(self.revision) is not int or not 0 <= self.revision < 2**64
                or not isinstance(self.binding_digest, bytes) or len(self.binding_digest) != 32
                or not any(self.binding_digest) or type(self.combat_target_present) is not bool):
            raise ValueError("invalid combat receipt scalar or digest")
        if (len(self.local_key) != 2 or len(self.target_key) != 2
                or any(type(v) is not int or not 0 < v < 2**32
                       for v in (*self.local_key, *self.target_key))
                or self.local_key[1] != 53 or self.local_key == self.target_key
                or self.target_key[1] != (37 if self.authority is Authority.NPC else 53)
                or (self.revision == 0) != (self.authority is Authority.NPC)
                or any(type(v) is not int or not 0 <= v < 2**32
                       for v in (self.mode, self.action_state))):
            raise ValueError("invalid combat receipt keys or native state")
        history = self.flags & (OUTBOUND_QUEUED | UNCERTAIN_HISTORY)
        if self.action is Action.NONE and (history or self.entry_state is not EntryState.UNKNOWN):
            raise ValueError("engagement control cannot claim per-action history")
        if self.flags & OUTBOUND_QUEUED and self.entry_state is not EntryState.ENTERED:
            raise ValueError("outbound history requires observed native entry")
        if self.outcome is Outcome.CLIENT_OUTBOUND_QUEUED and not self.flags & OUTBOUND_QUEUED:
            raise ValueError("queued outcome requires positive outbound evidence")
        if self.outcome is Outcome.ACTION_CANCELLED and (
            self.entry_state is not EntryState.NEVER_ENTERED or history
        ):
            raise ValueError("individual action cancellation requires definite no-entry proof")
        if self.outcome is Outcome.POWER_REUSE_BLOCKED:
            owned = self.phase in (Phase.BOUND, Phase.STOPPING, Phase.BLOCKED)
            closed = (self.phase is Phase.CLOSED
                      and self.closure is ClosureProof.NATIVE_STOPPED)
            retired = (self.phase is Phase.RETIRED
                       and self.closure is ClosureProof.SCENE_RETIRED)
            if (self.action not in (Action.CAST, Action.SELF_POWER)
                    or self.verb not in (Verb.SUBMIT, Verb.ACTION_STATUS)
                    or self.entry_state is not EntryState.NEVER_ENTERED
                    or (owned and (self.closure is not ClosureProof.NONE
                                   or self.flags != CLEANUP_REQUIRED))
                    or (not owned and (not (closed or retired) or self.flags))):
                raise ValueError("power reuse history requires exact no-entry ownership proof")
        if self.outcome is Outcome.DEFERRED:
            expected_entry = (EntryState.UNKNOWN if self.action is Action.NONE
                              else EntryState.NEVER_ENTERED)
            if self.entry_state is not expected_entry or history:
                raise ValueError("deferred operation has inconsistent entry history")
            if self.action is Action.NONE and (
                self.verb is not Verb.BIND_ENGAGEMENT or self.phase is not Phase.CLOSED
                or self.closure is not ClosureProof.NEVER_BOUND
            ):
                raise ValueError("deferred binding must close without native ownership")
        if self.closure is ClosureProof.NEVER_BOUND and self.entry_state is EntryState.ENTERED:
            raise ValueError("a never-bound engagement cannot contain entered actions")
        if self.outcome is Outcome.HISTORY_EXPIRED:
            if (self.phase is not Phase.UNKNOWN or self.entry_state is not EntryState.UNKNOWN
                    or self.closure is not ClosureProof.HISTORY_EXPIRED or self.flags):
                raise ValueError("expired history cannot claim entry or cleanup evidence")
        elif self.closure is ClosureProof.HISTORY_EXPIRED:
            raise ValueError("expired closure marker requires expired outcome")
        elif self.phase is Phase.CLOSED:
            if self.closure not in (ClosureProof.NEVER_BOUND, ClosureProof.NATIVE_STOPPED):
                raise ValueError("closed engagement requires explicit closure proof")
        elif self.phase is Phase.RETIRED:
            if self.closure is not ClosureProof.SCENE_RETIRED:
                raise ValueError("retired engagement requires actual scene retirement proof")
        elif self.closure is not ClosureProof.NONE:
            raise ValueError("live or unknown engagement cannot carry closure proof")
        if self.phase in (Phase.UNKNOWN, Phase.CLOSED, Phase.RETIRED) and (
            self.flags & CLEANUP_REQUIRED
        ):
            raise ValueError("unowned engagement state cannot claim cleanup ownership")
        if self.phase in (Phase.BOUND, Phase.STOPPING, Phase.BLOCKED) and not (
            self.flags & CLEANUP_REQUIRED
        ):
            raise ValueError("retained engagement requires a cleanup obligation")
        return _RECEIPT.pack(
            self.request.encode(), self.host.encode(), self.window, self.outcome, self.flags,
            self.grant.encode(), self.revision, *self.local_key, *self.target_key,
            _RECEIPT_SIGNATURE, self.phase, self.mode, self.action_state,
            int(self.combat_target_present), self.binding_digest, VERSION, self.authority,
            self.action, self.power_id, self.engagement.encode(), self.entry_state,
            self.verb, self.closure,
        )

    @classmethod
    def decode(cls, data: bytes) -> Receipt:
        if not isinstance(data, bytes) or len(data) != _RECEIPT.size:
            raise ValueError("invalid combat receipt geometry")
        (request, host, window, outcome, flags, grant, revision, local_a, local_b,
         target_a, target_b, signature, phase, mode, native_action, present, digest,
         version, authority, action, power, engagement, entry, verb, closure) = (
            _RECEIPT.unpack(data)
        )
        if signature != _RECEIPT_SIGNATURE or version != VERSION or present not in (0, 1):
            raise ValueError("invalid combat receipt version or signature")
        result = cls(RequestId.decode(request), Host.decode(host), window, Outcome(outcome), flags,
                     Grant.decode(grant), revision, (local_a, local_b), (target_a, target_b),
                     Phase(phase), mode, native_action, bool(present), digest, Authority(authority),
                     Action(action), power, EngagementId.decode(engagement), EntryState(entry),
                     Verb(verb), ClosureProof(closure))
        result.encode()
        return result

    def require_command(self, command: Command, verb: Verb) -> None:
        command.require_verb(verb)
        self.encode()
        b = command.binding
        if (self.request != command.request or self.host != command.host
                or self.window != command.window or self.grant != command.grant
                or self.revision != b.revision or self.local_key != b.local_key
                or self.target_key != b.target_key or self.binding_digest != b.digest
                or self.authority != b.authority or self.action != command.action
                or self.power_id != command.power_id or self.engagement != b.engagement
                or self.verb != verb):
            raise ValueError("receipt differs from immutable command or requested operation")

    @property
    def native_entered(self) -> bool | None:
        if self.entry_state is EntryState.UNKNOWN:
            return None
        return self.entry_state is EntryState.ENTERED

    @property
    def cleanup_confirmed(self) -> bool:
        return ((self.phase is Phase.CLOSED and self.closure is ClosureProof.NATIVE_STOPPED)
                or (self.phase is Phase.RETIRED and self.closure is ClosureProof.SCENE_RETIRED))
