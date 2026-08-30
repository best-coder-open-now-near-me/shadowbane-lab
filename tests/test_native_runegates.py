import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativeRunegateObservation,
    NativeRunegateRegistryCompatibilityError,
    NativeRunegateRegistryObservation,
    NativeRunegateRegistryProfile,
    NativeRunegateRegistryReader,
    load_bundled_native_runegate_registry_profile,
    load_native_runegate_registry_profile_text,
)


def _profile() -> NativeRunegateRegistryProfile:
    return NativeRunegateRegistryProfile(
        profile_id="native-runegates-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        registry_pointer_rva=0x300,
        registry_tree_offset=0xA4,
        tree_head_pointer_offset=0,
        head_first_node_offset=8,
        node_parent_offset=4,
        node_left_offset=8,
        node_right_offset=12,
        object_type_offset=0x10,
        object_uuid_offset=0x14,
        zone_name_offset=0x18,
        latitude_offset=0x30,
        altitude_offset=0x34,
        longitude_offset=0x38,
        longitude_multiplier=-1.0,
        string_begin_offset=4,
        string_end_offset=8,
        string_capacity_offset=12,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        maximum_zone_name_chars=128,
        maximum_runegates=256,
        maximum_absolute_coordinate=250_000,
    )


class FakeProcessMemory:
    pid = 91
    executable_name = "sb.exe"
    executable_path = Path("C:/Wonderbane/sb.exe")
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4

    def __init__(self) -> None:
        self.memory: dict[int, int] = {}
        self.closed = False

    def write(self, address: int, value: bytes) -> None:
        self.memory.update({address + index: byte for index, byte in enumerate(value)})

    def read(self, address: int, size: int) -> bytes:
        try:
            return bytes(self.memory[address + offset] for offset in range(size))
        except KeyError as exc:
            raise OSError(f"unexpected read at 0x{address:X}") from exc

    def close(self) -> None:
        self.closed = True


def _pointer(value: int) -> bytes:
    return struct.pack("<I", value)


def _write_string(
    process: FakeProcessMemory,
    address: int,
    buffer: int,
    value: str,
) -> None:
    encoded = value.encode("utf-16-le")
    process.write(
        address,
        struct.pack("<IIII", 0x10021A34, buffer, buffer + len(encoded), buffer + len(encoded) + 8),
    )
    process.write(buffer, encoded + b"\x00\x00")


def _write_node(
    process: FakeProcessMemory,
    address: int,
    *,
    parent: int,
    left: int,
    right: int,
    object_uuid: int,
    zone_name: str,
    lt: float,
    lg: float,
    altitude: float,
    string_buffer: int,
) -> None:
    process.write(address, bytes(0x3C))
    process.write(address + 4, struct.pack("<III", parent, left, right))
    process.write(address + 0x10, struct.pack("<II", 7, object_uuid))
    _write_string(process, address + 0x18, string_buffer, zone_name)
    process.write(address + 0x30, struct.pack("<fff", lt, altitude, -lg))


def _fixture() -> FakeProcessMemory:
    profile = _profile()
    process = FakeProcessMemory()
    registry = 0x21000000
    head = 0x22000000
    sea_dog = 0x22000100
    tyranth = 0x22000200
    process.write(process.base_address + profile.registry_pointer_rva, _pointer(registry))
    process.write(registry + profile.registry_tree_offset, _pointer(head))
    process.write(head, bytes(0x0C))
    process.write(head + profile.head_first_node_offset, _pointer(sea_dog))
    _write_node(
        process,
        sea_dog,
        parent=tyranth,
        left=0,
        right=0,
        object_uuid=401,
        zone_name="Sea Dog's Rest",
        lt=88_980,
        lg=45_020,
        altitude=132,
        string_buffer=0x23000000,
    )
    _write_node(
        process,
        tyranth,
        parent=head,
        left=sea_dog,
        right=0,
        object_uuid=402,
        zone_name="Tyranth",
        lt=46_720,
        lg=53_632,
        altitude=144,
        string_buffer=0x23000100,
    )
    return process


class NativeRunegateRegistryReaderTests(unittest.TestCase):
    def test_reads_server_registry_in_tree_order_and_converts_native_longitude(self) -> None:
        observation = NativeRunegateRegistryReader(_profile(), _fixture()).observe()

        self.assertEqual(2, len(observation.runegates))
        sea_dog = observation.runegates[0]
        self.assertEqual((7, 401), (sea_dog.object_type, sea_dog.object_uuid))
        self.assertEqual("Sea Dog's Rest", sea_dog.zone_name)
        self.assertEqual((88_980, 45_020, 132), (sea_dog.lt, sea_dog.lg, sea_dog.altitude))
        self.assertEqual(24, len(observation.registry_token))

    def test_executable_hash_mismatch_fails_before_reads(self) -> None:
        process = _fixture()
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(
            NativeRunegateRegistryCompatibilityError,
            "SHA-256",
        ):
            NativeRunegateRegistryReader(_profile(), process)


class NativeRunegateRegistryProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_decoded_registry_layout(self) -> None:
        profile = load_bundled_native_runegate_registry_profile()

        self.assertEqual(0x1389028, profile.registry_pointer_rva)
        self.assertEqual(0xA4, profile.registry_tree_offset)
        self.assertEqual(
            (4, 8, 12),
            (
                profile.node_parent_offset,
                profile.node_left_offset,
                profile.node_right_offset,
            ),
        )
        self.assertEqual(
            (0x10, 0x18, 0x30, 0x38),
            (
                profile.object_type_offset,
                profile.zone_name_offset,
                profile.latitude_offset,
                profile.longitude_offset,
            ),
        )
        self.assertEqual(-1.0, profile.longitude_multiplier)

    def test_profile_loader_rejects_unknown_fields(self) -> None:
        bundled = load_bundled_native_runegate_registry_profile()
        raw = {field: getattr(bundled, field) for field in bundled.__dataclass_fields__}
        raw["unknown"] = True

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_native_runegate_registry_profile_text(json.dumps(raw))


class FakeNativeRunegateReader:
    process_id = 91

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def observe(self) -> NativeRunegateRegistryObservation:
        return NativeRunegateRegistryObservation(
            runegates=(
                NativeRunegateObservation(
                    object_type=7,
                    object_uuid=401,
                    zone_name="Sea Dog's Rest",
                    lt=88_980,
                    lg=45_020,
                    altitude=132,
                ),
            ),
            registry_token="ab" * 12,
        )


class NativeRunegateRegistryCliTests(unittest.TestCase):
    def test_command_emits_server_runegates(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_runegate_registry_profile",
                return_value=_profile(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_runegate_registry_reader",
                return_value=FakeNativeRunegateReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "observe-native-runegates", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(1, payload["runegate_count"])
        self.assertEqual("Sea Dog's Rest", payload["runegates"][0]["zone_name"])
        self.assertEqual(88_980, payload["runegates"][0]["lt"])
        self.assertEqual(45_020, payload["runegates"][0]["lg"])


if __name__ == "__main__":
    unittest.main()
