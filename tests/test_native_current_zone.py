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
    NativeZoneGeometry,
    NativeZoneIdentity,
    load_bundled_native_zone_profile,
    load_native_zone_profile_text,
    open_windows_native_current_zone_reader,
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
        template_group_offset=0x14,
        template_id_offset=0x10,
        object_type_offset=0x78,
        object_uuid_offset=0x7C,
        geometry_bounds_offset=0x8C,
        geometry_rotation_offset=0xA4,
        geometry_absolute_center_offset=0xB4,
        geometry_local_center_offset=0xBC,
        geometry_radius_offset=0xF0,
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


def _geometry() -> NativeZoneGeometry:
    return NativeZoneGeometry(
        minimum_local_x=-384.0,
        minimum_local_z=-384.0,
        maximum_local_x=384.0,
        maximum_local_z=384.0,
        rotation_w=1.0,
        rotation_x=0.0,
        rotation_y=0.0,
        rotation_z=0.0,
        absolute_center_x=88_832.0,
        absolute_center_z=-45_056.0,
        local_center_x=0.0,
        local_center_z=0.0,
        radius_x=384.0,
        radius_z=384.0,
    )


def _geometry_fixture() -> tuple[bytes, bytes]:
    raw = bytearray(108)
    struct.pack_into("<ffffff", raw, 0, -384.0, 0.0, -384.0, 384.0, 0.0, 384.0)
    struct.pack_into("<ffff", raw, 24, 1.0, 0.0, 0.0, 0.0)
    struct.pack_into("<ff", raw, 40, 88_832.0, -45_056.0)
    struct.pack_into("<ff", raw, 48, 0.0, 0.0)
    struct.pack_into("<ff", raw, 100, 384.0, 384.0)
    return bytes(raw[:64]), bytes(raw[64:])


def _fixture(
    current_name: str,
    *,
    parent_name: str | None = None,
    current_template: tuple[int, int] = (0, 524),
    parent_template: tuple[int, int] = (0, 3010),
) -> tuple[FakeProcessMemory, int]:
    profile = _profile()
    player = 0x3518B280
    current_zone = 0x2A100000
    parent_zone = 0x2A200000
    current_buffer = 0x2B100000
    parent_buffer = 0x2B200000
    slot = FakeProcessMemory.base_address + profile.player_pointer_rva
    current_header, current_raw = _string_fixture(current_buffer, current_name)
    geometry_first, geometry_second = _geometry_fixture()
    responses = {
        slot: [_pointer(player)],
        player + profile.current_zone_offset: [_pointer(current_zone)],
        current_zone + profile.zone_name_offset: [current_header],
        current_zone + min(profile.template_group_offset, profile.template_id_offset): [
            struct.pack("<II", current_template[1], current_template[0])
        ],
        current_zone + profile.object_type_offset: [struct.pack("<II", 9, 80052)],
        current_zone + profile.geometry_bounds_offset: [geometry_first],
        current_zone + profile.geometry_bounds_offset + len(geometry_first): [geometry_second],
        current_zone + profile.parent_zone_offset: [_pointer(0)],
        current_buffer: [current_raw],
    }
    if parent_name is not None:
        parent_header, parent_raw = _string_fixture(parent_buffer, parent_name)
        responses[current_zone + profile.parent_zone_offset] = [_pointer(parent_zone)]
        responses[parent_zone + profile.zone_name_offset] = [parent_header]
        responses[parent_zone + min(profile.template_group_offset, profile.template_id_offset)] = [
            struct.pack("<II", parent_template[1], parent_template[0])
        ]
        responses[parent_zone + profile.object_type_offset] = [struct.pack("<II", 9, 70041)]
        responses[parent_zone + profile.geometry_bounds_offset] = [geometry_first]
        responses[parent_zone + profile.geometry_bounds_offset + len(geometry_first)] = [
            geometry_second
        ]
        responses[parent_zone + profile.parent_zone_offset] = [_pointer(0)]
        responses[parent_buffer] = [parent_raw]
    return FakeProcessMemory(responses), current_zone


