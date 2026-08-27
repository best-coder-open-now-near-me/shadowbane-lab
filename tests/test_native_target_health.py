import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativeTargetHealthCompatibilityError,
    NativeTargetHealthObservation,
    NativeTargetHealthProfile,
    NativeTargetHealthReader,
    NativeTargetHealthReadError,
    load_bundled_native_health_profile,
    load_native_health_profile_text,
    open_windows_native_target_health_reader,
)


def _profile() -> NativeTargetHealthProfile:
    return NativeTargetHealthProfile(
        profile_id="native-health-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        selected_pointer_rva=0x100,
        current_health_offset=0x5CC,
        maximum_health_offset=0x5D0,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        maximum_plausible_health=1_000_000,
    )


class FakeProcessMemory:
    pid = 41
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


def _health(current: float, maximum: float) -> bytes:
    return struct.pack("<ff", current, maximum)


class NativeTargetHealthReaderTests(unittest.TestCase):
    def test_opens_the_guarded_foreground_process_explicitly(self) -> None:
        process = FakeProcessMemory({})
        with patch(
            "shadowbane_lab.client_observation.native_health."
            "WindowsReadOnlyProcessMemory.open_for_process",
            return_value=process,
        ) as open_for_process:
            reader = open_windows_native_target_health_reader(
                _profile(),
                process_id=4320,
            )

        open_for_process.assert_called_once_with("sb.exe", 4320)
        self.assertEqual(41, reader.process_id)
        reader.close()
        self.assertTrue(process.closed)

    def test_absent_selection_returns_no_health(self) -> None:
        profile = _profile()
        slot = FakeProcessMemory.base_address + profile.selected_pointer_rva
        reader = NativeTargetHealthReader(profile, FakeProcessMemory({slot: [_pointer(0)]}))

        observation = reader.observe()

        self.assertEqual(NativeTargetHealthObservation(target_present=False), observation)
        self.assertIsNone(observation.health_fraction)

    def test_reads_stable_exact_current_and_maximum_health(self) -> None:
        profile = _profile()
        target = 0x12340000
        slot = FakeProcessMemory.base_address + profile.selected_pointer_rva
        process = FakeProcessMemory(
            {
                slot: [_pointer(target), _pointer(target)],
                target + profile.current_health_offset: [_health(8.55689, 10.0)],
            }
        )
        reader = NativeTargetHealthReader(profile, process)

        observation = reader.observe()

        self.assertTrue(observation.target_present)
        self.assertEqual(24, len(observation.target_token or ""))
        self.assertAlmostEqual(8.55689, observation.current_health, places=5)
        self.assertEqual(10.0, observation.maximum_health)
        self.assertAlmostEqual(0.855689, observation.health_fraction, places=5)

    def test_retries_when_selection_changes_during_read(self) -> None:
        profile = _profile()
        first = 0x12340000
        second = 0x12350000
        slot = FakeProcessMemory.base_address + profile.selected_pointer_rva
        reader = NativeTargetHealthReader(
            profile,
            FakeProcessMemory(
                {
                    slot: [
                        _pointer(first),
                        _pointer(second),
                        _pointer(second),
                        _pointer(second),
                    ],
                    first + profile.current_health_offset: [_health(4.0, 10.0)],
                    second + profile.current_health_offset: [_health(7.0, 10.0)],
                }
            ),
        )

        observation = reader.observe()

        self.assertEqual(7.0, observation.current_health)

    def test_out_of_range_pointer_fails_closed(self) -> None:
        profile = _profile()
        slot = FakeProcessMemory.base_address + profile.selected_pointer_rva
        reader = NativeTargetHealthReader(
            profile,
            FakeProcessMemory({slot: [_pointer(0x1000)]}),
        )

        with self.assertRaisesRegex(NativeTargetHealthReadError, "outside"):
            reader.observe()

    def test_impossible_health_fails_closed(self) -> None:
        profile = _profile()
        target = 0x12340000
        slot = FakeProcessMemory.base_address + profile.selected_pointer_rva
        reader = NativeTargetHealthReader(
            profile,
            FakeProcessMemory(
                {
                    slot: [_pointer(target), _pointer(target)],
                    target + profile.current_health_offset: [_health(11.0, 10.0)],
                }
            ),
        )

        with self.assertRaisesRegex(NativeTargetHealthReadError, "exceeds"):
            reader.observe()

    def test_executable_hash_mismatch_fails_before_reads(self) -> None:
        process = FakeProcessMemory({})
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativeTargetHealthCompatibilityError, "SHA-256"):
            NativeTargetHealthReader(_profile(), process)

    def test_context_manager_closes_process(self) -> None:
        profile = _profile()
        slot = FakeProcessMemory.base_address + profile.selected_pointer_rva
        process = FakeProcessMemory({slot: [_pointer(0)]})

        with NativeTargetHealthReader(profile, process) as reader:
            reader.observe()

        self.assertTrue(process.closed)


class NativeTargetHealthProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_live_validated_build_and_offsets(self) -> None:
        profile = load_bundled_native_health_profile()

        self.assertEqual("sb.exe", profile.executable_name)
        self.assertEqual(
            "0889b39a6f065f2ddf696bad01455e0b691892077105fe27e35de94bfdf59ebc",
            profile.executable_sha256,
        )
        self.assertEqual(0x16A2DA4, profile.selected_pointer_rva)
        self.assertEqual(0x5CC, profile.current_health_offset)
        self.assertEqual(0x5D0, profile.maximum_health_offset)

    def test_unknown_profile_field_fails_closed(self) -> None:
        payload = {
            "schema_version": 1,
            "profile_id": "test",
            "executable_name": "sb.exe",
            "executable_sha256": "ab" * 32,
            "pointer_size": 4,
            "selected_pointer_rva": 1,
            "current_health_offset": 4,
            "maximum_health_offset": 8,
            "minimum_user_address": 65536,
            "maximum_user_address": 2147418111,
            "maximum_plausible_health": 100,
            "surprise": True,
        }

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_native_health_profile_text(json.dumps(payload))


class FakeNativeReader:
    process_id = 77

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def observe(self) -> NativeTargetHealthObservation:
        return NativeTargetHealthObservation(
            target_present=True,
            current_health=8.5,
            maximum_health=10.0,
            target_token="target-test",
        )


class NativeTargetHealthCliTests(unittest.TestCase):
    def test_command_emits_exact_native_health(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_health_profile",
                return_value=_profile(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_target_health_reader",
                return_value=FakeNativeReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "observe-native-target", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["target_present"])
        self.assertEqual("target-test", payload["target_token"])
        self.assertEqual(8.5, payload["current_health"])
        self.assertEqual(10.0, payload["maximum_health"])
        self.assertEqual(0.85, payload["health_fraction"])


if __name__ == "__main__":
    unittest.main()
