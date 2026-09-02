"""Positive, evidence-backed authority for admitting PvE combat targets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.protocol import Relation
from shadowbane_lab.pve.model import PvEObservation


class PvETargetCharacterKind(StrEnum):
    """Native character category required by strict PvE admission."""

    UNKNOWN = "unknown"
    NPC = "npc"
    PLAYER = "player"
    PET = "pet"
    SUMMON = "summon"


class PvETargetAuthorityExclusion(StrEnum):
    """Stable fail-closed reasons that prevent PvE target admission."""

    TARGET_NOT_PRESENT = "target_not_present"
    AUTHORITY_EVIDENCE_UNAVAILABLE = "authority_evidence_unavailable"
    TARGET_TOKEN_MISMATCH = "target_token_mismatch"
    TARGET_NOT_ALIVE = "target_not_alive"
    IDENTITY_CLASSIFICATION_UNAVAILABLE = "identity_classification_unavailable"
    TARGET_NOT_ARC_CHARACTER = "target_not_arc_character"
    PROTECTED_SERVICE_ROLE = "protected_service_role"
    TARGET_OBJECT_IDENTITY_UNAVAILABLE = "target_object_identity_unavailable"
    LOCAL_PLAYER_OBJECT_IDENTITY_UNAVAILABLE = "local_player_object_identity_unavailable"
    SELF_TARGET = "self_target"
    CHARACTER_KIND_UNAVAILABLE = "character_kind_unavailable"
    CHARACTER_KIND_NOT_NPC = "character_kind_not_npc"
    RELATION_UNAVAILABLE = "relation_unavailable"
    RELATION_NOT_ENEMY = "relation_not_enemy"
    PARTY_STATUS_UNAVAILABLE = "party_status_unavailable"
    PARTY_MEMBER = "party_member"
    OWNERSHIP_STATUS_UNAVAILABLE = "ownership_status_unavailable"
    FRIENDLY_OWNED = "friendly_owned"
    ATTACKABILITY_UNAVAILABLE = "attackability_unavailable"
    NOT_ATTACKABLE = "not_attackable"


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _optional_boolean(value: bool | None, field_name: str) -> None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{field_name} must be boolean when present")


def _optional_object_key(value: NativeObjectKey | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, NativeObjectKey):
        raise ValueError(f"{field_name} must be NativeObjectKey when present")
    if value.is_null:
        raise ValueError(f"{field_name} must be non-null when present")


@dataclass(frozen=True, slots=True)
class PvETargetAuthorityEvidence:
    """Exact identity, category, relation, and attackability facts for one token."""

    target_token: str
    source_revision: int
    target_object_key: NativeObjectKey | None
    local_player_object_key: NativeObjectKey | None
    character_kind: PvETargetCharacterKind = PvETargetCharacterKind.UNKNOWN
    relation: Relation | None = None
    same_party: bool | None = None
    friendly_owned: bool | None = None
    attackable: bool | None = None
    evidence_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.target_token, "target_token")
        if (
            isinstance(self.source_revision, bool)
            or not isinstance(self.source_revision, int)
            or self.source_revision < 0
        ):
            raise ValueError("source_revision must be a non-negative integer")
        _optional_object_key(self.target_object_key, "target_object_key")
        _optional_object_key(self.local_player_object_key, "local_player_object_key")
        if not isinstance(self.character_kind, PvETargetCharacterKind):
            raise ValueError("character_kind must be PvETargetCharacterKind")
        if self.relation is not None and not isinstance(self.relation, Relation):
            raise ValueError("relation must be Relation when present")
        _optional_boolean(self.same_party, "same_party")
        _optional_boolean(self.friendly_owned, "friendly_owned")
        _optional_boolean(self.attackable, "attackable")
        if not isinstance(self.evidence_sources, tuple):
            raise ValueError("evidence_sources must be a tuple")
        if len(self.evidence_sources) != len(set(self.evidence_sources)):
            raise ValueError("evidence_sources must not contain duplicates")
        for source in self.evidence_sources:
            _identifier(source, "evidence source")


@dataclass(frozen=True, slots=True)
class PvETargetAuthorityDecision:
    """Auditable admission decision for one controller observation."""

    observed_at_ms: int
    target_token: str | None
    evidence_target_token: str | None
    source_revision: int | None
    target_object_key: NativeObjectKey | None
    local_player_object_key: NativeObjectKey | None
    character_kind: PvETargetCharacterKind
    relation: Relation | None
    same_party: bool | None
    friendly_owned: bool | None
    attackable: bool | None
    evidence_sources: tuple[str, ...]
    exclusions: tuple[PvETargetAuthorityExclusion, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.observed_at_ms, bool)
            or not isinstance(self.observed_at_ms, int)
            or self.observed_at_ms < 0
        ):
            raise ValueError("observed_at_ms must be a non-negative integer")
        if self.target_token is not None:
            _identifier(self.target_token, "target_token")
        if self.evidence_target_token is not None:
            _identifier(self.evidence_target_token, "evidence_target_token")
        if self.source_revision is not None and (
            isinstance(self.source_revision, bool)
            or not isinstance(self.source_revision, int)
            or self.source_revision < 0
        ):
            raise ValueError("source_revision must be non-negative when present")
        _optional_object_key(self.target_object_key, "target_object_key")
        _optional_object_key(self.local_player_object_key, "local_player_object_key")
        if not isinstance(self.character_kind, PvETargetCharacterKind):
            raise ValueError("character_kind must be PvETargetCharacterKind")
        if self.relation is not None and not isinstance(self.relation, Relation):
            raise ValueError("relation must be Relation when present")
        _optional_boolean(self.same_party, "same_party")
        _optional_boolean(self.friendly_owned, "friendly_owned")
        _optional_boolean(self.attackable, "attackable")
        if not isinstance(self.evidence_sources, tuple):
            raise ValueError("evidence_sources must be a tuple")
        if len(self.evidence_sources) != len(set(self.evidence_sources)):
            raise ValueError("evidence_sources must not contain duplicates")
        for source in self.evidence_sources:
            _identifier(source, "evidence source")
        if not isinstance(self.exclusions, tuple):
            raise ValueError("exclusions must be a tuple")
        if any(
            not isinstance(value, PvETargetAuthorityExclusion)
            for value in self.exclusions
        ):
            raise ValueError("exclusions must contain PvETargetAuthorityExclusion values")
        if len(self.exclusions) != len(set(self.exclusions)):
            raise ValueError("authority exclusions must not contain duplicates")
        if self.target_token is None and (
            PvETargetAuthorityExclusion.TARGET_NOT_PRESENT not in self.exclusions
        ):
            raise ValueError("an absent target decision must record target_not_present")
        if self.accepted:
            if self.target_token is None:
                raise ValueError("an accepted authority decision requires a target token")
            if self.evidence_target_token != self.target_token:
                raise ValueError("accepted authority evidence must match the target token")
            if self.source_revision is None:
                raise ValueError("an accepted authority decision requires a source revision")
            if not self.evidence_sources:
                raise ValueError("an accepted authority decision requires evidence sources")
            if self.target_object_key is None or self.local_player_object_key is None:
                raise ValueError("an accepted authority decision requires exact object identities")
            if self.target_object_key == self.local_player_object_key:
                raise ValueError("an accepted authority decision cannot target the local player")
            if self.character_kind is not PvETargetCharacterKind.NPC:
                raise ValueError("an accepted authority decision requires NPC classification")
            if self.relation is not Relation.ENEMY:
                raise ValueError("an accepted authority decision requires enemy relation")
            if self.same_party is not False:
                raise ValueError("an accepted authority decision must exclude party membership")
            if self.friendly_owned is not False:
                raise ValueError("an accepted authority decision must exclude friendly ownership")
            if self.attackable is not True:
                raise ValueError("an accepted authority decision requires attackability")

    @property
    def accepted(self) -> bool:
        return not self.exclusions

    @property
    def summary_reason(self) -> str:
        if self.accepted:
            return "verified_hostile_npc"
        return self.exclusions[0].value

    def as_dict(self) -> dict[str, object]:
        return {
            "observed_at_ms": self.observed_at_ms,
            "target_token": self.target_token,
            "evidence_target_token": self.evidence_target_token,
            "accepted": self.accepted,
            "summary_reason": self.summary_reason,
            "source_revision": self.source_revision,
            "target_object_key": (
                None if self.target_object_key is None else self.target_object_key.as_dict()
            ),
            "local_player_object_key": (
                None
                if self.local_player_object_key is None
                else self.local_player_object_key.as_dict()
            ),
            "character_kind": self.character_kind.value,
            "relation": None if self.relation is None else self.relation.value,
            "same_party": self.same_party,
            "friendly_owned": self.friendly_owned,
            "attackable": self.attackable,
            "evidence_sources": list(self.evidence_sources),
            "exclusions": [value.value for value in self.exclusions],
        }


@runtime_checkable
class PvETargetAuthorityEvaluator(Protocol):
    """Evaluate one coherent PvE observation without issuing client input."""

    def evaluate(self, observation: PvEObservation) -> PvETargetAuthorityDecision: ...


@dataclass(frozen=True, slots=True)
class StaticPvETargetAuthorityEvaluator:
    """Replay/test evaluator backed by exact per-token authority evidence."""

    evidence: tuple[PvETargetAuthorityEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, tuple):
            raise ValueError("evidence must be a tuple")
        if any(not isinstance(value, PvETargetAuthorityEvidence) for value in self.evidence):
            raise ValueError("evidence must contain PvETargetAuthorityEvidence values")
        tokens = tuple(value.target_token for value in self.evidence)
        if len(tokens) != len(set(tokens)):
            raise ValueError("authority evidence target tokens must be unique")

    def evaluate(self, observation: PvEObservation) -> PvETargetAuthorityDecision:
        if not isinstance(observation, PvEObservation):
            raise ValueError("observation must be PvEObservation")
        token = observation.target.target_token
        evidence = next(
            (value for value in self.evidence if value.target_token == token),
            None,
        )
        return evaluate_pve_target_authority(observation, evidence)


def evaluate_pve_target_authority(
    observation: PvEObservation,
    evidence: PvETargetAuthorityEvidence | None,
) -> PvETargetAuthorityDecision:
    """Require positive proof instead of treating missing relation facts as hostile."""

    if not isinstance(observation, PvEObservation):
        raise ValueError("observation must be PvEObservation")
    if evidence is not None and not isinstance(evidence, PvETargetAuthorityEvidence):
        raise ValueError("evidence must be PvETargetAuthorityEvidence when present")

    target = observation.target
    if not target.target_present:
        return PvETargetAuthorityDecision(
            observed_at_ms=observation.now_ms,
            target_token=None,
            evidence_target_token=None if evidence is None else evidence.target_token,
            source_revision=None if evidence is None else evidence.source_revision,
            target_object_key=None if evidence is None else evidence.target_object_key,
            local_player_object_key=(
                None if evidence is None else evidence.local_player_object_key
            ),
            character_kind=(
                PvETargetCharacterKind.UNKNOWN
                if evidence is None
                else evidence.character_kind
            ),
            relation=None if evidence is None else evidence.relation,
            same_party=None if evidence is None else evidence.same_party,
            friendly_owned=None if evidence is None else evidence.friendly_owned,
            attackable=None if evidence is None else evidence.attackable,
            evidence_sources=() if evidence is None else evidence.evidence_sources,
            exclusions=(PvETargetAuthorityExclusion.TARGET_NOT_PRESENT,),
        )

    assert target.target_token is not None
    exclusions: list[PvETargetAuthorityExclusion] = []
    if target.current_health is None or target.current_health <= 0.0:
        exclusions.append(PvETargetAuthorityExclusion.TARGET_NOT_ALIVE)

    identity = observation.target_identity
    if identity is None or not identity.classification_available:
        exclusions.append(
            PvETargetAuthorityExclusion.IDENTITY_CLASSIFICATION_UNAVAILABLE
        )
    else:
        if identity.target_token != target.target_token:
            exclusions.append(PvETargetAuthorityExclusion.TARGET_TOKEN_MISMATCH)
        if not identity.arc_character:
            exclusions.append(PvETargetAuthorityExclusion.TARGET_NOT_ARC_CHARACTER)
        if identity.protected_role:
            exclusions.append(PvETargetAuthorityExclusion.PROTECTED_SERVICE_ROLE)

    if evidence is None:
        exclusions.append(
            PvETargetAuthorityExclusion.AUTHORITY_EVIDENCE_UNAVAILABLE
        )
        return PvETargetAuthorityDecision(
            observed_at_ms=observation.now_ms,
            target_token=target.target_token,
            evidence_target_token=None,
            source_revision=None,
            target_object_key=None,
            local_player_object_key=None,
            character_kind=PvETargetCharacterKind.UNKNOWN,
            relation=None,
            same_party=None,
            friendly_owned=None,
            attackable=None,
            evidence_sources=(),
            exclusions=tuple(dict.fromkeys(exclusions)),
        )

    if evidence.target_token != target.target_token:
        exclusions.append(PvETargetAuthorityExclusion.TARGET_TOKEN_MISMATCH)
    if evidence.target_object_key is None:
        exclusions.append(
            PvETargetAuthorityExclusion.TARGET_OBJECT_IDENTITY_UNAVAILABLE
        )
    if evidence.local_player_object_key is None:
        exclusions.append(
            PvETargetAuthorityExclusion.LOCAL_PLAYER_OBJECT_IDENTITY_UNAVAILABLE
        )
    if (
        evidence.target_object_key is not None
        and evidence.local_player_object_key is not None
        and evidence.target_object_key == evidence.local_player_object_key
    ):
        exclusions.append(PvETargetAuthorityExclusion.SELF_TARGET)
    if evidence.character_kind is PvETargetCharacterKind.UNKNOWN:
        exclusions.append(PvETargetAuthorityExclusion.CHARACTER_KIND_UNAVAILABLE)
    elif evidence.character_kind is not PvETargetCharacterKind.NPC:
        exclusions.append(PvETargetAuthorityExclusion.CHARACTER_KIND_NOT_NPC)
    if evidence.relation is None:
        exclusions.append(PvETargetAuthorityExclusion.RELATION_UNAVAILABLE)
    elif evidence.relation is not Relation.ENEMY:
        exclusions.append(PvETargetAuthorityExclusion.RELATION_NOT_ENEMY)
    if evidence.same_party is None:
        exclusions.append(PvETargetAuthorityExclusion.PARTY_STATUS_UNAVAILABLE)
    elif evidence.same_party:
        exclusions.append(PvETargetAuthorityExclusion.PARTY_MEMBER)
    if evidence.friendly_owned is None:
        exclusions.append(
            PvETargetAuthorityExclusion.OWNERSHIP_STATUS_UNAVAILABLE
        )
    elif evidence.friendly_owned:
        exclusions.append(PvETargetAuthorityExclusion.FRIENDLY_OWNED)
    if evidence.attackable is None:
        exclusions.append(PvETargetAuthorityExclusion.ATTACKABILITY_UNAVAILABLE)
    elif not evidence.attackable:
        exclusions.append(PvETargetAuthorityExclusion.NOT_ATTACKABLE)

    return PvETargetAuthorityDecision(
        observed_at_ms=observation.now_ms,
        target_token=target.target_token,
        evidence_target_token=evidence.target_token,
        source_revision=evidence.source_revision,
        target_object_key=evidence.target_object_key,
        local_player_object_key=evidence.local_player_object_key,
        character_kind=evidence.character_kind,
        relation=evidence.relation,
        same_party=evidence.same_party,
        friendly_owned=evidence.friendly_owned,
        attackable=evidence.attackable,
        evidence_sources=evidence.evidence_sources,
        exclusions=tuple(dict.fromkeys(exclusions)),
    )
