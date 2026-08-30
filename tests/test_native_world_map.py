from __future__ import annotations

import io
import json
import struct
import unittest
from collections.abc import Mapping
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativeMemoryRegion,
    NativeWorldMapObservation,
    NativeWorldMapProfile,
    NativeWorldMapProfileLoadError,
    NativeWorldMapReader,
    NativeWorldMapReadError,
    load_bundled_native_world_map_profile,
    load_native_world_map_profile_text,
)


def _profile(**changes: object) -> NativeWorldMapProfile:
    values: dict[str, object] = {
        "profile_id": "test-world-map",
        "executable_name": "sb.exe",
        "executable_sha256": "a" * 64,
        "pointer_size": 4,
        "object_vtable_rva": 0x1000,
        "control_vtable_rva": 0x1100,
        "world_definition_pointer_rva": 0x1200,
        "rectangle_offset": 8,
        "hidden_offset": 0xD0,
        "left_padding_offset": 0x334,
        "top_padding_offset": 0x338,
        "right_padding_offset": 0x33C,
        "bottom_padding_offset": 0x340,
        "zoom_offset": 0x37C,
        "map_texture_pointer_offset": 0x400,
        "horizontal_pan_offset": 0x410,
        "vertical_pan_offset": 0x414,
        "world_length_tiles_offset": 0x10,
        "world_width_tiles_offset": 0x14,
        "world_coordinate_scale": 256.0,
        "minimum_user_address": 0x10000,
        "maximum_user_address": 0x7FFEFFFF,
        "maximum_scan_address": 0x7FFEFFFF,
        "scan_memory_type": 0x20000,
        "scan_protection": 4,
        "maximum_candidates": 16,
        "minimum_map_pixels": 128,
        "maximum_map_pixels": 8192,
        "minimum_zoom": 0.125,
        "maximum_zoom": 16.0,
        "maximum_world_tiles": 4096,
        "schema_version": 1,
    }
    values.update(changes)
    return NativeWorldMapProfile(**values)  # type: ignore[arg-type]


class FakeScanningProcess:
    pid = 73
    executable_name = "sb.exe"
    executable_path = Path("sb.exe")
    executable_sha256 = "a" * 64
    base_address = 0x400000
    pointer_size = 4

    def __init__(
        self,
        profile: NativeWorldMapProfile,
        *,
        object_addresses: tuple[int, ...] = (0x300000,),
        hidden: int = 0,
        hidden_addresses: tuple[int, ...] = (),
        zoom: float = 1.0,
        horizontal_pan: int = 0,
        vertical_pan: int = 0,
    ) -> None:
        self.profile = profile
        self.closed = False
        self.memory: dict[int, bytes] = {}
        self.object_addresses = object_addresses
        self.world_definition = 0x350000
        self.memory[self.base_address + profile.world_definition_pointer_rva] = struct.pack(
            "<I", self.world_definition
        )
        world = bytearray(profile.world_width_tiles_offset + 4)
        struct.pack_into("<i", world, profile.world_length_tiles_offset, 512)
        struct.pack_into("<i", world, profile.world_width_tiles_offset, 384)
        self.memory[self.world_definition] = bytes(world)
        for address in object_addresses:
            payload = bytearray(profile.vertical_pan_offset + 4)
            struct.pack_into(
                "<II",
                payload,
                0,
                self.base_address + profile.object_vtable_rva,
                self.base_address + profile.control_vtable_rva,
            )
            struct.pack_into("<iiii", payload, profile.rectangle_offset, 324, 0, 1597, 955)
            payload[profile.hidden_offset] = 1 if address in hidden_addresses else hidden
            for offset, value in zip(
                (
                    profile.left_padding_offset,
                    profile.top_padding_offset,
                    profile.right_padding_offset,
                    profile.bottom_padding_offset,
                ),
                (3, 16, 3, 3),
                strict=True,
            ):
                struct.pack_into("<i", payload, offset, value)
            struct.pack_into("<f", payload, profile.zoom_offset, zoom)
            struct.pack_into("<I", payload, profile.map_texture_pointer_offset, 0x360000)
            struct.pack_into("<i", payload, profile.horizontal_pan_offset, horizontal_pan)
            struct.pack_into("<i", payload, profile.vertical_pan_offset, vertical_pan)
            self.memory[address] = bytes(payload)

    def read(self, address: int, size: int) -> bytes:
        return self.read_block(address, size)

    def read_block(self, address: int, size: int) -> bytes:
        for start, payload in self.memory.items():
            if start <= address and address + size <= start + len(payload):
                offset = address - start
                return payload[offset : offset + size]
        raise RuntimeError(f"unmapped read at {address:#x}")

    def query_region(self, address: int) -> NativeMemoryRegion:
        return NativeMemoryRegion(address & ~0xFFF, 0x1000, 4, 0x20000)

    def find_all(
        self,
        needles: tuple[bytes, ...],
        **_: object,
    ) -> Mapping[bytes, tuple[int, ...]]:
        expected = struct.pack("<I", self.base_address + self.profile.object_vtable_rva)
        return {needle: self.object_addresses if needle == expected else () for needle in needles}

    def find_pointer_values_near(self, *_: object, **__: object):
        return {}

    def close(self) -> None:
        self.closed = True


