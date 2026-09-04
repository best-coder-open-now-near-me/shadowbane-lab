import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativeGroundedPlayerPositionObservation,
    NativePlayerPositionCompatibilityError,
    NativePlayerPositionObservation,
    NativePlayerPositionProfile,
    NativePlayerPositionReader,
    NativePlayerPositionReadError,
    load_bundled_native_position_profile,
    load_native_position_profile_text,
    open_windows_native_player_position_reader,
)


def _profile() -> NativePlayerPositionProfile:
    return NativePlayerPositionProfile(
        profile_id="native-player-position-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        player_pointer_rva=0x100,
        vtable_minimum_rva=0x200000,
        vtable_maximum_rva=0x300000,
        position_getter_slot_offset=0x58,
        position_getter_rva=0xA3D0,
        position_component_offset=0x4B0,
        component_value_offset=0,
        position_value_offset=0x20,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        minimum_world_coordinate=0,
        maximum_world_coordinate=200_000,
        minimum_altitude=-2_000,
        maximum_altitude=20_000,
        maximum_sample_drift=100,
        location_vtable_rva=0x225000,
        location_parent_offset=8,
        ground_height_offset=0x108,
        explicit_height_offset=0x10C,
        grounding_flag_offset=0x146,
        player_collision_wrapper_offset=0x4AC,
        collision_wrapper_value_offset=0,
        collision_vtable_rva=0x226000,
        collision_minimum_offset=0x90,
        maximum_ground_origin_error=0.01,
    )


class FakeProcessMemory:
    pid = 77
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


def _position(lt: float, lg: float, altitude: float) -> bytes:
    return struct.pack("<fff", lt, altitude, -lg)


def _fixture(
    *,
    first_position: tuple[float, float, float] = (106662.0, 52432.0, 148.0),
    second_position: tuple[float, float, float] = (106662.5, 52432.25, 148.0),
    getter: int | None = None,
) -> tuple[FakeProcessMemory, dict[str, int]]:
    profile = _profile()
    addresses = {
        "slot": FakeProcessMemory.base_address + profile.player_pointer_rva,
        "player": 0x21000000,
        "vtable": FakeProcessMemory.base_address + 0x220000,
        "getter": FakeProcessMemory.base_address + profile.position_getter_rva,
        "component": 0x23000000,
        "value": 0x24000000,
        "location_vtable": FakeProcessMemory.base_address + profile.location_vtable_rva,
        "collision_wrapper": 0x25000000,
        "collision": 0x26000000,
        "collision_vtable": FakeProcessMemory.base_address + profile.collision_vtable_rva,
    }
    resolved_getter = addresses["getter"] if getter is None else getter
    process = FakeProcessMemory(
        {
            addresses["slot"]: [_pointer(addresses["player"])],
            addresses["player"]: [_pointer(addresses["vtable"])],
            addresses["vtable"] + profile.position_getter_slot_offset: [_pointer(resolved_getter)],
            addresses["player"] + profile.position_component_offset: [
                _pointer(addresses["component"])
            ],
            addresses["component"]: [_pointer(addresses["value"])],
            addresses["value"] + profile.position_value_offset: [
                _position(*first_position),
                _position(*second_position),
            ],
            addresses["value"]: [_pointer(addresses["location_vtable"])],
            addresses["value"] + profile.location_parent_offset: [_pointer(0)],
            addresses["value"] + profile.ground_height_offset: [
                struct.pack("<ff", second_position[2] - 2.5, 0.0)
            ],
            addresses["value"] + profile.grounding_flag_offset: [b"\x01"],
            addresses["player"] + profile.player_collision_wrapper_offset: [
                _pointer(addresses["collision_wrapper"])
            ],
            addresses["collision_wrapper"]: [_pointer(addresses["collision"])],
            addresses["collision"]: [_pointer(addresses["collision_vtable"])],
            addresses["collision"] + profile.collision_minimum_offset: [
                struct.pack("<fff", -1.0, -2.5, -1.0)
            ],
        }
    )
    return process, addresses


