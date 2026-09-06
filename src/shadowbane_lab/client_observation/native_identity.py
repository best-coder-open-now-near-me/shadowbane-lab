"""Exact-key joins from live native observations into simulator affiliations."""

from __future__ import annotations

from dataclasses import dataclass

from shadowbane_lab.client_observation.native_group import (
    NativeGroupMemberObservation,
    NativeGroupObservation,
)
from shadowbane_lab.client_observation.native_object import (
    NativeEntityBinding,
    NativeEntityIdentityMap,
    NativeObjectKey,
)
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterObservation,
)
from shadowbane_lab.sim.affiliations import (
    AffiliationSnapshot,
    GroupKey,
    GroupKind,
    GroupMembership,
)

__all__ = (
    "NativeEntityBinding",
    "NativeEntityIdentityMap",
    "NativeGroupPopulationJoin",
    "NativeGroupPopulationMatch",
    "NativeKeyedCharacterObservation",
    "NativeObjectKey",
    "NativePartyAffiliationProjection",
    "join_native_group_population",
    "native_group_member_key",
    "project_native_group_to_party",
)


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class NativeKeyedCharacterObservation:
    """Population observation accompanied by a separately calibrated object key."""

    object_key: NativeObjectKey
    character: NativeCharacterObservation

    def __post_init__(self) -> None:
        if not isinstance(self.object_key, NativeObjectKey):
            raise ValueError("object_key must be a NativeObjectKey")
        if self.object_key.is_null:
            raise ValueError("a keyed character requires a non-null object key")
        if not isinstance(self.character, NativeCharacterObservation):
            raise ValueError("character must be a NativeCharacterObservation")


@dataclass(frozen=True, slots=True)
class NativeGroupPopulationMatch:
    """Exact group-roster to population match by native object key."""

    member: NativeGroupMemberObservation
    character: NativeKeyedCharacterObservation

    def __post_init__(self) -> None:
        if not isinstance(self.member, NativeGroupMemberObservation):
            raise ValueError("member must be a NativeGroupMemberObservation")
        if not isinstance(self.character, NativeKeyedCharacterObservation):
            raise ValueError("character must be a NativeKeyedCharacterObservation")
        if native_group_member_key(self.member) != self.character.object_key:
            raise ValueError("group and population observations do not share an object key")


@dataclass(frozen=True, slots=True)
class NativeGroupPopulationJoin:
    """Auditable exact-key join with all unresolved observations retained."""

    matches: tuple[NativeGroupPopulationMatch, ...]
    unresolved_members: tuple[NativeGroupMemberObservation, ...]
    unmatched_characters: tuple[NativeKeyedCharacterObservation, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(value, NativeGroupPopulationMatch) for value in self.matches):
            raise ValueError("matches must contain NativeGroupPopulationMatch values")
        if any(
            not isinstance(value, NativeGroupMemberObservation) for value in self.unresolved_members
        ):
            raise ValueError("unresolved_members must contain NativeGroupMemberObservation values")
        if any(
            not isinstance(value, NativeKeyedCharacterObservation)
            for value in self.unmatched_characters
        ):
            raise ValueError(
                "unmatched_characters must contain NativeKeyedCharacterObservation values"
            )


@dataclass(frozen=True, slots=True)
class NativePartyAffiliationProjection:
    """Party affiliation snapshot plus members lacking an explicit entity binding."""

    group_key: GroupKey
    snapshot: AffiliationSnapshot
    unresolved_members: tuple[NativeGroupMemberObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.group_key, GroupKey):
            raise ValueError("group_key must be a GroupKey")
        if self.group_key.kind is not GroupKind.PARTY:
            raise ValueError("group_key must identify a party")
        if not isinstance(self.snapshot, AffiliationSnapshot):
            raise ValueError("snapshot must be an AffiliationSnapshot")
        if any(
            not isinstance(value, NativeGroupMemberObservation) for value in self.unresolved_members
        ):
            raise ValueError("unresolved_members must contain NativeGroupMemberObservation values")


def native_group_member_key(
    member: NativeGroupMemberObservation,
) -> NativeObjectKey:
    """Project an existing roster record into the common native identity type."""

    if not isinstance(member, NativeGroupMemberObservation):
        raise ValueError("member must be a NativeGroupMemberObservation")
    return NativeObjectKey(member.object_type, member.object_uuid)


def join_native_group_population(
    group: NativeGroupObservation,
    characters: tuple[NativeKeyedCharacterObservation, ...],
) -> NativeGroupPopulationJoin:
    """Join only exact object keys; never infer identity from names or state."""

    if not isinstance(group, NativeGroupObservation):
        raise ValueError("group must be a NativeGroupObservation")
    if any(not isinstance(value, NativeKeyedCharacterObservation) for value in characters):
        raise ValueError("characters must contain NativeKeyedCharacterObservation values")
    character_keys = tuple(character.object_key for character in characters)
    if len(character_keys) != len(set(character_keys)):
        raise ValueError("keyed character object keys must be unique")
    characters_by_key = {character.object_key: character for character in characters}
    matches: list[NativeGroupPopulationMatch] = []
    unresolved: list[NativeGroupMemberObservation] = []
    matched_keys: set[NativeObjectKey] = set()
    for member in group.members:
        object_key = native_group_member_key(member)
        character = characters_by_key.get(object_key)
        if object_key.is_null or character is None:
            unresolved.append(member)
            continue
        matches.append(NativeGroupPopulationMatch(member, character))
        matched_keys.add(object_key)
    unmatched = tuple(
        sorted(
            (character for character in characters if character.object_key not in matched_keys),
            key=lambda value: (
                value.object_key.object_type,
                value.object_key.object_uuid,
                value.character.token,
            ),
        )
    )
    return NativeGroupPopulationJoin(
        matches=tuple(matches),
        unresolved_members=tuple(unresolved),
        unmatched_characters=unmatched,
    )


def project_native_group_to_party(
    group: NativeGroupObservation,
    identities: NativeEntityIdentityMap,
    *,
    party_group_id: str,
    revision: int = 1,
) -> NativePartyAffiliationProjection:
    """Compile bound roster members into one party without inventing identities."""

    if not isinstance(group, NativeGroupObservation):
        raise ValueError("group must be a NativeGroupObservation")
    if not isinstance(identities, NativeEntityIdentityMap):
        raise ValueError("identities must be a NativeEntityIdentityMap")
    _identifier(party_group_id, "party_group_id")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("revision must be a non-negative integer")
    group_key = GroupKey(GroupKind.PARTY, party_group_id)
    memberships: list[GroupMembership] = []
    unresolved: list[NativeGroupMemberObservation] = []
    for member in group.members:
        object_key = native_group_member_key(member)
        entity_id = identities.entity_id_for(object_key)
        if object_key.is_null or entity_id is None:
            unresolved.append(member)
            continue
        role = "leader" if member.is_leader else ("member" if member.role_code else None)
        memberships.append(
            GroupMembership(
                entity_id=entity_id,
                group_key=group_key,
                role=role,
            )
        )
    memberships.sort(key=lambda value: value.entity_id)
    return NativePartyAffiliationProjection(
        group_key=group_key,
        snapshot=AffiliationSnapshot(
            revision=revision,
            memberships=tuple(memberships),
        ),
        unresolved_members=tuple(unresolved),
    )