class NativeWorldMapReaderTests(unittest.TestCase):
    def test_full_world_click_uses_native_inverse_projection(self) -> None:
        profile = _profile()
        process = FakeScanningProcess(profile)
        reader = NativeWorldMapReader(profile, process)

        observation = reader.observe()
        expected_lt = 70175.0
        expected_lg = 47876.0
        local_x = round(
            observation.left_padding
            + observation.content_width * expected_lt / observation.world_length
        )
        local_y = round(
            observation.top_padding
            + observation.content_height * (1.0 - expected_lg / observation.world_width)
        )
        point = observation.resolve_screen_point(
            observation.left + local_x,
            observation.top + local_y,
        )

        self.assertTrue(observation.is_open)
        self.assertAlmostEqual(expected_lt, point.lt, delta=55.0)
        self.assertAlmostEqual(expected_lg, point.lg, delta=55.0)
        self.assertTrue(reader.attached)

    def test_zoom_and_pan_are_applied_before_world_projection(self) -> None:
        profile = _profile()
        process = FakeScanningProcess(
            profile,
            zoom=2.0,
            horizontal_pan=500,
            vertical_pan=200,
        )
        observation = NativeWorldMapReader(profile, process).observe()
        expected_lt = 70000.0
        expected_lg = 48000.0
        local_x = round(
            (
                observation.left_padding
                + observation.content_width * expected_lt / observation.world_length
            )
            * observation.zoom
            - observation.horizontal_pan
        )
        local_y = round(
            (
                observation.top_padding
                + observation.content_height * (1.0 - expected_lg / observation.world_width)
            )
            * observation.zoom
            - observation.vertical_pan
        )

        point = observation.resolve_screen_point(
            observation.left + local_x,
            observation.top + local_y,
        )

        self.assertAlmostEqual(expected_lt, point.lt, delta=55.0)
        self.assertAlmostEqual(expected_lg, point.lg, delta=55.0)

    def test_hidden_map_and_points_outside_projection_fail_closed(self) -> None:
        profile = _profile()
        hidden = NativeWorldMapReader(
            profile,
            FakeScanningProcess(profile, hidden=1),
        ).observe()
        with self.assertRaisesRegex(NativeWorldMapReadError, "not open"):
            hidden.resolve_screen_point(500, 500)

        visible = NativeWorldMapReader(profile, FakeScanningProcess(profile)).observe()
        with self.assertRaisesRegex(NativeWorldMapReadError, "outside the world map"):
            visible.resolve_screen_point(100, 100)
        with self.assertRaisesRegex(NativeWorldMapReadError, "outside the projected world"):
            visible.resolve_screen_point(visible.left, visible.top)

    def test_unique_active_native_object_wins_over_inactive_duplicate(self) -> None:
        profile = _profile()
        reader = NativeWorldMapReader(
            profile,
            FakeScanningProcess(
                profile,
                object_addresses=(0x300000, 0x310000),
                hidden_addresses=(0x310000,),
            ),
        )

        reader.attach()

        self.assertEqual(0x300000, reader._object_address)
        self.assertTrue(reader.observe().is_open)

    def test_multiple_active_native_objects_fail_closed(self) -> None:
        profile = _profile()
        reader = NativeWorldMapReader(
            profile,
            FakeScanningProcess(profile, object_addresses=(0x300000, 0x310000)),
        )
        with self.assertRaisesRegex(NativeWorldMapReadError, r"found 2.*\(2 active\)"):
            reader.attach()

    def test_bundled_profile_matches_verified_wonderbane_layout(self) -> None:
        profile = load_bundled_native_world_map_profile()
        self.assertEqual(0x1170BC8, profile.object_vtable_rva)
        self.assertEqual(0x1170B8C, profile.control_vtable_rva)
        self.assertEqual(0x16A7C3C, profile.world_definition_pointer_rva)
        self.assertEqual(0x37C, profile.zoom_offset)
        self.assertEqual(0x410, profile.horizontal_pan_offset)

    def test_profile_loader_rejects_unknown_fields(self) -> None:
        payload = {
            field: getattr(_profile(), field)
            for field in NativeWorldMapProfile.__dataclass_fields__
        }
        payload["unexpected"] = True
        with self.assertRaisesRegex(NativeWorldMapProfileLoadError, "unknown fields"):
            load_native_world_map_profile_text(json.dumps(payload))


class FakeNativeWorldMapReader:
    process_id = 73

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def observe(self) -> NativeWorldMapObservation:
        return NativeWorldMapObservation(
            is_open=True,
            left=324,
            top=0,
            right=1597,
            bottom=955,
            left_padding=3,
            top_padding=16,
            right_padding=3,
            bottom_padding=3,
            zoom=1.0,
            horizontal_pan=0,
            vertical_pan=0,
            world_length=131_072.0,
            world_width=98_304.0,
            snapshot_token="ab" * 12,
        )


class NativeWorldMapCliTests(unittest.TestCase):
    def test_command_emits_native_projection_state(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_world_map_profile",
                return_value=_profile(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_world_map_reader",
                return_value=FakeNativeWorldMapReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "observe-native-world-map", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["is_open"])
        self.assertEqual(324, payload["rectangle"]["left"])
        self.assertEqual(1.0, payload["zoom"])
        self.assertEqual(131_072.0, payload["world"]["length"])


if __name__ == "__main__":
    unittest.main()
