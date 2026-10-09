"""Presentation-only preparation snapshots; never native action authority."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .preparation import (
    ActorIdentity,
    Coverage,
    PreparationDecision,
    PreparationGroup,
    PreparationObservation,
    Readiness,
)
from .tracking import TrackingStatus


def _text(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("status requires bounded text")


def _time(value):
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError("status requires a finite timestamp")


@dataclass(frozen=True, slots=True)
class BuffActionStatus:
    action_id: str
    readiness: Readiness

    def __post_init__(self):
        _text(self.action_id)
        if not isinstance(self.readiness, Readiness):
            raise ValueError("status requires typed readiness")


@dataclass(frozen=True, slots=True)
class BuffGroupStatus:
    group_id: str
    coverage: Coverage
    application_pending: bool
    actions: tuple[BuffActionStatus, ...]

    def __post_init__(self):
        _text(self.group_id)
        if not isinstance(self.coverage, Coverage) or type(self.application_pending) is not bool:
            raise ValueError("status requires typed coverage and pending state")
        if (
            type(self.actions) is not tuple
            or not 1 <= len(self.actions) <= 16
            or any(not isinstance(a, BuffActionStatus) for a in self.actions)
            or len({a.action_id for a in self.actions}) != len(self.actions)
        ):
            raise ValueError("status alternatives must be bounded and unique")


@dataclass(frozen=True, slots=True)
class PreparationStatus:
    enabled: bool
    captured_at: float | None
    actor: ActorIdentity | None
    capture_sequence: int | None
    publication_revision: int | None
    admission_revision: int | None
    admission_blocks: int | None
    complete: bool
    local_pending: bool
    groups: tuple[BuffGroupStatus, ...]

    def __post_init__(self):
        if any(type(v) is not bool for v in (self.enabled, self.complete, self.local_pending)):
            raise ValueError("status flags must be boolean")
        if (
            type(self.groups) is not tuple
            or len(self.groups) > 32
            or any(not isinstance(g, BuffGroupStatus) for g in self.groups)
            or len({g.group_id for g in self.groups}) != len(self.groups)
            or sum(len(g.actions) for g in self.groups) > 32
        ):
            raise ValueError("status groups must be bounded and unique")
        observed = self.captured_at is not None
        if observed:
            _time(self.captured_at)
            if not isinstance(self.actor, ActorIdentity):
                raise ValueError("observed status requires exact actor")
            if (
                type(self.capture_sequence) is not int
                or not 0 < self.capture_sequence < 2**63
                or self.capture_sequence % 2
            ):
                raise ValueError("invalid completed capture sequence")
            if any(
                type(v) is not int or not 0 < v < 2**64
                for v in (self.publication_revision, self.admission_revision)
            ):
                raise ValueError("invalid native revisions")
            if type(self.admission_blocks) is not int or not 0 <= self.admission_blocks <= 63:
                raise ValueError("invalid admission flags")
        elif (
            any(
                v is not None
                for v in (
                    self.actor,
                    self.capture_sequence,
                    self.publication_revision,
                    self.admission_revision,
                    self.admission_blocks,
                )
            )
            or self.complete
        ):
            raise ValueError("unavailable status cannot assert native facts")
        if not self.complete and (
            self.admission_blocks
            or any(
                g.coverage is not Coverage.UNKNOWN
                or any(a.readiness is not Readiness.UNKNOWN for a in g.actions)
                for g in self.groups
            )
        ):
            raise ValueError("incomplete status cannot assert coverage/readiness")
        if not self.enabled and (observed or self.groups or self.local_pending):
            raise ValueError("disabled status cannot retain observations")

    @classmethod
    def disabled(cls):
        return cls(False, None, None, None, None, None, None, False, False, ())

    def to_dict(self):
        a = self.actor
        return dict(
            enabled=self.enabled,
            captured_at=self.captured_at,
            actor=None
            if a is None
            else dict(
                process_id=a.process_id,
                process_creation=a.process_creation,
                scene=a.scene,
                actor_key=list(a.actor_key),
                actor_token=a.actor_token,
            ),
            capture_sequence=self.capture_sequence,
            publication_revision=self.publication_revision,
            admission_revision=self.admission_revision,
            admission_blocks=self.admission_blocks,
            complete=self.complete,
            local_pending=self.local_pending,
            groups=[
                dict(
                    group_id=g.group_id,
                    coverage=g.coverage.value,
                    application_pending=g.application_pending,
                    actions=[
                        dict(action_id=a.action_id, readiness=a.readiness.value) for a in g.actions
                    ],
                )
                for g in self.groups
            ],
        )

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("invalid preparation status fields")
        v = dict(value)
        actor = v["actor"]
        if actor is not None:
            if not isinstance(actor, dict) or set(actor) != set(ActorIdentity.__dataclass_fields__):
                raise ValueError("invalid actor status")
            actor = dict(actor)
            if not isinstance(actor["actor_key"], list):
                raise ValueError("invalid actor key")
            actor["actor_key"] = tuple(actor["actor_key"])
            v["actor"] = ActorIdentity(**actor)
        if not isinstance(v["groups"], list) or len(v["groups"]) > 32:
            raise ValueError("invalid group status")
        groups = []
        for g in v["groups"]:
            if not isinstance(g, dict) or set(g) != set(BuffGroupStatus.__dataclass_fields__):
                raise ValueError("invalid group fields")
            if not isinstance(g["actions"], list) or len(g["actions"]) > 16:
                raise ValueError("invalid action status")
            actions = []
            for a in g["actions"]:
                if not isinstance(a, dict) or set(a) != {"action_id", "readiness"}:
                    raise ValueError("invalid action fields")
                actions.append(BuffActionStatus(a["action_id"], Readiness(a["readiness"])))
            groups.append(
                BuffGroupStatus(
                    g["group_id"], Coverage(g["coverage"]), g["application_pending"], tuple(actions)
                )
            )
        v["groups"] = tuple(groups)
        return cls(**v)


def capture_status(
    groups: tuple[PreparationGroup, ...],
    observation: PreparationObservation | None,
    decision: PreparationDecision | None,
    *,
    captured_at: float | None,
    local_pending: bool,
    application_pending_groups: frozenset[str] | None = None,
) -> PreparationStatus:
    """Copy only already-validated observations; elapsed time never proves an effect."""
    complete = observation is not None and observation.complete
    coverage = {} if not complete else {g.group_id: g.state for g in observation.coverage}
    readiness = {} if not complete else {a.action_id: a.state for a in observation.readiness}
    pending = set() if observation is None else set(observation.pending_applications)
    if application_pending_groups is not None:
        if type(application_pending_groups) is not frozenset:
            raise ValueError("pending groups must be an immutable policy projection")
        pending.update(application_pending_groups)
    elif decision is not None:
        pending.update(g.group_id for g in decision.groups if g.application_pending)
    return PreparationStatus(
        True,
        captured_at if observation is not None else None,
        None if observation is None else observation.actor,
        None if observation is None else observation.capture_sequence,
        None if observation is None else observation.publication_epoch,
        None if observation is None else observation.admission_revision,
        None if observation is None else observation.admission_blocks,
        complete,
        local_pending,
        tuple(
            BuffGroupStatus(
                g.group_id,
                coverage.get(g.group_id, Coverage.UNKNOWN),
                g.group_id in pending,
                tuple(
                    BuffActionStatus(a.action_id, readiness.get(a.action_id, Readiness.UNKNOWN))
                    for a in g.alternatives
                ),
            )
            for g in groups
        ),
    )


@dataclass(frozen=True, slots=True)
class PvEProgress:
    observed_at: float
    phase: str
    reason: str
    kills: int
    preparation: PreparationStatus
    tracking: TrackingStatus = TrackingStatus()

    def __post_init__(self):
        if not isinstance(self.tracking, TrackingStatus):
            raise ValueError("progress requires typed tracking status")
        _time(self.observed_at)
        _text(self.phase)
        _text(self.reason)
        if type(self.kills) is not int or not 0 <= self.kills < 2**32:
            raise ValueError("invalid kill count")
        if not isinstance(self.preparation, PreparationStatus):
            raise ValueError("progress requires typed preparation status")
        if (
            self.preparation.captured_at is not None
            and self.preparation.captured_at > self.observed_at
        ):
            raise ValueError("capture cannot postdate progress")

    def to_dict(self):
        return dict(
            observed_at=self.observed_at,
            phase=self.phase,
            reason=self.reason,
            kills=self.kills,
            preparation=self.preparation.to_dict(),
            tracking=self.tracking.to_dict(),
        )

    @classmethod
    def from_dict(cls, value):
        fields = set(cls.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) not in (fields, fields - {"tracking"}):
            raise ValueError("invalid PvE progress fields")
        return cls(
            value["observed_at"],
            value["phase"],
            value["reason"],
            value["kills"],
            PreparationStatus.from_dict(value["preparation"]),
            (TrackingStatus.from_dict(value["tracking"])
             if "tracking" in value else TrackingStatus()),
        )