class NativeCurrentZoneReaderTests(unittest.TestCase):
    def test_reads_client_resolved_current_zone_name(self) -> None:
        process, _ = _fixture("Keep of the Gorgoi")

        observation = NativeCurrentZoneReader(_profile(), process).observe()

        self.assertEqual("Keep of the Gorgoi", observation.name)
        self.assertEqual(0, observation.name_source_depth)
        self.assertEqual(24, len(observation.zone_token))
        self.assertEqual(
            (0, 524),
            (
                observation.current.template_group_id,
                observation.current.template_id,
            ),
        )
        self.assertEqual(
            (9, 80052),
            (
                observation.current.object_type,
                observation.current.object_uuid,
            ),
        )
        self.assertEqual(
            (88_832.0, 45_056.0),
            (
                observation.current.geometry.center_lt,
                observation.current.geometry.center_lg,
            ),
        )

    def test_matches_client_parent_name_fallback(self) -> None:
        process, _ = _fixture("", parent_name="The Dalgoth Marches")

        observation = NativeCurrentZoneReader(_profile(), process).observe()

        self.assertEqual("The Dalgoth Marches", observation.name)
        self.assertEqual(1, observation.name_source_depth)
        self.assertEqual((524, 3010), tuple(zone.template_id for zone in observation.chain))

    def test_preserves_runtime_zone_chain_with_zero_template_ids(self) -> None:
        process, _ = _fixture(
            "Oblivion Isle",
            parent_name="Seafloor",
            current_template=(310, 0),
            parent_template=(1, 0),
        )

        observation = NativeCurrentZoneReader(_profile(), process).observe()

        self.assertEqual("Oblivion Isle", observation.name)
        self.assertEqual(
            ((310, 0), (1, 0)),
            tuple((zone.template_group_id, zone.template_id) for zone in observation.chain),
        )
        self.assertFalse(observation.current.cache_resolvable)

    def test_rejects_parent_cycle(self) -> None:
        profile = _profile()
        process, current_zone = _fixture("")
        process.responses[current_zone + profile.parent_zone_offset] = [_pointer(current_zone)]

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
        self.assertEqual(
            (0x14, 0x10),
            (
                profile.template_group_offset,
                profile.template_id_offset,
            ),
        )
        self.assertEqual(
            (0x78, 0x7C),
            (
                profile.object_type_offset,
                profile.object_uuid_offset,
            ),
        )
        self.assertEqual(
            (0x8C, 0xA4, 0xB4, 0xBC, 0xF0),
            (
                profile.geometry_bounds_offset,
                profile.geometry_rotation_offset,
                profile.geometry_absolute_center_offset,
                profile.geometry_local_center_offset,
                profile.geometry_radius_offset,
            ),
        )
        self.assertEqual(
            (4, 8, 12),
            (
                profile.string_begin_offset,
                profile.string_end_offset,
                profile.string_capacity_offset,
            ),
        )

    def test_profile_loader_rejects_unknown_fields(self) -> None:
        bundled = load_bundled_native_zone_profile()
        raw = {field: getattr(bundled, field) for field in bundled.__dataclass_fields__}
        raw["unknown"] = True

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_native_zone_profile_text(json.dumps(raw))

    def test_windows_opener_can_bind_to_the_guarded_process(self) -> None:
        process = FakeProcessMemory({})
        with patch(
            "shadowbane_lab.client_observation.native_zone."
            "WindowsReadOnlyProcessMemory.open_for_process",
            return_value=process,
        ) as open_for_process:
            reader = open_windows_native_current_zone_reader(
                _profile(),
                process_id=4320,
            )

        self.assertEqual(52, reader.process_id)
        open_for_process.assert_called_once_with("sb.exe", 4320)
        reader.close()
        self.assertTrue(process.closed)


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
            chain=(
                NativeZoneIdentity(
                    depth=0,
                    name="Keep of the Gorgoi",
                    template_group_id=0,
                    template_id=524,
                    object_type=9,
                    object_uuid=80052,
                    geometry=_geometry(),
                ),
            ),
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
        self.assertEqual(524, payload["template_id"])
        self.assertTrue(payload["cache_resolvable"])
        self.assertEqual(80052, payload["object_uuid"])
        self.assertTrue(payload["chain"][0]["cache_resolvable"])
        self.assertEqual(1, len(payload["chain"]))


if __name__ == "__main__":
    unittest.main()