class NativePlayerPositionReaderTests(unittest.TestCase):
    def test_opens_the_guarded_foreground_process_explicitly(self) -> None:
        process = FakeProcessMemory({})
        with patch(
            "shadowbane_lab.client_observation.native_position."
            "WindowsReadOnlyProcessMemory.open_for_process",
            return_value=process,
        ) as open_for_process:
            reader = open_windows_native_player_position_reader(
                _profile(),
                process_id=4320,
            )

        open_for_process.assert_called_once_with("sb.exe", 4320)
        self.assertEqual(77, reader.process_id)
        reader.close()
        self.assertTrue(process.closed)

    def test_null_player_pointer_fails_closed(self) -> None:
        profile = _profile()
        slot = FakeProcessMemory.base_address + profile.player_pointer_rva
        reader = NativePlayerPositionReader(
            profile,
            FakeProcessMemory({slot: [_pointer(0)]}),
        )

        with self.assertRaisesRegex(NativePlayerPositionReadError, "pointer is null"):
            reader.observe()

    def test_reads_position_storage_used_by_virtual_getter(self) -> None:
        process, _ = _fixture()

        observation = NativePlayerPositionReader(_profile(), process).observe()

        self.assertEqual(106662.5, observation.lt)
        self.assertEqual(52432.25, observation.lg)
        self.assertEqual(148.0, observation.altitude)
        self.assertEqual(145.5, observation.ground_altitude)
        self.assertEqual(1, observation.transform_count)

    def test_grounded_observation_preserves_legacy_serialized_position(self) -> None:
        observation = NativeGroundedPlayerPositionObservation(10.0, 20.0, 7.25, 5.0)

        self.assertEqual(5.0, observation.ground_altitude)
        self.assertEqual(
            {"lt": 10.0, "lg": 20.0, "altitude": 7.25, "transform_count": 1},
            asdict(observation),
        )

    def test_invalid_ground_height_falls_back_without_interrupting_position(self) -> None:
        process, addresses = _fixture()
        process.responses[addresses["value"] + _profile().ground_height_offset] = [
            struct.pack("<ff", 100.0, 0.0)
        ]

        observation = NativePlayerPositionReader(
            _profile(), process, stability_attempts=1
        ).observe()

        self.assertIs(type(observation), NativePlayerPositionObservation)
        self.assertEqual(
            (106662.5, 52432.25, 148.0),
            (observation.lt, observation.lg, observation.altitude),
        )

    def test_rejects_unsupported_position_getter(self) -> None:
        process, _ = _fixture(getter=FakeProcessMemory.base_address + 0xBEEF0)

        with self.assertRaisesRegex(NativePlayerPositionReadError, "unsupported"):
            NativePlayerPositionReader(
                _profile(),
                process,
                stability_attempts=1,
            ).observe()

    def test_rejects_incoherent_position_jump(self) -> None:
        process, _ = _fixture(
            first_position=(1000.0, 2000.0, 50.0),
            second_position=(2000.0, 3000.0, 50.0),
        )

        with self.assertRaisesRegex(NativePlayerPositionReadError, "coherent-sample"):
            NativePlayerPositionReader(
                _profile(),
                process,
                stability_attempts=1,
            ).observe()

    def test_executable_hash_mismatch_fails_before_reads(self) -> None:
        process, _ = _fixture()
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativePlayerPositionCompatibilityError, "SHA-256"):
            NativePlayerPositionReader(_profile(), process)


class NativePlayerPositionProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_static_getter_path(self) -> None:
        profile = load_bundled_native_position_profile()

        self.assertEqual(0x16A2D98, profile.player_pointer_rva)
        self.assertEqual(
            (0x1141000, 0x12C1000),
            (profile.vtable_minimum_rva, profile.vtable_maximum_rva),
        )
        self.assertEqual(0x58, profile.position_getter_slot_offset)
        self.assertEqual(0xA3D0, profile.position_getter_rva)
        self.assertEqual(
            (0x4B0, 0, 0x20),
            (
                profile.position_component_offset,
                profile.component_value_offset,
                profile.position_value_offset,
            ),
        )

    def test_profile_loader_rejects_unknown_fields(self) -> None:
        bundled = load_bundled_native_position_profile()
        raw = {field: getattr(bundled, field) for field in bundled.__dataclass_fields__}
        raw["unknown"] = True

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_native_position_profile_text(json.dumps(raw))


class FakeNativePositionReader:
    process_id = 77

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def observe(self) -> NativePlayerPositionObservation:
        return NativePlayerPositionObservation(106765.5, 52335.7, 146.7)


class NativePlayerPositionCliTests(unittest.TestCase):
    def test_command_emits_exact_native_position(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_position_profile",
                return_value=_profile(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_player_position_reader",
                return_value=FakeNativePositionReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "observe-native-position", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(106765.5, payload["lt"])
        self.assertEqual(52335.7, payload["lg"])
        self.assertEqual(146.7, payload["altitude"])
        self.assertEqual(1, payload["transform_count"])


if __name__ == "__main__":
    unittest.main()
