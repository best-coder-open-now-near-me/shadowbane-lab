from __future__ import annotations

import unittest
from dataclasses import replace

from shadowbane_lab.client_observation import (
    NativeCharacterKind,
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
)
from shadowbane_lab.client_observation.native_group import (
    NativeGroupMemberObservation,
    NativeGroupObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.pve.authority import PvETargetCharacterKind
from shadowbane_lab.pve.authority_snapshot import (
    NativePartyAuthoritySnapshotReader,
    NativePartyAuthoritySnapshotReadError,
    build_native_party_authority_snapshot,
)


class _SequenceSource:
    def __init__(self, process_id: int, values: tuple[object, ...]) -> None:
        self.process_id = process_id
        self._values = iter(values)

    def observe(self) -> object:
        return next(self._values)


def _character(
    token: str,
    object_type: int,
    object_uuid: int,
    kind: NativeCharacterKind,
) -> NativeCharacterObservation:
    return NativeCharacterObservation(
        token=token,
        current_health=100,
        maximum_health=100,
        lt=10,
        lg=20,
        altitude=2,
        merchant=False,
        shopkeeper=False,
        banker=False,
        trainer=False,
        minion=False,
        object_key=NativeObjectKey(object_type, object_uuid),
        character_kind=kind,
    )


def _member(name: str, object_type: int, object_uuid: int) -> NativeGroupMemberObservation:
    return NativeGroupMemberObservation(
        first_name=name,
        last_name="",
        object_type=object_type,
        object_uuid=object_uuid,
        health_percent=100,
        stamina_percent=100,
        mana_percent=100,
        lt=10,
        lg=20,
        altitude=2,
        role_code=0x15,
        follow_enabled=False,
    )


class LivePvEAuthoritySnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.local_key = NativeObjectKey(1_901_199, 53)
        self.player = _character("paul-token", 1_812_817, 53, NativeCharacterKind.PLAYER)
        self.npc = _character("hulda-token", 36_760, 37, NativeCharacterKind.NPC)
        self.population = NativeCharacterPopulationObservation(
            characters=(self.player, self.npc),
            selected_target_token=self.player.token,
            player_action_target_token=None,
            scan_generation=5,
            rejected_candidates=0,
            local_player_object_key=self.local_key,
        )
        self.group = NativeGroupObservation(
            split_gold_enabled=True,
            local_follow_enabled=True,
            members=(
                _member("local", self.local_key.object_type, self.local_key.object_uuid),
                _member(
                    "paul",
                    self.player.object_key.object_type,
                    self.player.object_key.object_uuid,
                ),
            ),
        )

    def test_builds_exact_party_identity_snapshot_without_claiming_other_authority(self) -> None:
        snapshot = build_native_party_authority_snapshot(
            self.population,
            self.group,
            revision=12,
            party_group_id="live-party:12",
        )

        self.assertTrue(snapshot.party_complete)
        self.assertFalse(snapshot.ownership_complete)
        self.assertFalse(snapshot.relation_complete)
        self.assertEqual(3, len(snapshot.identities.bindings))
        self.assertEqual(2, len(snapshot.affiliations.memberships))
        records = {record.target_token: record for record in snapshot.characters}
        self.assertEqual(PvETargetCharacterKind.PLAYER, records["paul-token"].character_kind)
        self.assertEqual(PvETargetCharacterKind.NPC, records["hulda-token"].character_kind)
        self.assertIsNone(records["hulda-token"].attackable)

    def test_unresolved_roster_member_makes_party_incomplete(self) -> None:
        group = replace(
            self.group,
            members=(*self.group.members, _member("missing", 999, 53)),
        )

        snapshot = build_native_party_authority_snapshot(
            self.population,
            group,
            revision=13,
            party_group_id="live-party:13",
        )

        self.assertFalse(snapshot.party_complete)

    def test_missing_population_keys_fail_closed(self) -> None:
        population = replace(
            self.population,
            characters=(replace(self.npc, object_key=None),),
        )

        with self.assertRaisesRegex(ValueError, "no proven native object key"):
            build_native_party_authority_snapshot(
                population,
                NativeGroupObservation(False, False, ()),
                revision=14,
                party_group_id="live-party:14",
            )

    def test_reader_brackets_population_with_stable_group_reads(self) -> None:
        reader = NativePartyAuthoritySnapshotReader(
            _SequenceSource(42, (self.population,)),
            _SequenceSource(42, (self.group, self.group)),
            party_group_id="live-party",
            starting_revision=8,
        )

        snapshot = reader.observe()

        self.assertEqual(9, snapshot.revision)
        self.assertEqual(9, reader.revision)
        self.assertTrue(snapshot.party_complete)

    def test_reader_rejects_group_change_without_advancing_revision(self) -> None:
        changed = replace(self.group, local_follow_enabled=False)
        reader = NativePartyAuthoritySnapshotReader(
            _SequenceSource(42, (self.population,)),
            _SequenceSource(42, (self.group, changed)),
            party_group_id="live-party",
            starting_revision=8,
        )

        with self.assertRaisesRegex(
            NativePartyAuthoritySnapshotReadError,
            "group roster changed",
        ):
            reader.observe()

        self.assertEqual(8, reader.revision)

    def test_reader_rejects_mixed_processes(self) -> None:
        with self.assertRaisesRegex(ValueError, "different processes"):
            NativePartyAuthoritySnapshotReader(
                _SequenceSource(42, (self.population,)),
                _SequenceSource(43, (self.group, self.group)),
                party_group_id="live-party",
            )


if __name__ == "__main__":
    unittest.main()
