"""Pure actor preparation policy over qualified native publication and receipt projections.

This module observes no memory and sends no input. The owning coordinator supplies
complete, mutation-safe coverage and exact native action receipts. Publication
ordering is not elapsed time; neither queueing nor a timer proves an active effect.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


def _positive(value: int, name: str, bits: int = 64) -> None:
    if type(value) is not int or not 0 < value < 2**bits:
        raise ValueError(f"{name} must be a positive uint{bits}")


def _text(value: str, name: str) -> None:
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > 128 or any(ord(c) < 32 for c in value)):
        raise ValueError(f"{name} requires bounded canonical text")


def _key(value: tuple[int, int], name: str) -> None:
    if type(value) is not tuple or len(value) != 2:
        raise ValueError(f"{name} requires an immutable native key")
    for part in value:
        _positive(part, name, 32)


def _template_key(value: tuple[int, int]) -> None:
    # Reviewed InstanceInfo template references are (positive ID, zero), unlike
    # concrete object keys. Greater Concoction Potion was observed as (980066, 0).
    if type(value) is not tuple or len(value) != 2:
        raise ValueError("template requires an immutable native template reference")
    _positive(value[0], "template ID", 32)
    if type(value[1]) is not int or value[1] != 0:
        raise ValueError("qualified native template reference requires second word zero")


class Coverage(StrEnum):
    PRESENT = "present"
    PARTIAL = "partial"
    MISSING = "missing"
    UNKNOWN = "unknown"


class Readiness(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    UNKNOWN = "unknown"


class Disposition(StrEnum):
    QUEUED = "queued"
    DEFERRED = "deferred"
    NOT_READY = "not_ready"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class EntryState(StrEnum):
    NEVER_ENTERED = "never_entered"
    ENTERED = "entered"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ActorIdentity:
    process_id: int
    process_creation: int
    scene: int
    actor_key: tuple[int, int]
    actor_token: str

    def __post_init__(self) -> None:
        _positive(self.process_id, "process_id", 32)
        _positive(self.process_creation, "process_creation")
        _positive(self.scene, "scene")
        _key(self.actor_key, "actor_key")
        if self.actor_key[1] != 53:
            raise ValueError("preparation requires the exact local player key")
        _text(self.actor_token, "actor_token")


@dataclass(frozen=True, slots=True)
class PowerOperand:
    power_id: int

    def __post_init__(self) -> None:
        _positive(self.power_id, "power_id", 32)


@dataclass(frozen=True, slots=True)
class ItemOperand:
    """Already resolved inventory identity; native entry must retain/revalidate it."""
    item_key: tuple[int, int]
    item_token: str
    template_key: tuple[int, int]

    def __post_init__(self) -> None:
        _key(self.item_key, "item_key")
        _template_key(self.template_key)
        _text(self.item_token, "item_token")


@dataclass(frozen=True, slots=True)
class PreparationAction:
    action_id: str
    power_id: int | None = None
    item_template: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        _text(self.action_id, "action_id")
        if (self.power_id is None) == (self.item_template is None):
            raise ValueError("action requires exactly one power or item template")
        if self.power_id is not None:
            _positive(self.power_id, "power_id", 32)
        if self.item_template is not None:
            _template_key(self.item_template)

    def matches(self, operand: PowerOperand | ItemOperand) -> bool:
        return ((isinstance(operand, PowerOperand) and operand.power_id == self.power_id)
                or (isinstance(operand, ItemOperand)
                    and operand.template_key == self.item_template))


@dataclass(frozen=True, slots=True)
class PreparationGroup:
    """One coverage intent; alternatives are ordered, not additive requirements.

    The canonical observer projects either active form as PRESENT. PARTIAL always
    suppresses reapplication, including a consumable's staggered effect records.
    """
    group_id: str
    alternatives: tuple[PreparationAction, ...]

    def __post_init__(self) -> None:
        _text(self.group_id, "group_id")
        if (type(self.alternatives) is not tuple or not 1 <= len(self.alternatives) <= 16
                or not all(isinstance(a, PreparationAction) for a in self.alternatives)
                or len({a.action_id for a in self.alternatives}) != len(self.alternatives)):
            raise ValueError("group requires bounded distinct immutable alternatives")


@dataclass(frozen=True, slots=True)
class CoverageEvidence:
    group_id: str
    state: Coverage

    def __post_init__(self) -> None:
        _text(self.group_id, "group_id")
        if not isinstance(self.state, Coverage):
            raise ValueError("coverage must be typed")


@dataclass(frozen=True, slots=True)
class ReadinessEvidence:
    action_id: str
    state: Readiness
    operand: PowerOperand | ItemOperand | None = None

    def __post_init__(self) -> None:
        _text(self.action_id, "action_id")
        if not isinstance(self.state, Readiness):
            raise ValueError("readiness must be typed")
        if self.operand is not None and not isinstance(self.operand, (PowerOperand, ItemOperand)):
            raise ValueError("readiness requires a typed operand")
        if self.state is Readiness.READY and self.operand is None:
            raise ValueError("ready action requires a resolved operand")


@dataclass(frozen=True, slots=True)
class PreparationObservation:
    actor: ActorIdentity
    publication_epoch: int
    complete: bool
    coverage: tuple[CoverageEvidence, ...]
    readiness: tuple[ReadinessEvidence, ...]
    pending_applications: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.actor, ActorIdentity) or type(self.complete) is not bool:
            raise ValueError("observation requires exact actor and explicit completeness")
        _positive(self.publication_epoch, "publication_epoch")
        for values, kind, field in ((self.coverage, CoverageEvidence, "group_id"),
                                    (self.readiness, ReadinessEvidence, "action_id")):
            if (type(values) is not tuple or len(values) > 256
                    or not all(isinstance(v, kind) for v in values)
                    or len({getattr(v, field) for v in values}) != len(values)):
                raise ValueError("publication evidence must be bounded, typed and unique")
        if type(self.pending_applications) is not frozenset or len(self.pending_applications) > 32:
            raise ValueError("pending application history must be an immutable bounded set")
        for group in self.pending_applications:
            _text(group, "pending group")


@dataclass(frozen=True, slots=True)
class PreparationProposal:
    sequence: int
    actor: ActorIdentity
    publication_epoch: int
    group_id: str
    action: PreparationAction
    operand: PowerOperand | ItemOperand


@dataclass(frozen=True, slots=True)
class PreparationAcknowledgement:
    """Projection of a fully correlated receipt, not raw wire or effect evidence.

    local_settled is independent positive proof that the exact action has no
    remaining local responsibility. Only the native adapter may establish it;
    effect presence, remote uncertainty and elapsed time cannot. UNCERTAIN may
    coexist with that proof when remote application remains unknown.
    """
    proposal: PreparationProposal
    disposition: Disposition
    entry_state: EntryState
    local_settled: bool

    def __post_init__(self) -> None:
        if (not isinstance(self.proposal, PreparationProposal)
                or not isinstance(self.disposition, Disposition)
                or not isinstance(self.entry_state, EntryState)
                or type(self.local_settled) is not bool):
            raise ValueError("acknowledgement requires typed receipt evidence")
        if self.disposition is Disposition.QUEUED:
            if self.entry_state is not EntryState.ENTERED:
                raise ValueError("queued requires positive native entry")
        elif (self.disposition is not Disposition.UNCERTAIN
              and (self.entry_state is not EntryState.NEVER_ENTERED or not self.local_settled)):
            raise ValueError("definitive refusal requires no entry and local settlement")


@dataclass(frozen=True, slots=True)
class GroupStatus:
    group_id: str
    coverage: Coverage
    application_pending: bool


@dataclass(frozen=True, slots=True)
class PreparationDecision:
    proposal: PreparationProposal | None
    poll_pending: bool
    groups: tuple[GroupStatus, ...]
    reason: str


class PreparationPolicyError(RuntimeError):
    """The owner must fail closed; this never confirms or discards native cleanup."""


class PreparationPolicy:
    """No default groups, native calls, timers, persistence or runtime activation."""

    def __init__(self, actor: ActorIdentity, groups: tuple[PreparationGroup, ...] = ()):
        if (not isinstance(actor, ActorIdentity) or type(groups) is not tuple
                or len(groups) > 32 or not all(isinstance(g, PreparationGroup) for g in groups)
                or len({g.group_id for g in groups}) != len(groups)):
            raise ValueError("policy requires an exact actor and unique immutable groups")
        actions = [a for group in groups for a in group.alternatives]
        if len({a.action_id for a in actions}) != len(actions):
            raise ValueError("action identities must be unique across groups")
        self.actor, self.groups = actor, groups
        self._group_ids = frozenset(g.group_id for g in groups)
        self._actions = {a.action_id: a for a in actions}
        self._last: PreparationObservation | None = None
        self._pending: PreparationProposal | None = None
        self._queued = False
        self._entered = False
        self._rejected: set[str] = set()
        self._applications: dict[str, int] = {}
        self._sequence = 0
        self._after_epoch = 0
        self._fault: str | None = None

    @property
    def pending_proposal(self) -> PreparationProposal | None:
        return self._pending

    def _fail(self, reason: str):
        self._fault = reason
        raise PreparationPolicyError(reason)

    def advance(self, observation: PreparationObservation) -> PreparationDecision:
        if self._fault is not None:
            raise PreparationPolicyError(self._fault)
        if not isinstance(observation, PreparationObservation) or observation.actor != self.actor:
            self._fail("preparation actor identity changed")
        if self._last is not None and (
            observation.publication_epoch < self._last.publication_epoch
            or (observation.publication_epoch == self._last.publication_epoch
                and observation != self._last)
        ):
            self._fail("native publication regressed or changed without an epoch")
        if (any(e.group_id not in self._group_ids for e in observation.coverage)
                or not observation.pending_applications <= self._group_ids
                or any(e.action_id not in self._actions for e in observation.readiness)):
            self._fail("publication references unconfigured preparation intent")
        for evidence in observation.readiness:
            if (evidence.operand is not None
                    and not self._actions[evidence.action_id].matches(evidence.operand)):
                self._fail("resolved operand differs from configured native identity")
        self._last = observation
        coverage = ({e.group_id: e.state for e in observation.coverage}
                    if observation.complete else {})
        for group in observation.pending_applications:
            self._applications.setdefault(group, observation.publication_epoch)
        for group, epoch in tuple(self._applications.items()):
            if (coverage.get(group) is Coverage.PRESENT and observation.publication_epoch > epoch
                    and group not in observation.pending_applications):
                del self._applications[group]
        status = tuple(GroupStatus(g.group_id, coverage.get(g.group_id, Coverage.UNKNOWN),
                                   g.group_id in self._applications) for g in self.groups)
        if self._pending is not None:
            return PreparationDecision(self._pending, True, status, "native_action_pending")
        if not observation.complete:
            return PreparationDecision(None, False, status, "observation_unknown")
        if observation.publication_epoch <= self._after_epoch:
            return PreparationDecision(None, False, status, "fresh_publication_required")
        ready = {e.action_id: e for e in observation.readiness}
        for group in self.groups:
            if (coverage.get(group.group_id) is not Coverage.MISSING
                    or group.group_id in self._applications):
                continue
            for action in group.alternatives:
                evidence = ready.get(action.action_id)
                if (evidence is None or evidence.state is not Readiness.READY
                        or action.action_id in self._rejected):
                    continue
                self._sequence += 1
                self._pending = PreparationProposal(self._sequence, self.actor,
                    observation.publication_epoch, group.group_id, action, evidence.operand)
                self._queued = self._entered = False
                return PreparationDecision(self._pending, False, status, "submit")
        reason = "covered" if all(s.coverage is Coverage.PRESENT for s in status) else "waiting"
        return PreparationDecision(None, False, status, reason)

    def acknowledge(self, acknowledgement: PreparationAcknowledgement) -> None:
        if self._fault is not None:
            raise PreparationPolicyError(self._fault)
        if (not isinstance(acknowledgement, PreparationAcknowledgement)
                or self._pending is None or acknowledgement.proposal != self._pending):
            self._fail("receipt does not match the exact pending preparation proposal")
        ack = acknowledgement
        if self._queued and ack.disposition not in (Disposition.QUEUED, Disposition.UNCERTAIN):
            self._fail("positive queue history cannot become never-entered refusal")
        if self._entered and ack.entry_state is EntryState.NEVER_ENTERED:
            self._fail("positive entry history cannot become never-entered refusal")
        self._entered |= ack.entry_state is EntryState.ENTERED
        if ack.disposition is Disposition.REJECTED:
            self._rejected.add(self._pending.action.action_id)
        if ack.disposition is Disposition.QUEUED:
            self._queued = True
        if (ack.disposition is Disposition.QUEUED
                or (ack.disposition is Disposition.UNCERTAIN
                    and ack.entry_state is not EntryState.NEVER_ENTERED)):
            # Possible remote application suppresses duplicates independently of
            # proven local completion. Other groups need not wait for its effect.
            self._applications.setdefault(self._pending.group_id, self._last.publication_epoch)
        if ack.local_settled:
            self._after_epoch = self._last.publication_epoch
            self._pending = None
            self._queued = self._entered = False
