import json
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.client_observation import (
    NativePlayerActionObservation,
    NativeTargetActionCompatibilityError,
    NativeTargetActionObservation,
    NativeTargetActionPhase,
    NativeTargetActionProfile,
    NativeTargetActionReader,
    NativeTargetActionReadError,
    load_bundled_native_target_action_profile,
    load_native_target_action_profile_text,
    open_windows_native_target_action_reader,
)


def _profile() -> NativeTargetActionProfile:
    return NativeTargetActionProfile(
        profile_id="target-action-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        player_pointer_rva=0x100,
        selected_pointer_rva=0x104,
        arc_character_vtable_rva=0x200,
        arc_motion_vtable_rva=0x300,
        current_motion_pointer_offset=0x988,
        current_motion_id_offset=0x98C,
        impact_frame_offset=0x9A8,
        action_pending_offset=0x9BC,
        target_of_target_pointer_offset=0xAF8,
        idle_motion_ids=(21,),
        observed_attack_motion_ids=(106, 107, 108),
        no_impact_frame_sentinel=-1,
        maximum_motion_id=4096,
        maximum_impact_frame=4096,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
    )


class FakeProcessMemory:
    pid = 41
    executable_name = "sb.exe"
    executable_path = Path("C:/Wonderbane/sb.exe")
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4

    player = 0x12300000
    target = 0x12400000
    motion = 0x12500000
    player_motion = 0x12600000

    def __init__(self, profile: NativeTargetActionProfile) -> None:
        self.profile = profile
        self.closed = False
        self.selected = self.target
        self.motion_id = 21
        self.pending = False
        self.impact_frame = -1
        self.target_of_target = self.player
        self.player_motion_id = 21
        self.player_pending = False
        self.player_impact_frame = -1
        self.player_action_target = self.target
        self.selected_vtable = self.base_address + profile.arc_character_vtable_rva
        self.player_vtable = self.selected_vtable
        self.motion_vtable = self.base_address + profile.arc_motion_vtable_rva
        self.read_sizes: list[int] = []

    def read(self, address: int, size: int) -> bytes:
        self.read_sizes.append(size)
        if not 1 <= size <= 64:
            raise AssertionError(f"native read exceeded backend bound: {size}")
        if address == self.base_address + self.profile.selected_pointer_rva:
            return struct.pack("<I", self.selected)
        if address == self.base_address + self.profile.player_pointer_rva:
            return struct.pack("<I", self.player)
        if address == self.selected:
            return struct.pack("<I", self.selected_vtable)
        if address == self.player:
            return struct.pack("<I", self.player_vtable)
        if address == self.motion:
            return struct.pack("<I", self.motion_vtable)
        if address == self.player_motion:
            return struct.pack("<I", self.motion_vtable)
        if address == self.selected + self.profile.current_motion_pointer_offset:
            if size != 8:
                raise AssertionError(f"unexpected motion read size {size}")
            return struct.pack("<II", self.motion, self.motion_id)
        if address == self.selected + self.profile.impact_frame_offset:
            return struct.pack("<i", self.impact_frame)
        if address == self.selected + self.profile.action_pending_offset:
            return struct.pack("<I", int(self.pending))
        if address == self.selected + self.profile.target_of_target_pointer_offset:
            return struct.pack("<I", self.target_of_target)
        if address == self.player + self.profile.current_motion_pointer_offset:
            if size != 8:
                raise AssertionError(f"unexpected player motion read size {size}")
            return struct.pack("<II", self.player_motion, self.player_motion_id)
        if address == self.player + self.profile.impact_frame_offset:
            return struct.pack("<i", self.player_impact_frame)
        if address == self.player + self.profile.action_pending_offset:
            return struct.pack("<I", int(self.player_pending))
        if address == self.player + self.profile.target_of_target_pointer_offset:
            return struct.pack("<I", self.player_action_target)
        raise AssertionError(f"unexpected read at 0x{address:X} ({size} bytes)")

    def close(self) -> None:
        self.closed = True


