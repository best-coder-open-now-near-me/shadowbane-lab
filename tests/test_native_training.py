from __future__ import annotations

import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation.native_progression_core import (
    NativePlayerProgressionCoreObservation,
)
from shadowbane_lab.client_observation.native_training import (
    NativePlayerTrainingCompatibilityError,
    NativePlayerTrainingObservation,
    NativePlayerTrainingProfile,
    NativePlayerTrainingReader,
    NativePlayerTrainingReadError,
    NativeTrainingEntry,
    NativeTrainingToken,
    load_bundled_native_training_profile,
)


def _profile() -> NativePlayerTrainingProfile:
    return NativePlayerTrainingProfile(
        profile_id="native-training-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        player_pointer_rva=0x200,
        skill_vector_offset=0xC24,
        power_vector_offset=0x670,
        vector_entry_size=16,
        maximum_skill_count=16,
        maximum_power_count=32,
        maximum_plausible_rank=1_000,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        skill_tokens=(NativeTrainingToken(3200634440, "unarmed", "Unarmed Combat"),),
        power_tokens=(NativeTrainingToken(429410121, "shadow_mantle", "Shadow Mantle"),),
    )


class FakeProcessMemory:
    pid = 52
    executable_name = "sb.exe"
    executable_path = Path("C:/Wonderbane/sb.exe")
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4

    def __init__(self, responses: dict[int, list[bytes]]) -> None:
        self.responses = {address: list(values) for address, values in responses.items()}
        self.closed = False

    def read(self, address: int, size: int) -> bytes:
        try:
            value = self.responses[address].pop(0)
        except (KeyError, IndexError) as exc:
            raise AssertionError(f"unexpected read at 0x{address:X}") from exc
        if len(value) != size:
            raise AssertionError(f"expected a {size}-byte fixture, found {len(value)}")
        return value

    def close(self) -> None:
        self.closed = True


def _pointer(value: int) -> bytes:
    return struct.pack("<I", value)


def _metadata(start: int, count: int, capacity: int | None = None) -> bytes:
    capacity_count = count if capacity is None else capacity
    return struct.pack("<III", start, start + count * 16, start + capacity_count * 16)


def _entry(token: int, trained: int, effective: int, maximum: int) -> bytes:
    return struct.pack("<IIII", token, trained, effective, maximum)


class NativePlayerTrainingReaderTests(unittest.TestCase):
    def test_reads_catalogued_and_unknown_lossless_entries(self) -> None:
        profile = _profile()
        player = 0x1C93D008
        skill_start = 0x10273598
        power_start = 0x330E1A68
        slot = FakeProcessMemory.base_address + profile.player_pointer_rva
        skill_metadata_address = player + profile.skill_vector_offset
        power_metadata_address = player + profile.power_vector_offset
        skill_metadata = _metadata(skill_start, 1)
        power_metadata = _metadata(power_start, 2)
        reader = NativePlayerTrainingReader(
            profile,
            FakeProcessMemory(
                {
                    slot: [_pointer(player), _pointer(player)],
                    skill_metadata_address: [skill_metadata, skill_metadata],
                    power_metadata_address: [power_metadata, power_metadata],
                    skill_start: [_entry(3200634440, 68, 110, 110)],
                    power_start: [_entry(429410121, 24, 24, 24) + _entry(421087049, 5, 10, 10)],
                }
            ),
        )

        observation = reader.observe()

        self.assertEqual("unarmed", observation.skills[0].key)
        self.assertEqual(68, observation.skills[0].trained_rank)
        self.assertEqual(110, observation.skills[0].effective_rank)
        self.assertTrue(observation.skills[0].catalogued)
        self.assertEqual("shadow_mantle", observation.powers[0].key)
        self.assertEqual("power_0x19194749", observation.powers[1].key)
        self.assertFalse(observation.powers[1].catalogued)
        self.assertEqual("0x19194749", observation.powers[1].as_dict()["token_hex"])

    def test_rejects_vector_with_end_beyond_capacity(self) -> None:
        profile = _profile()
        player = 0x1C93D008
        slot = FakeProcessMemory.base_address + profile.player_pointer_rva
        invalid = struct.pack("<III", 0x200000, 0x200020, 0x200010)
        reader = NativePlayerTrainingReader(
            profile,
            FakeProcessMemory(
                {
                    slot: [_pointer(player), _pointer(player)],
                    player + profile.skill_vector_offset: [invalid],
                }
            ),
        )

        with self.assertRaisesRegex(NativePlayerTrainingReadError, "not ordered"):
            reader.observe()

    def test_large_vectors_use_backend_bounded_reads(self) -> None:
        profile = _profile()
        player = 0x1C93D008
        skill_start = 0x10273598
        slot = FakeProcessMemory.base_address + profile.player_pointer_rva
        skill_metadata = _metadata(skill_start, 5)
        empty_metadata = struct.pack("<III", 0, 0, 0)
        raw = b"".join(
            _entry(token, trained, effective, effective)
            for token, trained, effective in (
                (3200634440, 68, 110),
                (1, 0, 20),
                (2, 0, 20),
                (3, 0, 20),
                (4, 0, 20),
            )
        )
        reader = NativePlayerTrainingReader(
            profile,
            FakeProcessMemory(
                {
                    slot: [_pointer(player), _pointer(player)],
                    player + profile.skill_vector_offset: [skill_metadata, skill_metadata],
                    player + profile.power_vector_offset: [empty_metadata, empty_metadata],
                    skill_start: [raw[:64]],
                    skill_start + 64: [raw[64:]],
                }
            ),
        )

        observation = reader.observe()

        self.assertEqual(5, len(observation.skills))
        self.assertEqual(4, observation.skills[-1].token)

    def test_executable_hash_mismatch_fails_before_reads(self) -> None:
        process = FakeProcessMemory({})
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativePlayerTrainingCompatibilityError, "SHA-256"):
            NativePlayerTrainingReader(_profile(), process)


class NativePlayerTrainingProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_live_offsets_and_semantic_tokens(self) -> None:
        profile = load_bundled_native_training_profile()
        skills = {item.token: item.key for item in profile.skill_tokens}
        powers = {item.token: item.key for item in profile.power_tokens}

        self.assertEqual(0x16A2D98, profile.player_pointer_rva)
        self.assertEqual(0xC24, profile.skill_vector_offset)
        self.assertEqual(0x670, profile.power_vector_offset)
        self.assertEqual("unarmed", skills[3200634440])
        self.assertEqual("light_armor", skills[38031547])
        self.assertEqual("poison_blade", powers[429016905])
        self.assertEqual("shadow_mantle", powers[429410121])


class FakeNativeTrainingReader:
    process_id = 77

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def observe(self) -> NativePlayerTrainingObservation:
        return NativePlayerTrainingObservation(
            skills=(
                NativeTrainingEntry(
                    3200634440,
                    "unarmed",
                    "Unarmed Combat",
                    68,
                    110,
                    110,
                    True,
                ),
            ),
            powers=(
                NativeTrainingEntry(
                    429410121,
                    "shadow_mantle",
                    "Shadow Mantle",
                    24,
                    24,
                    24,
                    True,
                ),
            ),
        )


class FakeCurrentNativeTrainingReader(FakeNativeTrainingReader):
    def observe(self) -> NativePlayerTrainingObservation:
        skills = {
            "light_armor": 110,
            "dodge": 46,
            "shadowmastery": 100,
            "unarmed_mastery": 110,
            "unarmed": 110,
        }
        powers = {
            "poison_blade": 40,
            "cloak_of_shadows": 40,
            "shadow_touch": 40,
            "shadow_mantle": 24,
            "sneak": 20,
            "blindness": 12,
            "plague_of_blindness": 1,
            "steal_breath": 1,
            "silence": 1,
            "backstab": 1,
            "shadow_bolt": 2,
            "slayers_focus": 1,
        }
        return NativePlayerTrainingObservation(
            skills=tuple(
                NativeTrainingEntry(index, key, key, rank, rank, rank, True)
                for index, (key, rank) in enumerate(skills.items(), start=1)
            ),
            powers=tuple(
                NativeTrainingEntry(index, key, key, rank, rank, rank, True)
                for index, (key, rank) in enumerate(powers.items(), start=100)
            ),
        )


class FakeNativeProgressionReader:
    process_id = 77

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def observe(self) -> NativePlayerProgressionCoreObservation:
        return NativePlayerProgressionCoreObservation(59, 168, 113, 366, 366, 150)


class NativePlayerTrainingCliTests(unittest.TestCase):
    def test_command_emits_lossless_training_vectors(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_training_profile",
                return_value=_profile(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_player_training_reader",
                return_value=FakeNativeTrainingReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "observe-native-training", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(110, payload["skills"][0]["effective_rank"])
        self.assertEqual(68, payload["skills"][0]["trained_rank"])
        self.assertEqual("shadow_mantle", payload["powers"][0]["key"])

    def test_live_advice_composes_scalar_and_rank_observations(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_progression_core_profile",
                return_value=SimpleNamespace(profile_id="core-test"),
            ),
            patch(
                "shadowbane_lab.cli.load_bundled_native_training_profile",
                return_value=_profile(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_player_progression_core_reader",
                return_value=FakeNativeProgressionReader(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_player_training_reader",
                return_value=FakeCurrentNativeTrainingReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "advise-irekei-proc", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(49, payload["audit"]["power_rank_increments_needed"])
        self.assertEqual(64, payload["audit"]["power_training_reserve_after_targets"])


if __name__ == "__main__":
    unittest.main()
