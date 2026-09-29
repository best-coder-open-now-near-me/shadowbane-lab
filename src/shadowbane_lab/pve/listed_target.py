"""Provisional listed players from coherent population and exact party evidence.

These candidates are saved intent. Native entry still resolves the current player
and validates its full name/server under the captured movement Grant.
"""

from dataclasses import dataclass

from shadowbane_lab.client_observation.native_population import (
    NativeCharacterKind,
    NativeCharacterObservation,
)
from shadowbane_lab.pve.attack_list import AttackListEntry, AttackListOwner, AttackListSnapshot
from shadowbane_lab.pve.authority import PvETargetCharacterKind
from shadowbane_lab.pve.model import PvECampLease, PvEObservation
from shadowbane_lab.sim.affiliations import RelationResolver


@dataclass(frozen=True, slots=True)
class ListedTarget:
    entry: AttackListEntry
    revision: int
    character: NativeCharacterObservation


def listed_targets(
    saved: AttackListSnapshot, owner: AttackListOwner, observation: PvEObservation,
    camp: PvECampLease | None,
) -> tuple[ListedTarget, ...]:
    population = observation.population
    authority = observation.authority_snapshot
    position = observation.player_position
    if (population is None or authority is None or position is None
            or not authority.party_complete or saved.revision <= 0
            or population.local_player_object_key != authority.local_player_object_key):
        return ()
    actor = authority.identities.entity_id_for(authority.local_player_object_key)
    if actor is None:
        return ()
    # A camp interruption never turns into pursuit outside the existing camp.
    if camp is not None and not camp.contains(position.lt, position.lg):
        return ()
    relations = RelationResolver(authority.affiliations)
    by_key = {character.object_key: character for character in population.characters}
    candidates = []
    for entry in saved.entries:
        identity = entry.player_identity
        if (entry.source != "manual" or identity is None or identity.server != owner.server
                or identity.object_key == authority.local_player_object_key):
            continue
        character = by_key.get(identity.object_key)
        if (character is None or character.character_kind is not NativeCharacterKind.PLAYER
                or not character.attack_eligible
                or (camp is not None and not camp.contains(character.lt, character.lg))):
            continue
        target = authority.identities.entity_id_for(identity.object_key)
        record = authority.character_for_token(character.token)
        if (target is None or record is None or record.object_key != identity.object_key
                or record.character_kind is not PvETargetCharacterKind.PLAYER
                or record.attackable is False
                or relations.facts_between(actor, target).same_party):
            continue
        candidates.append(ListedTarget(entry, saved.revision, character))
    return tuple(sorted(candidates, key=lambda candidate: (
        (candidate.character.lt - position.lt) ** 2
        + (candidate.character.lg - position.lg) ** 2,
        candidate.entry.entry_id,
    )))
