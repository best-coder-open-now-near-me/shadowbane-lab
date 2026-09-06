from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import (
    NativeCharacterKind,
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
)
from shadowbane_lab.client_observation.native_group import (
    NativeGroupMemberObservation,
    NativeGroupObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.protocol import DispatchResult
from shadowbane_lab.pve import (
    NativePvEObservationSource,
    PvEController,
    PvEControllerConfig,
    PvEObservationCoherenceError,
    PvERunner,
)
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
        changed = replace(self.group, members=self.group.members[:1])
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

    def _frame_inputs(self, *, groups=None, health=None):
        target = NativeTargetHealthObservation(
            target_present=True, current_health=100, maximum_health=100,
            target_token=self.player.token,
        )
        vitals = NativePlayerVitalsObservation(
            current_health=100, maximum_health=100, current_mana=100,
            maximum_mana=100, current_stamina=100, maximum_stamina=100,
        )
        return dict(
            health_reader=_SequenceSource(42, health or (target, target)),
            player_vitals_reader=SimpleNamespace(observe=lambda: vitals),
            population_reader=_SequenceSource(42, (self.population,)),
            group_reader=_SequenceSource(42, groups or (self.group, self.group)),
            party_group_id="fixture-party",
            combat_log_reader=SimpleNamespace(read_new_entries=lambda: ()),
        )

    def test_coherent_frame_carries_party_snapshot_while_members_move(self) -> None:
        moving = replace(
            self.group, members=tuple(replace(m, lt=m.lt + 10) for m in self.group.members),
            local_follow_enabled=False,
        )
        source = NativePvEObservationSource(**self._frame_inputs(groups=(self.group, moving)))
        frame = source.observe(now_ms=27, target_action_active=False, player_action_active=False)
        self.assertTrue(frame.authority_snapshot.party_complete)
        self.assertEqual(1, frame.authority_snapshot.revision)
        self.assertEqual(self.local_key, frame.authority_snapshot.local_player_object_key)

    def test_group_identity_change_rejects_frame(self) -> None:
        changed = replace(self.group, members=self.group.members[:1])
        source = NativePvEObservationSource(**self._frame_inputs(groups=(self.group, changed)))
        with self.assertRaisesRegex(PvEObservationCoherenceError, "party roster changed"):
            source.observe(now_ms=27, target_action_active=False, player_action_active=False)

    def test_selection_change_rejects_authority_frame(self) -> None:
        first = NativeTargetHealthObservation(
            target_present=True, current_health=100, maximum_health=100,
            target_token=self.player.token,
        )
        second = replace(first, target_token=self.npc.token)
        source = NativePvEObservationSource(**self._frame_inputs(health=(first, second)))
        with self.assertRaisesRegex(PvEObservationCoherenceError, "selected target changed"):
            source.observe(now_ms=27, target_action_active=False, player_action_active=False)

    def test_runner_preserves_same_frame_party_authority_in_trace(self) -> None:
        stop = EventEmergencyStop()
        controller = PvEController(PvEControllerConfig())
        class Dispatcher:
            def dispatch(self, intent, *, sequence):
                return DispatchResult(
                    adapter_name="test", correlation_id=str(sequence), accepted=True,
                )

        runner = PvERunner(
            controller=controller, **self._frame_inputs(), dispatcher=Dispatcher(),
            stop_signal=stop, trace_sink=lambda step: stop.trip(),
            sleeper=lambda seconds: None,
        )
        result = runner.run()
        authority = result.trace[0].as_dict()["target_authority"]
        self.assertEqual(1, authority["source_revision"])
        self.assertIn("party_member", authority["exclusions"])
        self.assertIn("relation_unavailable", authority["exclusions"])
        self.assertFalse(controller.require_verified_target_authority)


if __name__ == "__main__":
    unittest.main()