class NativeTargetActionReaderTests(unittest.TestCase):
    def test_opens_the_guarded_process_explicitly(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        with patch(
            "shadowbane_lab.client_observation.native_target_action."
            "WindowsReadOnlyProcessMemory.open_for_process",
            return_value=process,
        ) as open_for_process:
            reader = open_windows_native_target_action_reader(
                profile,
                process_id=4320,
            )

        open_for_process.assert_called_once_with("sb.exe", 4320)
        reader.close()
        self.assertTrue(process.closed)

    def test_absent_selection_has_no_action_state(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.selected = 0

        observation = NativeTargetActionReader(profile, process).observe()

        self.assertEqual(NativeTargetActionObservation(target_present=False), observation)
        self.assertFalse(observation.interrupt_opportunity)

    def test_observes_queued_windup_impact_and_next_action_sequence(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        reader = NativeTargetActionReader(profile, process)

        idle = reader.observe()
        process.pending = True
        queued = reader.observe()
        process.pending = False
        process.motion_id = 107
        windup = reader.observe()
        process.impact_frame = 19
        impact = reader.observe()
        process.impact_frame = -1
        process.motion_id = 21
        idle_again = reader.observe()
        process.pending = True
        next_queued = reader.observe()

        self.assertEqual(NativeTargetActionPhase.IDLE, idle.phase)
        self.assertEqual(0, idle.action_sequence)
        self.assertEqual(NativeTargetActionPhase.QUEUED, queued.phase)
        self.assertTrue(queued.targeting_player)
        self.assertTrue(queued.interrupt_opportunity)
        self.assertEqual(1, queued.action_sequence)
        self.assertEqual(NativeTargetActionPhase.WINDUP, windup.phase)
        self.assertTrue(windup.interrupt_opportunity)
        self.assertEqual(1, windup.action_sequence)
        self.assertEqual(NativeTargetActionPhase.IMPACT, impact.phase)
        self.assertFalse(impact.interrupt_opportunity)
        self.assertEqual(19, impact.impact_frame)
        self.assertEqual(NativeTargetActionPhase.IDLE, idle_again.phase)
        self.assertEqual(2, next_queued.action_sequence)
        self.assertLessEqual(max(process.read_sizes), 64)

    def test_other_target_is_not_an_interrupt_opportunity(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.pending = True
        process.target_of_target = 0x12600000

        observation = NativeTargetActionReader(profile, process).observe()

        self.assertEqual(NativeTargetActionPhase.QUEUED, observation.phase)
        self.assertFalse(observation.targeting_player)
        self.assertFalse(observation.interrupt_opportunity)

    def test_new_queue_wins_over_lingering_impact_and_advances_sequence(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        reader = NativeTargetActionReader(profile, process)
        process.impact_frame = 5
        impact = reader.observe()
        process.pending = True

        queued = reader.observe()

        self.assertEqual(NativeTargetActionPhase.IMPACT, impact.phase)
        self.assertEqual(1, impact.action_sequence)
        self.assertEqual(NativeTargetActionPhase.QUEUED, queued.phase)
        self.assertEqual(2, queued.action_sequence)
        self.assertTrue(queued.interrupt_opportunity)

    def test_observes_local_player_animation_sequence_and_selected_target(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        reader = NativeTargetActionReader(profile, process)

        idle = reader.observe_player()
        process.player_pending = True
        queued = reader.observe_player()
        process.player_pending = False
        process.player_motion_id = 107
        windup = reader.observe_player()

        self.assertEqual(
            NativePlayerActionObservation(
                phase=NativeTargetActionPhase.IDLE,
                targeting_selected=True,
                motion_id=21,
                action_pending=False,
                impact_frame=None,
                action_sequence=0,
                motion_sequence=0,
            ),
            idle,
        )
        self.assertEqual(NativeTargetActionPhase.QUEUED, queued.phase)
        self.assertTrue(queued.action_active)
        self.assertEqual(1, queued.action_sequence)
        self.assertEqual(NativeTargetActionPhase.WINDUP, windup.phase)
        self.assertEqual(1, windup.action_sequence)

    def test_unknown_targeted_player_motion_still_advances_observed_sequence(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        reader = NativeTargetActionReader(profile, process)
        reader.observe_player()

        process.player_motion_id = 777
        unknown_motion = reader.observe_player()
        process.player_motion_id = 21
        idle_again = reader.observe_player()

        self.assertEqual(NativeTargetActionPhase.OTHER_MOTION, unknown_motion.phase)
        self.assertEqual(0, unknown_motion.action_sequence)
        self.assertEqual(1, unknown_motion.motion_sequence)
        self.assertFalse(unknown_motion.action_active)
        self.assertEqual(0, idle_again.action_sequence)
        self.assertEqual(2, idle_again.motion_sequence)

    def test_wrong_selected_type_fails_closed(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.selected_vtable += 4

        with self.assertRaisesRegex(NativeTargetActionReadError, "ArcCharacter"):
            NativeTargetActionReader(profile, process).observe()

    def test_wrong_motion_type_fails_closed(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.motion_vtable += 4

        with self.assertRaisesRegex(NativeTargetActionReadError, "current-motion"):
            NativeTargetActionReader(profile, process).observe()

    def test_executable_hash_mismatch_fails_before_reads(self) -> None:
        profile = _profile()
        process = FakeProcessMemory(profile)
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativeTargetActionCompatibilityError, "SHA-256"):
            NativeTargetActionReader(profile, process)


class NativeTargetActionProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_live_validated_offsets(self) -> None:
        profile = load_bundled_native_target_action_profile()

        self.assertEqual("sb.exe", profile.executable_name)
        self.assertEqual(0x16A2D98, profile.player_pointer_rva)
        self.assertEqual(0x16A2DA4, profile.selected_pointer_rva)
        self.assertEqual(0x114165C, profile.arc_character_vtable_rva)
        self.assertEqual(0x1149ADC, profile.arc_motion_vtable_rva)
        self.assertEqual(0x988, profile.current_motion_pointer_offset)
        self.assertEqual(0x98C, profile.current_motion_id_offset)
        self.assertEqual(0x9A8, profile.impact_frame_offset)
        self.assertEqual(0x9BC, profile.action_pending_offset)
        self.assertEqual(0xAF8, profile.target_of_target_pointer_offset)
        self.assertEqual((106, 107, 108), profile.observed_attack_motion_ids)

    def test_unknown_profile_field_fails_closed(self) -> None:
        profile = _profile()
        payload = {
            field: getattr(profile, field)
            for field in NativeTargetActionProfile.__dataclass_fields__
        }
        payload["idle_motion_ids"] = list(payload["idle_motion_ids"])
        payload["observed_attack_motion_ids"] = list(payload["observed_attack_motion_ids"])
        payload["surprise"] = True

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_native_target_action_profile_text(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
