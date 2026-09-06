"""Exact-identity and affiliation snapshot adapter for PvE target authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_observation.group_affiliations import (
    project_native_party_memberships,
)
from shadowbane_lab.client_observation.native_group import NativeGroupObservation
from shadowbane_lab.client_observation.native_object import (
    NativeEntityBinding,
    NativeEntityIdentityMap,
    NativeObjectKey,
)
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterKind,
    NativeCharacterPopulationObservation,
)
from shadowbane_lab.pve.authority import (
    PvETargetAuthorityDecision,
    PvETargetAuthorityEvidence,
    PvETargetCharacterKind,
    evaluate_pve_target_authority,
)
from shadowbane_lab.pve.model import PvEObservation
from shadowbane_lab.sim.affiliations import (
    AffiliationSnapshot,
    DefaultRelationPolicy,
    GroupKey,
    GroupKind,
    OwnershipEdge,
    RelationPolicy,
    RelationResolver,
)


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _non_null_key(value: NativeObjectKey, field_name: str) -> None:
    if not isinstance(value, NativeObjectKey):
        raise ValueError(f"{field_name} must be NativeObjectKey")
    if value.is_null:
        raise ValueError(f"{field_name} must be non-null")


def _sources(values: tuple[str, ...], field_name: str) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    for value in values:
        _identifier(value, field_name)


@dataclass(frozen=True, slots=True)
class PvEAuthorityCharacterRecord:
    """Exact token-to-object projection plus independently proven character facts."""

    target_token: str
    object_key: NativeObjectKey
    character_kind: PvETargetCharacterKind
    attackable: bool | None
    evidence_sources: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.target_token, "target_token")
        _non_null_key(self.object_key, "object_key")
        if not isinstance(self.character_kind, PvETargetCharacterKind):
            raise ValueError("character_kind must be PvETargetCharacterKind")
        if self.attackable is not None and not isinstance(self.attackable, bool):
            raise ValueError("attackable must be boolean when present")
        _sources(self.evidence_sources, "character evidence sources")

    def as_dict(self) -> dict[str, object]:
        return {
            "target_token": self.target_token,
            "object_key": self.object_key.as_dict(),
            "character_kind": self.character_kind.value,
            "attackable": self.attackable,
            "evidence_sources": list(self.evidence_sources),
        }


@dataclass(frozen=True, slots=True)
class PvETargetAuthoritySnapshot:
    """One immutable authority revision with explicit completeness declarations."""

    revision: int
    local_player_object_key: NativeObjectKey
    identities: NativeEntityIdentityMap
    affiliations: AffiliationSnapshot
    characters: tuple[PvEAuthorityCharacterRecord, ...]
    party_complete: bool
    ownership_complete: bool
    relation_complete: bool
    evidence_sources: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 0
        ):
            raise ValueError("revision must be a non-negative integer")
        _non_null_key(self.local_player_object_key, "local_player_object_key")
        if not isinstance(self.identities, NativeEntityIdentityMap):
            raise ValueError("identities must be NativeEntityIdentityMap")
        if not isinstance(self.affiliations, AffiliationSnapshot):
            raise ValueError("affiliations must be AffiliationSnapshot")
        if not isinstance(self.characters, tuple):
            raise ValueError("characters must be a tuple")
        if any(not isinstance(value, PvEAuthorityCharacterRecord) for value in self.characters):
            raise ValueError("characters must contain PvEAuthorityCharacterRecord values")
        tokens = tuple(value.target_token for value in self.characters)
        object_keys = tuple(value.object_key for value in self.characters)
        if len(tokens) != len(set(tokens)):
            raise ValueError("authority character target tokens must be unique")
        if len(object_keys) != len(set(object_keys)):
            raise ValueError("authority character object keys must be unique")
        for value, field_name in (
            (self.party_complete, "party_complete"),
            (self.ownership_complete, "ownership_complete"),
            (self.relation_complete, "relation_complete"),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{field_name} must be boolean")
        _sources(self.evidence_sources, "snapshot evidence sources")

    def character_for_token(self, target_token: str) -> PvEAuthorityCharacterRecord | None:
        _identifier(target_token, "target_token")
        return next(
            (value for value in self.characters if value.target_token == target_token),
            None,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "local_player_object_key": self.local_player_object_key.as_dict(),
            "identity_bindings": [
                {
                    "object_key": binding.object_key.as_dict(),
                    "entity_id": binding.entity_id,
                }
                for binding in self.identities.canonical_bindings
            ],
            "affiliation_revision": self.affiliations.revision,
            "ownership_edges": [
                {"owner_id": edge.owner_id, "owned_id": edge.owned_id}
                for edge in self.affiliations.ownership_edges
            ],
            "characters": [value.as_dict() for value in self.characters],
            "completeness": {
                "party": self.party_complete,
                "ownership": self.ownership_complete,
                "relation": self.relation_complete,
            },
            "evidence_sources": list(self.evidence_sources),
        }


class NativePartyAuthoritySnapshotReadError(RuntimeError):
    """Raised when native party channels cannot form one coherent snapshot."""


@runtime_checkable
class NativeCharacterPopulationSource(Protocol):
    """Native population channel required by the party snapshot reader."""

    @property
    def process_id(self) -> int: ...

    def observe(self) -> NativeCharacterPopulationObservation: ...


@runtime_checkable
class NativeGroupSource(Protocol):
    """Native group channel required by the party snapshot reader."""

    @property
    def process_id(self) -> int: ...

    def observe(self) -> NativeGroupObservation: ...


def native_party_identity_signature(group: NativeGroupObservation) -> tuple[tuple[int, int], ...]:
    """Party identity coherence excludes moving coordinates, vitals, and follow state."""

    return tuple(sorted((m.object_type, m.object_uuid) for m in group.members))


def build_native_party_authority_snapshot(
    population: NativeCharacterPopulationObservation,
    group: NativeGroupObservation,
    *,
    revision: int,
    party_group_id: str,
) -> PvETargetAuthoritySnapshot:
    """Build the identity and exact-party portion of one native authority snapshot."""

    if not isinstance(population, NativeCharacterPopulationObservation):
        raise ValueError("population must be NativeCharacterPopulationObservation")
    if not isinstance(group, NativeGroupObservation):
        raise ValueError("group must be NativeGroupObservation")
    if population.local_player_object_key is None:
        raise ValueError("population has no proven local player object key")
    _identifier(party_group_id, "party_group_id")

    bindings = [
        NativeEntityBinding(
            population.local_player_object_key,
            f"native:{population.local_player_object_key.canonical_token}",
        )
    ]
    records = []
    kind_map = {
        NativeCharacterKind.PLAYER: PvETargetCharacterKind.PLAYER,
        NativeCharacterKind.NPC: PvETargetCharacterKind.NPC,
        NativeCharacterKind.PET: PvETargetCharacterKind.PET,
        NativeCharacterKind.UNKNOWN: PvETargetCharacterKind.UNKNOWN,
    }
    for character in population.characters:
        if character.object_key is None:
            raise ValueError(f"character {character.token} has no proven native object key")
        entity_id = f"native:{character.object_key.canonical_token}"
        bindings.append(NativeEntityBinding(character.object_key, entity_id))
        records.append(
            PvEAuthorityCharacterRecord(
                target_token=character.token,
                object_key=character.object_key,
                character_kind=kind_map[character.character_kind],
                attackable=None,
                evidence_sources=(
                    "native_character_population_object_key",
                    "native_character_population_kind",
                ),
            )
        )

    identities = NativeEntityIdentityMap(tuple(bindings))
    entity_by_key = {binding.object_key: binding.entity_id for binding in bindings}
    ownership_edges = tuple(
        OwnershipEdge(
            entity_by_key[character.owner_object_key], entity_by_key[character.object_key]
        )
        for character in population.characters
        if character.owner_object_key is not None and character.owner_object_key in entity_by_key
    )
    party = project_native_party_memberships(
        GroupKey(GroupKind.PARTY, party_group_id),
        group,
        identities,
        revision=revision,
        require_complete=False,
    )
    return PvETargetAuthoritySnapshot(
        revision=revision,
        local_player_object_key=population.local_player_object_key,
        identities=identities,
        affiliations=AffiliationSnapshot(
            revision=revision,
            memberships=party.memberships,
            ownership_edges=ownership_edges,
        ),
        characters=tuple(records),
        party_complete=party.complete,
        ownership_complete=False,
        relation_complete=False,
        evidence_sources=(
            "coherent_native_character_population",
            "native_group_roster_exact_key_projection",
            "native_pet_data_positive_owner_projection",
        ),
    )


class NativePartyAuthoritySnapshotReader:
    """Read group/population/group and publish only a stable party snapshot."""

    def __init__(
        self,
        population_reader: NativeCharacterPopulationSource,
        group_reader: NativeGroupSource,
        *,
        party_group_id: str,
        starting_revision: int = 0,
    ) -> None:
        if not isinstance(population_reader, NativeCharacterPopulationSource):
            raise ValueError("population_reader must implement NativeCharacterPopulationSource")
        if not isinstance(group_reader, NativeGroupSource):
            raise ValueError("group_reader must implement NativeGroupSource")
        if population_reader.process_id != group_reader.process_id:
            raise ValueError("native party authority readers resolved different processes")
        _identifier(party_group_id, "party_group_id")
        if (
            isinstance(starting_revision, bool)
            or not isinstance(starting_revision, int)
            or starting_revision < 0
        ):
            raise ValueError("starting_revision must be a non-negative integer")
        self._population_reader = population_reader
        self._group_reader = group_reader
        self._party_group_id = party_group_id
        self._revision = starting_revision
        self._process_id = population_reader.process_id

    @property
    def process_id(self) -> int:
        return self._process_id

    @property
    def revision(self) -> int:
        return self._revision

    def observe(self) -> PvETargetAuthoritySnapshot:
        if (
            self._population_reader.process_id != self._process_id
            or self._group_reader.process_id != self._process_id
        ):
            raise NativePartyAuthoritySnapshotReadError(
                "native party authority process identity changed during reader lifetime"
            )
        group_before = self._group_reader.observe()
        population = self._population_reader.observe()
        group_after = self._group_reader.observe()
        if (
            self._population_reader.process_id != self._process_id
            or self._group_reader.process_id != self._process_id
        ):
            raise NativePartyAuthoritySnapshotReadError(
                "native party authority process identity changed during sample"
            )
        if native_party_identity_signature(group_before) != native_party_identity_signature(
            group_after
        ):
            raise NativePartyAuthoritySnapshotReadError(
                "native group roster changed during party authority sample"
            )
        next_revision = self._revision + 1
        snapshot = build_native_party_authority_snapshot(
            population,
            group_after,
            revision=next_revision,
            party_group_id=self._party_group_id,
        )
        self._revision = next_revision
        return snapshot


class SnapshotPvETargetAuthorityEvaluator:
    """Resolve strict PvE evidence through existing exact identity and affiliation models."""

    def __init__(
        self,
        snapshot: PvETargetAuthoritySnapshot,
        relation_policy: RelationPolicy | None = None,
    ) -> None:
        if not isinstance(snapshot, PvETargetAuthoritySnapshot):
            raise ValueError("snapshot must be PvETargetAuthoritySnapshot")
        if relation_policy is not None and not callable(
            getattr(relation_policy, "coarse_relation", None)
        ):
            raise ValueError("relation_policy must provide coarse_relation")
        self._snapshot = snapshot
        self._relations = RelationResolver(snapshot.affiliations)
        self._policy = DefaultRelationPolicy() if relation_policy is None else relation_policy

    @property
    def snapshot(self) -> PvETargetAuthoritySnapshot:
        return self._snapshot

    def evaluate(self, observation: PvEObservation) -> PvETargetAuthorityDecision:
        if not isinstance(observation, PvEObservation):
            raise ValueError("observation must be PvEObservation")
        target_token = observation.target.target_token
        if target_token is None:
            return evaluate_pve_target_authority(observation, None)
        character = self._snapshot.character_for_token(target_token)
        if character is None:
            return evaluate_pve_target_authority(observation, None)

        actor_id = self._snapshot.identities.entity_id_for(
            self._snapshot.local_player_object_key
        )
        target_id = self._snapshot.identities.entity_id_for(character.object_key)
        relation = None
        same_party = None
        friendly_owned = None
        identity_joined = actor_id is not None and target_id is not None
        if identity_joined:
            assert actor_id is not None
            assert target_id is not None
            facts = self._relations.facts_between(actor_id, target_id)
            if self._snapshot.relation_complete:
                relation = self._policy.coarse_relation(facts)
            if self._snapshot.party_complete:
                same_party = facts.same_party
            if self._snapshot.ownership_complete:
                friendly_owned = facts.left_owns_right or facts.same_ownership_family

        sources = list(self._snapshot.evidence_sources)
        sources.extend(character.evidence_sources)
        if identity_joined:
            sources.append("native_entity_identity_map")
        if self._snapshot.party_complete:
            sources.append("complete_party_affiliation_snapshot")
        if self._snapshot.ownership_complete:
            sources.append("complete_ownership_affiliation_snapshot")
        if self._snapshot.relation_complete:
            sources.append("complete_relation_affiliation_snapshot")

        evidence = PvETargetAuthorityEvidence(
            target_token=character.target_token,
            source_revision=self._snapshot.revision,
            target_object_key=character.object_key,
            local_player_object_key=self._snapshot.local_player_object_key,
            character_kind=character.character_kind,
            relation=relation,
            same_party=same_party,
            friendly_owned=friendly_owned,
            attackable=character.attackable,
            evidence_sources=tuple(dict.fromkeys(sources)),
        )
        return evaluate_pve_target_authority(observation, evidence)
