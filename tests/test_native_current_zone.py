import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativeCurrentZoneCompatibilityError,
    NativeCurrentZoneObservation,
    NativeCurrentZoneProfile,
    NativeCurrentZoneReader,
    NativeCurrentZoneReadError,
    load_bundled_native_zone_profile,
    load_native_zone_profile_text,
)


def _profile() -> NativeCurrentZoneProfile:
    return NativeCurrentZoneProfile(
        profile_id="native-zone-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        player_pointer_rva=0x200,
        current_zone_offset=0xD40,
        parent_zone_offset=0xEC,
        zone_name_offset=0x1BC,
        string_begin_offset=4,
        string_end_offset=8,
        string_capacity_offset=12,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        maximum_zone_name_chars=128,
        maximum_parent_depth=32,
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
            responses = self.responses[address]
            value = responses[0] if len(responses) == 1 else responses.pop(0)
        except (KeyError, IndexError) as exc:
            raise OSError(f"unexpected read at 0x{address:X}") from exc
        if len(value) != size:
            raise AssertionError(f"expected a {size}-byte fixture")
        return value

    def close(self) -> None:
        self.closed = True


def _pointer(value: int) -> bytes:
    return struct.pack("<I", value)


def _string_fixture(buffer: int, value: str) -> tuple[bytes, bytes]:
    encoded = value.encode("utf-16-le")
    header = struct.pack(
        "<IIII",
        0x10021A34,
        buffer,
        buffer + len(encoded),
        buffer + len(encoded) + 16,
    )
    return header, encoded + b"\x00\x00"


def _fixture(
    current_name: str,
    *,
    parent_name: str | None = None,
) -> tuple[FakeProcessMemory, int]:
    profile = _profile()
    player = 0x3518B280
    current_zone = 0x2A100000
    parent_zone = 0x2A200000
    current_buffer = 0x2B100000
    parent_buffer = 0x2B200000
    slot = FakeProcessMemory.base_address + profile.player_pointer_rva
    current_header, current_raw = _string_fixture(current_buffer, current_name)
    responses = {
        slot: [_pointer(player)],
        player + profile.current_zone_offset: [_pointer(current_zone)],
        current_zone + profile.zone_name_offset: [current_header],
        current_buffer: [current_raw],
    }
    if parent_name is not None:
        parent_header, parent_raw = _string_fixture(parent_buffer, parent_name)
        responses[current_zone + profile.parent_zone_offset] = [_pointer(parent_zone)]
        responses[parent_zone + profile.zone_name_offset] = [parent_header]
        responses[parent_buffer] = [parent_raw]
    return FakeProcessMemory(responses), current_zone


class NativeCurrentZoneReaderTests(unittest.TestCase):
    def test_reads_client_resolved_current_zone_name(self) -> None:
        process, _ = _fixture("Keep of the Gorgoi")

        observation = NativeCurrentZoneReader(_profile(), process).observe()

        self.assertEqual("Keep of the Gorgoi", observation.name)
        self.assertEqual(0, observation.name_source_depth)
        self.assertEqual(24, len(observation.zone_token))

    def test_matches_client_parent_name_fallback(self) -> None:
        process, _ = _fixture("", parent_name="The Dalgoth Marches")

        observation = NativeCurrentZoneReader(_profile(), process).observe()

        self.assertEqual("The Dalgoth Marches", observation.name)
        self.assertEqual(1, observation.name_source_depth)

    def test_rejects_parent_cycle(self) -> None:
        profile = _profile()
        process, current_zone = _fixture("")
        process.responses[current_zone + profile.parent_zone_offset] = [
            _pointer(current_zone)
        ]

        with self.assertRaisesRegex(NativeCurrentZoneReadError, "cycle"):
            NativeCurrentZoneReader(profile, process).observe()

    def test_rejects_invalid_string_bounds(self) -> None:
        profile = _profile()
        process, current_zone = _fixture("Keep of the Gorgoi")
        process.responses[current_zone + profile.zone_name_offset] = [
            struct.pack("<IIII", 0x10021A34, 0x2B100100, 0x2B100000, 0x2B100200)
        ]

        with self.assertRaisesRegex(NativeCurrentZoneReadError, "pointers are invalid"):
            NativeCurrentZoneReader(profile, process).observe()

    def test_executable_hash_mismatch_fails_before_reads(self) -> None:
        process, _ = _fixture("Keep of the Gorgoi")
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativeCurrentZoneCompatibilityError, "SHA-256"):
            NativeCurrentZoneReader(_profile(), process)


class NativeCurrentZoneProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_static_client_offsets(self) -> None:
        profile = load_bundled_native_zone_profile()

        self.assertEqual(0x16A2D98, profile.player_pointer_rva)
        self.assertEqual(0xD40, profile.current_zone_offset)
        self.assertEqual(0xEC, profile.parent_zone_offset)
        self.assertEqual(0x1BC, profile.zone_name_offset)
        self.assertEqual((4, 8, 12), (
            profile.string_begin_offset,
            profile.string_end_offset,
            profile.string_capacity_offset,
        ))

    def test_profile_loader_rejects_unknown_fields(self) -> None:
        bundled = load_bundled_native_zone_profile()
        raw = {
            field: getattr(bundled, field)
            for field in bundled.__dataclass_fields__
        }
        raw["unknown"] = True

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_native_zone_profile_text(json.dumps(raw))


class FakeNativeCurrentZoneReader:
    process_id = 77

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def observe(self) -> NativeCurrentZoneObservation:
        return NativeCurrentZoneObservation(
            name="Keep of the Gorgoi",
            zone_token="zone-token",
            name_source_depth=0,
        )


class NativeCurrentZoneCliTests(unittest.TestCase):
    def test_command_emits_native_current_zone(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_zone_profile",
                return_value=_profile(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_current_zone_reader",
                return_value=FakeNativeCurrentZoneReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "observe-native-zone", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual("Keep of the Gorgoi", payload["name"])
        self.assertEqual("zone-token", payload["zone_token"])
        self.assertEqual(0, payload["name_source_depth"])


if __name__ == "__main__":
    unittest.main()
