"""Strict v3 shared actor/action codec; no transport activation or legacy fallback."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from enum import IntEnum

from .actor_action_fence import (
    ActorBinding,
    ContextBinding,
    ContextId,
    OwnerId,
    Purpose,
    RequestId,
    address,
    digest,
    key,
    uint,
)
from .combat_wire_v2 import Outcome
from .movement_wire import Grant, Host, Owner

VERSION = 3
CAPABILITY = 0x80
ADMISSION_CAPABILITY = 0x100
PREPARATION_CAPABILITY = 0x200
NO_SELECTOR = 0xFFFFFFFF
ZERO_DIGEST = bytes(32)
_COMMAND = struct.Struct("<16sQ216s16s16s16s32s32s10I32sQ16sI124s")
_RECEIPT = struct.Struct("<16s16sQII216s16s16s32s14I")
assert _COMMAND.size == 576 and _RECEIPT.size == 384


class Verb(IntEnum):
    OPEN_OWNER = 43
    ATTACH_CONTEXT = 44
    SUBMIT = 45
    ACTION_STATUS = 46
    CANCEL_ACTION = 47
    CONTEXT_STATUS = 48
    STOP_CONTEXT = 49
    OWNER_STATUS = 50
    STOP_OWNER = 51
    OBSERVE_ACTOR = 52
    REGISTER_SELECTORS = 53


class Action(IntEnum):
    NONE = 0
    ATTACK = 1
    CAST = 2
    SELF_POWER = 3
    USE_ITEM = 4


class Recipient(IntEnum):
    NONE = 0
    ACTOR = 1
    TARGET = 2


class Phase(IntEnum):
    UNKNOWN = 0
    BOUND = 1
    STOPPING = 2
    CLOSED = 3
    RETIRED = 4
    BLOCKED = 5


class Entry(IntEnum):
    UNKNOWN = 0
    NEVER_ENTERED = 1
    ENTERED = 2


class LocalSettlement(IntEnum):
    UNKNOWN = 0
    PENDING = 1
    SETTLED = 2


class Application(IntEnum):
    NONE = 0
    PENDING = 1
    OBSERVED = 2
    UNKNOWN = 3
    INTERRUPTED = 4


class Closure(IntEnum):
    NONE = 0
    NEVER_BOUND = 1
    NATIVE_STOPPED = 2
    SCENE_RETIRED = 3
    HISTORY_EXPIRED = 4
    LOCAL_RELEASED = 5


class ClosureScope(IntEnum):
    NONE = 0
    OWNER = 1
    CONTEXT = 2


class Reason(IntEnum):
    NONE = 0
    POWER_REUSE = 1
    RECOVERY = 2
    INITIATION = 3
    STANCE = 4
    OBSERVATION = 5
    ITEM = 6
    TARGET_OCCUPIED = 7
    LOCAL_ACTION = 8
    NATIVE_USE = 9
    CHILD_CLEANUP = 10
    ADMISSION_CHANGED = 11
    MANUAL_ACTIVITY = 12


OWNER_CLEANUP = 1
CONTEXT_CLEANUP = 2
OUTBOUND_QUEUED = 4
UNCERTAIN_HISTORY = 8
APPLICATION_PENDING = 16
_OWNED = (Phase.BOUND, Phase.STOPPING, Phase.BLOCKED)
_ACTION_VERBS = (Verb.SUBMIT, Verb.ACTION_STATUS, Verb.CANCEL_ACTION)
_READ_VERBS = (Verb.OBSERVE_ACTOR, Verb.REGISTER_SELECTORS)
_CONTEXT_VERBS = (Verb.ATTACH_CONTEXT, Verb.CONTEXT_STATUS, Verb.STOP_CONTEXT)


def _id(value, kind, optional=False):
    if value is None and optional:
        return bytes(16)
    if type(value) is not kind:
        raise ValueError("wrong ordinal namespace")
    return value.encode()


def _decode_id(value, kind):
    return kind.decode(value) if any(value) else None


def _grant(value):
    if value is None:
        return bytes(216)
    if not isinstance(value, Grant) or value.owner is not Owner.AUTOMATION:
        raise ValueError("mutation requires an exact automation Grant")
    return value.encode()


@dataclass(frozen=True, slots=True)
class Command:
    host: Host
    window: int
    grant: Grant | None
    request: RequestId
    parent_id: OwnerId | None
    context_id: ContextId | None
    parent_digest: bytes
    context_digest: bytes
    action: Action = Action.NONE
    power_id: int = 0
    item_key: tuple[int, int] = (0, 0)
    template_key: tuple[int, int] = (0, 0)
    item_hint: int = 0
    recipient: Recipient = Recipient.NONE
    template_hint: int = 0
    selector_index: int = NO_SELECTOR
    manifest_digest: bytes = ZERO_DIGEST
    publication_revision: int = 0
    snapshot_id: bytes = bytes(16)

    def encode(self):
        if not isinstance(self.host, Host):
            raise ValueError("invalid host")
        uint(self.window, positive=True)
        _id(self.request, RequestId)
        _id(self.parent_id, OwnerId, True)
        _id(self.context_id, ContextId, True)
        digest(self.parent_digest, zero=self.parent_id is None)
        digest(self.context_digest, zero=self.context_id is None)
        if self.context_id is not None and self.parent_id is None:
            raise ValueError("context has no parent")
        if self.grant is not None and self.parent_id is None:
            raise ValueError("movement Grant requires owner")
        if self.grant is None and self.context_id is not None:
            raise ValueError("preparation cannot own a target context")
        grant = _grant(self.grant)
        if not isinstance(self.action, Action) or not isinstance(self.recipient, Recipient):
            raise ValueError("untyped action/recipient")
        uint(self.power_id)
        uint(self.selector_index)
        uint(self.publication_revision, 64)
        if type(self.snapshot_id) is not bytes or len(self.snapshot_id) != 16:
            raise ValueError("invalid publication identity")
        selected = self.selector_index != NO_SELECTOR
        digest(self.manifest_digest, zero=not selected)
        if selected and self.selector_index >= 32:
            raise ValueError("selector outside bounded manifest")
        if not selected and (self.publication_revision or any(self.snapshot_id)):
            raise ValueError("publication evidence without selector")
        if bool(self.publication_revision) != bool(any(self.snapshot_id)):
            raise ValueError("incomplete publication reference")
        for operand_key in (self.item_key, self.template_key):
            if type(operand_key) is not tuple or len(operand_key) != 2:
                raise ValueError("operand key must be immutable")
            for word in operand_key:
                uint(word)
        uint(self.item_hint)
        uint(self.template_hint)
        item = self.action is Action.USE_ITEM
        if item:
            key(self.item_key)
            if type(self.template_key) is not tuple or len(self.template_key) != 2:
                raise ValueError("invalid item template")
            uint(self.template_key[0], positive=True)
            if type(self.template_key[1]) is not int or self.template_key[1] != 0:
                raise ValueError("item template second word must be zero")
            address(self.item_hint)
            address(self.template_hint)
            if self.item_hint == self.template_hint:
                raise ValueError("item instance aliases template")
        elif (
            self.item_key != (0, 0)
            or self.template_key != (0, 0)
            or self.item_hint
            or self.template_hint
        ):
            raise ValueError("non-item has item operand")
        if (self.power_id != 0) != (self.action in (Action.CAST, Action.SELF_POWER)):
            raise ValueError("action/power mismatch")
        expected = (
            Recipient.NONE
            if self.action is Action.NONE
            else Recipient.ACTOR
            if self.action in (Action.SELF_POWER, Action.USE_ITEM)
            else Recipient.TARGET
        )
        if self.recipient is not expected:
            raise ValueError("action recipient mismatch")
        if self.recipient is Recipient.TARGET and self.context_id is None:
            raise ValueError("target action has no target context")
        if item and self.context_id is not None:
            raise ValueError("item consumption is actor-scoped")
        if self.action is not Action.NONE and self.parent_id is None:
            raise ValueError("unowned mutation")
        if self.action in (Action.SELF_POWER, Action.USE_ITEM) and self.context_id is None:
            if not selected or not self.publication_revision:
                raise ValueError("preparation requires exact manifest publication")
        return _COMMAND.pack(
            self.host.encode(),
            self.window,
            grant,
            self.request.encode(),
            _id(self.parent_id, OwnerId, True),
            _id(self.context_id, ContextId, True),
            self.parent_digest,
            self.context_digest,
            self.action,
            self.power_id,
            *self.item_key,
            *self.template_key,
            self.item_hint,
            self.recipient,
            self.template_hint,
            self.selector_index,
            self.manifest_digest,
            self.publication_revision,
            self.snapshot_id,
            VERSION,
            bytes(124),
        )

    def require_verb(self, verb):
        self.encode()
        if not isinstance(verb, Verb) or (
            (verb in _ACTION_VERBS) != (self.action is not Action.NONE)
        ):
            raise ValueError("verb/action mismatch")
        if verb in _READ_VERBS:
            if self.parent_id is not None or self.grant is not None:
                raise ValueError("observation cannot carry mutation authority")
            if verb is Verb.REGISTER_SELECTORS and self.selector_index == NO_SELECTOR:
                raise ValueError("selector registration requires manifest")
        elif self.parent_id is None:
            raise ValueError("owner operation lacks owner")
        if verb in _CONTEXT_VERBS and self.context_id is None:
            raise ValueError("context control lacks target context")
        if verb in (Verb.OPEN_OWNER, Verb.OWNER_STATUS, Verb.STOP_OWNER) and self.context_id:
            raise ValueError("parent control carries target context")

    def require_bindings(self, parent, context=None):
        if not isinstance(parent, ActorBinding) or self.parent_digest != parent.digest:
            raise ValueError("wrong parent fence")
        if (
            self.parent_id != parent.owner_id
            or (self.host.process_id, self.host.creation_filetime, self.host.lease_generation)
            != (parent.producer_pid, parent.producer_creation, parent.producer_generation)
        ):
            raise ValueError("parent namespace mismatch")
        if parent.purpose is Purpose.PREPARATION:
            if (self.grant is not None or self.context_id is not None
                    or hashlib.sha256(parent.owner_id.encode()).digest() != parent.operation):
                raise ValueError("preparation cannot carry movement or target authority")
        elif (self.grant is None
                or (self.grant.generation, self.grant.scene)
                != (parent.movement_generation, parent.scene)
                or hashlib.sha256(self.grant.encode()[24:]).digest() != parent.operation):
            raise ValueError("parent movement namespace mismatch")
        if self.context_id is None:
            if context is not None:
                raise ValueError("unexpected target context")
        elif not isinstance(context, ContextBinding):
            raise ValueError("missing target context")
        else:
            context.require_parent(parent)
            if self.context_id != context.context_id or self.context_digest != context.digest:
                raise ValueError("wrong target fence")

    @property
    def digest(self):
        return hashlib.sha256(self.encode()).digest()

    @classmethod
    def decode(cls, data):
        if type(data) is not bytes or len(data) != 576:
            raise ValueError("invalid actor command size")
        v = _COMMAND.unpack(data)
        if v[-2] != VERSION or any(v[-1]):
            raise ValueError("invalid actor command version/reserved")
        result = cls(
            Host.decode(v[0]),
            v[1],
            Grant.decode(v[2]) if any(v[2]) else None,
            RequestId.decode(v[3]),
            _decode_id(v[4], OwnerId),
            _decode_id(v[5], ContextId),
            v[6],
            v[7],
            Action(v[8]),
            v[9],
            tuple(v[10:12]),
            tuple(v[12:14]),
            v[14],
            Recipient(v[15]),
            v[16],
            v[17],
            v[18],
            v[19],
            v[20],
        )
        result.encode()
        return result


@dataclass(frozen=True, slots=True)
class Receipt:
    request: RequestId
    host: Host
    window: int
    outcome: Outcome
    flags: int
    grant: Grant | None
    parent_id: OwnerId | None
    context_id: ContextId | None
    command_digest: bytes
    verb: Verb
    action: Action
    entry: Entry = Entry.UNKNOWN
    local_settlement: LocalSettlement = LocalSettlement.UNKNOWN
    owner_phase: Phase = Phase.UNKNOWN
    context_phase: Phase = Phase.UNKNOWN
    closure: Closure = Closure.NONE
    application: Application = Application.NONE
    mode: int = 0
    action_state: int = 0
    combat_target_present: bool = False
    reason: Reason = Reason.NONE
    closure_scope: ClosureScope = ClosureScope.NONE

    def encode(self):
        _id(self.request, RequestId)
        _id(self.parent_id, OwnerId, True)
        _id(self.context_id, ContextId, True)
        digest(self.command_digest)
        uint(self.window, positive=True)
        uint(self.flags)
        uint(self.mode)
        uint(self.action_state)
        if self.flags & ~31 or type(self.combat_target_present) is not bool:
            raise ValueError("invalid receipt flags/state")
        for value, kind in (
            (self.outcome, Outcome),
            (self.verb, Verb),
            (self.action, Action),
            (self.entry, Entry),
            (self.local_settlement, LocalSettlement),
            (self.owner_phase, Phase),
            (self.context_phase, Phase),
            (self.closure, Closure),
            (self.application, Application),
            (self.reason, Reason),
            (self.closure_scope, ClosureScope),
        ):
            if not isinstance(value, kind):
                raise ValueError("unknown receipt enum")
        if (
            (self.verb in _ACTION_VERBS) != (self.action is not Action.NONE)
            or bool(self.flags & OWNER_CLEANUP) != (self.owner_phase in _OWNED)
            or bool(self.flags & CONTEXT_CLEANUP) != (self.context_phase in _OWNED)
        ):
            raise ValueError("receipt action/ownership mismatch")
        if self.parent_id is None:
            if (
                self.grant is not None
                or self.context_id is not None
                or self.owner_phase is not Phase.UNKNOWN
                or self.verb not in _READ_VERBS
            ):
                raise ValueError("unowned receipt is not read-only")
        elif self.verb in _READ_VERBS:
            raise ValueError("receipt lacks exact owner Grant")
        if (
            self.action in (Action.ATTACK, Action.CAST)
            and self.context_id is None
            or self.action is Action.USE_ITEM
            and self.context_id is not None
        ):
            raise ValueError("receipt action has wrong target scope")
        if self.grant is None and self.context_id is not None:
            raise ValueError("preparation receipt cannot own a target context")
        if self.context_id is None and self.context_phase is not Phase.UNKNOWN:
            raise ValueError("context phase without context")
        if self.verb in _CONTEXT_VERBS and self.context_id is None:
            raise ValueError("context receipt lacks context")
        if self.verb in (Verb.OPEN_OWNER, Verb.OWNER_STATUS, Verb.STOP_OWNER) and self.context_id:
            raise ValueError("parent receipt carries context")
        if self.context_phase in _OWNED and self.owner_phase not in _OWNED:
            raise ValueError("live child under closed parent")
        history = self.flags & (OUTBOUND_QUEUED | UNCERTAIN_HISTORY)
        if self.action is Action.NONE and (
            history
            or self.entry is not Entry.UNKNOWN
            or self.local_settlement is not LocalSettlement.UNKNOWN
        ):
            raise ValueError("control cannot assert action settlement/history")
        if self.flags & OUTBOUND_QUEUED and self.entry is not Entry.ENTERED:
            raise ValueError("queue requires native entry")
        if self.entry is Entry.NEVER_ENTERED and (
            history or self.application is not Application.NONE
        ):
            raise ValueError("no-entry action has possible effects")
        if (
            self.entry is Entry.NEVER_ENTERED
            and self.local_settlement is not LocalSettlement.SETTLED
        ):
            raise ValueError("no-entry action must be locally settled")
        if self.outcome is Outcome.CLIENT_OUTBOUND_QUEUED and not self.flags & OUTBOUND_QUEUED:
            raise ValueError("queued outcome lacks append proof")
        if bool(self.flags & APPLICATION_PENDING) != (
            self.application in (Application.PENDING, Application.UNKNOWN)
        ):
            raise ValueError("application flag disagrees with remote history")
        if self.application is Application.INTERRUPTED and (
            self.entry is not Entry.ENTERED or not self.flags & OUTBOUND_QUEUED
        ):
            raise ValueError("interruption requires retained positive entry and queue history")
        if self.application is not Application.NONE and self.action not in (
            Action.SELF_POWER,
            Action.CAST,
            Action.USE_ITEM,
        ):
            raise ValueError("non-power/item application claim")
        if (self.outcome is Outcome.HISTORY_EXPIRED) != (self.closure is Closure.HISTORY_EXPIRED):
            raise ValueError("expired outcome requires unknown historical closure")
        if self.closure_scope is ClosureScope.CONTEXT and self.owner_phase in (
            Phase.CLOSED,
            Phase.RETIRED,
        ):
            raise ValueError("context closure cannot prove terminal parent")
        if (
            self.closure_scope is ClosureScope.OWNER
            and self.context_phase in (Phase.CLOSED, Phase.RETIRED)
            and self.context_phase is not self.owner_phase
        ):
            raise ValueError("parent closure disagrees with terminal child")
        if self.closure is Closure.HISTORY_EXPIRED and self.closure_scope is not ClosureScope.NONE:
            raise ValueError("expired history has no closure scope")
        scope_phase = (
            self.owner_phase if self.closure_scope is ClosureScope.OWNER else self.context_phase
        )
        if self.closure is Closure.NONE:
            if (
                self.closure_scope is not ClosureScope.NONE
                or self.owner_phase in (Phase.CLOSED, Phase.RETIRED)
                or self.context_phase in (Phase.CLOSED, Phase.RETIRED)
            ):
                raise ValueError("closed lifecycle requires exact closure proof")
        elif self.closure is Closure.HISTORY_EXPIRED:
            if (
                self.outcome is not Outcome.HISTORY_EXPIRED
                or self.flags
                or self.entry is not Entry.UNKNOWN
                or self.owner_phase is not Phase.UNKNOWN
                or self.context_phase is not Phase.UNKNOWN
                or self.local_settlement is not LocalSettlement.UNKNOWN
            ):
                raise ValueError("expired history cannot prove no entry or closure")
        else:
            if self.closure_scope is ClosureScope.NONE:
                raise ValueError("closure lacks explicit scope")
            expected = Phase.RETIRED if self.closure is Closure.SCENE_RETIRED else Phase.CLOSED
            if scope_phase is not expected:
                raise ValueError("closure and scoped lifecycle disagree")
            if self.closure_scope is ClosureScope.CONTEXT and self.context_id is None:
                raise ValueError("target closure without target")
            if self.closure is Closure.NATIVE_STOPPED and (
                self.mode != 1 or self.combat_target_present
            ):
                raise ValueError("native stop lacks qualified local stop state")
            if (
                self.action is not Action.NONE
                and self.local_settlement is not LocalSettlement.SETTLED
            ):
                raise ValueError("terminal closure cannot retain local action responsibility")
            if (
                self.closure is Closure.NEVER_BOUND
                and self.action is not Action.NONE
                and self.entry is not Entry.NEVER_ENTERED
            ):
                raise ValueError("never-bound action requires positive no-entry proof")
            if self.closure is Closure.NEVER_BOUND and self.entry is Entry.ENTERED:
                raise ValueError("never-bound cannot contain entered history")
        if self.outcome in (
            Outcome.DEFERRED,
            Outcome.ACTION_CANCELLED,
            Outcome.POWER_REUSE_BLOCKED,
        ):
            if self.action is not Action.NONE and (
                self.entry is not Entry.NEVER_ENTERED
                or self.local_settlement is not LocalSettlement.SETTLED
                or history
            ):
                raise ValueError("definitive action refusal requires no entry")
        if self.reason in (
            Reason.TARGET_OCCUPIED,
            Reason.LOCAL_ACTION,
            Reason.NATIVE_USE,
            Reason.CHILD_CLEANUP,
            Reason.ADMISSION_CHANGED,
            Reason.MANUAL_ACTIVITY,
        ) and (
            self.verb not in (Verb.SUBMIT, Verb.ACTION_STATUS)
            or self.action is Action.NONE
            or self.entry is not Entry.NEVER_ENTERED
            or self.local_settlement is not LocalSettlement.SETTLED
            or history
            or self.application is not Application.NONE
            or self.outcome is not Outcome.DEFERRED
        ):
            raise ValueError("invalid typed admission refusal")
        if self.outcome is Outcome.POWER_REUSE_BLOCKED:
            if (
                self.action not in (Action.CAST, Action.SELF_POWER)
                or self.verb not in (Verb.SUBMIT, Verb.ACTION_STATUS)
                or self.reason is not Reason.POWER_REUSE
                or self.owner_phase is Phase.UNKNOWN
            ):
                raise ValueError("invalid power reuse refusal history")
        elif self.reason is Reason.POWER_REUSE:
            raise ValueError("reuse reason without typed outcome")
        return _RECEIPT.pack(
            self.request.encode(),
            self.host.encode(),
            self.window,
            self.outcome,
            self.flags,
            _grant(self.grant),
            _id(self.parent_id, OwnerId, True),
            _id(self.context_id, ContextId, True),
            self.command_digest,
            VERSION,
            self.verb,
            self.action,
            self.entry,
            self.local_settlement,
            self.owner_phase,
            self.context_phase,
            self.closure,
            self.application,
            self.mode,
            self.action_state,
            self.combat_target_present,
            self.reason,
            self.closure_scope,
        )

    @classmethod
    def decode(cls, data):
        if type(data) is not bytes or len(data) != 384:
            raise ValueError("invalid receipt size")
        v = _RECEIPT.unpack(data)
        if v[9] != VERSION:
            raise ValueError("invalid receipt version")
        result = cls(
            RequestId.decode(v[0]),
            Host.decode(v[1]),
            v[2],
            Outcome(v[3]),
            v[4],
            Grant.decode(v[5]) if any(v[5]) else None,
            _decode_id(v[6], OwnerId),
            _decode_id(v[7], ContextId),
            v[8],
            Verb(v[10]),
            Action(v[11]),
            Entry(v[12]),
            LocalSettlement(v[13]),
            Phase(v[14]),
            Phase(v[15]),
            Closure(v[16]),
            Application(v[17]),
            v[18],
            v[19],
            bool(v[20]),
            Reason(v[21]),
            ClosureScope(v[22]),
        )
        if v[20] > 1 or result.encode() != data:
            raise ValueError("noncanonical receipt")
        return result

    def require_command(self, command, verb):
        command.require_verb(verb)
        self.encode()
        if (
            self.request != command.request
            or self.host != command.host
            or self.window != command.window
            or self.grant != command.grant
            or self.parent_id != command.parent_id
            or self.context_id != command.context_id
            or self.command_digest != command.digest
            or self.action != command.action
            or self.verb is not verb
        ):
            raise ValueError("receipt differs from exact immutable command")
