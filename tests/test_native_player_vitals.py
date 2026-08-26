import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativePlayerVitalsCompatibilityError,
    NativePlayerVitalsObservation,
    NativePlayerVitalsProfile,
    NativePlayerVitalsReader,
    NativePlayerVitalsReadError,
    load_bundled_native_vitals_profile,
)


def _profile() -> NativePlayerVitalsProfile:
    return NativePlayerVitalsProfile(
        profile_id="native-vitals-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        player_pointer_rva=0x200,
        current_health_offset=0x5CC,
        maximum_health_offset=0x5D0,
        current_mana_offset=0xCD0,
        maximum_mana_offset=0xCD4,
        current_stamina_offset=0xCDC,
        maximum_stamina_offset=0xCD8,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        maximum_plausible_vital=1_000_000,
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


class NativePlayerVitalsReaderTests(unittest.TestCase):
    def test_reads_stable_exact_player_vitals(self) -> None:
        profile = _profile()
        player = 0x3518B280
        slot = FakeProcessMemory.base_address + profile.player_pointer_rva
        reader = NativePlayerVitalsReader(
            profile,
            FakeProcessMemory(
                {
                    slot: [_pointer(player), _pointer(player)],
                    player + profile.current_health_offset: [
                        struct.pack("<ff", 1075.375, 1075.375)
                    ],
                    player + profile.current_mana_offset: [
                        struct.pack("<ffff", 53.75, 63.75, 324.0, 123.0)
                    ],
                }
            ),
        )

        observation = reader.observe()

        self.assertEqual(1075.375, observation.current_health)
        self.assertEqual(53.75, observation.current_mana)
        self.assertEqual(63.75, observation.maximum_mana)
        self.assertEqual(123.0, observation.current_stamina)
        self.assertEqual(324.0, observation.maximum_stamina)
        self.assertEqual(1.0, observation.health_fraction)
        self.assertAlmostEqual(53.75 / 63.75, observation.mana_fraction)
        self.assertAlmostEqual(123.0 / 324.0, observation.stamina_fraction)

    def test_zero_player_pointer_fails_closed(self) -> None:
        profile = _profile()
        slot = FakeProcessMemory.base_address + profile.player_pointer_rva
        reader = NativePlayerVitalsReader(
            profile,
            FakeProcessMemory({slot: [_pointer(0)]}),
        )

        with self.assertRaisesRegex(NativePlayerVitalsReadError, "outside"):
            reader.observe()

    def test_impossible_resource_fails_closed(self) -> None:
        profile = _profile()
        player = 0x3518B280
        slot = FakeProcessMemory.base_address + profile.player_pointer_rva
        reader = NativePlayerVitalsReader(
            profile,
            FakeProcessMemory(
                {
                    slot: [_pointer(player)] * 6,
                    player + profile.current_health_offset: [struct.pack("<ff", 10, 10)] * 3,
                    player + profile.current_mana_offset: [
                        struct.pack("<ffff", 11, 10, 20, 20)
                    ]
                    * 3,
                }
            ),
        )

        with self.assertRaisesRegex(NativePlayerVitalsReadError, "current mana exceeds"):
            reader.observe()

    def test_retries_torn_resource_sample_before_returning_stable_vitals(self) -> None:
        profile = _profile()
        player = 0x3518B280
        slot = FakeProcessMemory.base_address + profile.player_pointer_rva
        reader = NativePlayerVitalsReader(
            profile,
            FakeProcessMemory(
                {
                    slot: [_pointer(player)] * 4,
                    player + profile.current_health_offset: [
                        struct.pack("<ff", 10, 10),
                        struct.pack("<ff", 10, 10),
                    ],
                    player + profile.current_mana_offset: [
                        struct.pack("<ffff", 10, 10, 20, 21),
                        struct.pack("<ffff", 10, 10, 20, 19),
                    ],
                }
            ),
            stability_attempts=2,
        )

        observation = reader.observe()

        self.assertEqual(19, observation.current_stamina)
        self.assertEqual(20, observation.maximum_stamina)

    def test_executable_hash_mismatch_fails_before_reads(self) -> None:
        process = FakeProcessMemory({})
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativePlayerVitalsCompatibilityError, "SHA-256"):
            NativePlayerVitalsReader(_profile(), process)


class NativePlayerVitalsProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_live_validated_offsets(self) -> None:
        profile = load_bundled_native_vitals_profile()

        self.assertEqual(0x16A2D98, profile.player_pointer_rva)
        self.assertEqual(0x5CC, profile.current_health_offset)
        self.assertEqual(0xCD0, profile.current_mana_offset)
        self.assertEqual(0xCDC, profile.current_stamina_offset)
        self.assertEqual(0xCD8, profile.maximum_stamina_offset)


class FakeNativeVitalsReader:
    process_id = 77

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def observe(self) -> NativePlayerVitalsObservation:
        return NativePlayerVitalsObservation(80, 100, 40, 50, 30, 60)


class NativePlayerVitalsCliTests(unittest.TestCase):
    def test_command_emits_exact_native_vitals(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_vitals_profile",
                return_value=_profile(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_player_vitals_reader",
                return_value=FakeNativeVitalsReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "observe-native-player", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(80, payload["current_health"])
        self.assertEqual(0.8, payload["health_fraction"])
        self.assertEqual(40, payload["current_mana"])
        self.assertEqual(0.8, payload["mana_fraction"])
        self.assertEqual(30, payload["current_stamina"])
        self.assertEqual(0.5, payload["stamina_fraction"])


if __name__ == "__main__":
    unittest.main()
