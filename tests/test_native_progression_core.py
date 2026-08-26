from __future__ import annotations

import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation.native_progression_core import (
    NativePlayerProgressionCoreCompatibilityError,
    NativePlayerProgressionCoreObservation,
    NativePlayerProgressionCoreProfile,
    NativePlayerProgressionCoreReader,
    NativePlayerProgressionCoreReadError,
    load_bundled_native_progression_core_profile,
)


def _profile() -> NativePlayerProgressionCoreProfile:
    return NativePlayerProgressionCoreProfile(
        profile_id="native-progression-core-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        player_pointer_rva=0x200,
        training_points_offset=0xC20,
        ability_points_offset=0xCAC,
        level_offset=0xCC0,
        left_attack_rating_offset=0xCFC,
        right_attack_rating_offset=0xD00,
        defense_offset=0xD04,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        maximum_level=75,
        maximum_plausible_points=10_000,
        maximum_plausible_rating=100_000,
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
            raise AssertionError(f"expected a {size}-byte fixture")
        return value

    def close(self) -> None:
        self.closed = True


def _pointer(value: int) -> bytes:
    return struct.pack("<I", value)


def _progression_block(profile: NativePlayerProgressionCoreProfile, **values: int) -> bytes:
    first = min(profile.value_offsets)
    final = max(profile.value_offsets) + 4
    block = bytearray(final - first)
    fields = {
        "unspent_training_points": profile.training_points_offset,
        "unspent_ability_points": profile.ability_points_offset,
        "level": profile.level_offset,
        "left_attack_rating": profile.left_attack_rating_offset,
        "right_attack_rating": profile.right_attack_rating_offset,
        "defense": profile.defense_offset,
    }
    for name, offset in fields.items():
        struct.pack_into("<i", block, offset - first, values[name])
    return bytes(block)


def _bounded_block_responses(address: int, block: bytes) -> dict[int, list[bytes]]:
    return {address + offset: [block[offset : offset + 64]] for offset in range(0, len(block), 64)}


class NativePlayerProgressionCoreReaderTests(unittest.TestCase):
    def test_reads_live_calibrated_progression_values(self) -> None:
        profile = _profile()
        player = 0x1C93D008
        slot = FakeProcessMemory.base_address + profile.player_pointer_rva
        block_address = player + min(profile.value_offsets)
        block = _progression_block(
            profile,
            level=59,
            unspent_ability_points=168,
            unspent_training_points=113,
            left_attack_rating=366,
            right_attack_rating=366,
            defense=150,
        )
        reader = NativePlayerProgressionCoreReader(
            profile,
            FakeProcessMemory(
                {
                    slot: [_pointer(player), _pointer(player)],
                    **_bounded_block_responses(block_address, block),
                }
            ),
        )

        observation = reader.observe()

        self.assertEqual(59, observation.level)
        self.assertEqual(168, observation.unspent_ability_points)
        self.assertEqual(113, observation.unspent_training_points)
        self.assertEqual(366, observation.left_attack_rating)
        self.assertEqual(366, observation.right_attack_rating)
        self.assertEqual(150, observation.defense)

    def test_impossible_level_fails_closed(self) -> None:
        profile = _profile()
        player = 0x1C93D008
        slot = FakeProcessMemory.base_address + profile.player_pointer_rva
        block_address = player + min(profile.value_offsets)
        block = _progression_block(
            profile,
            level=76,
            unspent_ability_points=168,
            unspent_training_points=113,
            left_attack_rating=366,
            right_attack_rating=366,
            defense=150,
        )
        reader = NativePlayerProgressionCoreReader(
            profile,
            FakeProcessMemory(
                {
                    slot: [_pointer(player), _pointer(player)],
                    **_bounded_block_responses(block_address, block),
                }
            ),
        )

        with self.assertRaisesRegex(NativePlayerProgressionCoreReadError, "level"):
            reader.observe()

    def test_executable_hash_mismatch_fails_before_reads(self) -> None:
        process = FakeProcessMemory({})
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativePlayerProgressionCoreCompatibilityError, "SHA-256"):
            NativePlayerProgressionCoreReader(_profile(), process)


class NativePlayerProgressionCoreProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_live_calibrated_offsets(self) -> None:
        profile = load_bundled_native_progression_core_profile()

        self.assertEqual(0x16A2D98, profile.player_pointer_rva)
        self.assertEqual(0xC20, profile.training_points_offset)
        self.assertEqual(0xCAC, profile.ability_points_offset)
        self.assertEqual(0xCC0, profile.level_offset)
        self.assertEqual(0xCFC, profile.left_attack_rating_offset)
        self.assertEqual(0xD04, profile.defense_offset)


class FakeNativeProgressionCoreReader:
    process_id = 77

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def observe(self) -> NativePlayerProgressionCoreObservation:
        return NativePlayerProgressionCoreObservation(59, 168, 113, 366, 366, 150)


class NativePlayerProgressionCoreCliTests(unittest.TestCase):
    def test_command_emits_exact_native_progression(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_progression_core_profile",
                return_value=_profile(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_player_progression_core_reader",
                return_value=FakeNativeProgressionCoreReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "observe-native-progression", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(59, payload["level"])
        self.assertEqual(168, payload["unspent_ability_points"])
        self.assertEqual(113, payload["unspent_training_points"])
        self.assertEqual(366, payload["left_attack_rating"])
        self.assertEqual(150, payload["defense"])


if __name__ == "__main__":
    unittest.main()
