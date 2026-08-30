import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativeGroupCompatibilityError,
    NativeGroupMemberObservation,
    NativeGroupObservation,
    NativeGroupProfile,
    NativeGroupReader,
    NativeGroupReadError,
    load_bundled_native_group_profile,
    load_native_group_profile_text,
)


def _profile() -> NativeGroupProfile:
    return NativeGroupProfile(
        profile_id="native-group-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        window_pointer_rva=0x200,
        group_manager_offset=0x98,
        split_gold_offset=0x98,
        local_follow_offset=0x99,
        member_list_offset=0x9C,
        list_node_next_offset=0,
        list_node_value_offset=8,
        member_object_type_offset=0x10,
        member_uuid_offset=0x14,
        member_first_name_offset=0x28,
        member_last_name_offset=0x40,
        member_health_percent_offset=0x5C,
        member_stamina_percent_offset=0x60,
        member_mana_percent_offset=0x64,
        member_position_x_offset=0x68,
        member_position_y_offset=0x6C,
        member_position_z_offset=0x70,
        member_role_offset=0x74,
        member_follow_offset=0x78,
        string_begin_offset=4,
        string_end_offset=8,
        string_capacity_offset=12,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        maximum_member_name_chars=64,
        maximum_members=10,
        maximum_absolute_coordinate=250_000,
    )


class FakeProcessMemory:
    pid = 81
    executable_name = "sb.exe"
    executable_path = Path("C:/Wonderbane/sb.exe")
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4

    def __init__(self) -> None:
        self.memory: dict[int, int] = {}
        self.read_overrides: dict[tuple[int, int], list[bytes]] = {}
        self.closed = False

    def write(self, address: int, value: bytes) -> None:
        self.memory.update({address + index: byte for index, byte in enumerate(value)})

    def read(self, address: int, size: int) -> bytes:
        overrides = self.read_overrides.get((address, size))
        if overrides:
            return overrides[0] if len(overrides) == 1 else overrides.pop(0)
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
    if not value:
        process.write(address, bytes(16))
        return
    encoded = value.encode("utf-16-le")
    process.write(
        address,
        struct.pack("<IIII", 0x10021A34, buffer, buffer + len(encoded), buffer + len(encoded) + 16),
    )
    process.write(buffer, encoded + b"\x00\x00")


def _fixture(*, empty: bool = False) -> tuple[FakeProcessMemory, dict[str, int]]:
    profile = _profile()
    process = FakeProcessMemory()
    addresses = {
        "window": 0x21000000,
        "manager": 0x22000000,
        "sentinel": 0x23000000,
        "node": 0x23000100,
        "entry": 0x24000000,
    }
    slot = process.base_address + profile.window_pointer_rva
    process.write(slot, _pointer(addresses["window"]))
    process.write(
        addresses["window"] + profile.group_manager_offset,
        _pointer(addresses["manager"]),
    )
    process.write(addresses["manager"] + profile.split_gold_offset, b"\x01\x01")
    process.write(
        addresses["manager"] + profile.member_list_offset,
        _pointer(addresses["sentinel"]),
    )
    process.write(
        addresses["sentinel"],
        _pointer(addresses["sentinel"] if empty else addresses["node"]),
    )
    if empty:
        return process, addresses

    process.write(addresses["node"], _pointer(addresses["sentinel"]))
    process.write(addresses["node"] + 8, _pointer(addresses["entry"]))
    process.write(addresses["entry"] + 0x10, struct.pack("<II", 10, 73421))
    _write_string(process, addresses["entry"] + 0x28, 0x25000000, "Ashen")
    _write_string(process, addresses["entry"] + 0x40, 0x25000100, "Blade")
    process.write(
        addresses["entry"] + 0x5C,
        struct.pack(
            "<iiifffIB",
            87,
            62,
            49,
            106662.0,
            148.0,
            -52432.0,
            0x16,
            1,
        ),
    )
    return process, addresses


class NativeGroupReaderTests(unittest.TestCase):
    def test_reads_leader_resources_coordinates_and_follow_state(self) -> None:
        process, _ = _fixture()

        observation = NativeGroupReader(_profile(), process).observe()

        self.assertTrue(observation.grouped)
        self.assertTrue(observation.split_gold_enabled)
        self.assertTrue(observation.local_follow_enabled)
        self.assertEqual(1, len(observation.members))
        leader = observation.leader
        self.assertIsNotNone(leader)
        assert leader is not None
        self.assertEqual("Ashen Blade", leader.full_name)
        self.assertEqual((10, 73421), (leader.object_type, leader.object_uuid))
        self.assertEqual(
            (87, 62, 49),
            (
                leader.health_percent,
                leader.stamina_percent,
                leader.mana_percent,
            ),
        )
        self.assertEqual(
            (106662.0, 52432.0, 148.0),
            (
                leader.lt,
                leader.lg,
                leader.altitude,
            ),
        )
        self.assertTrue(leader.follow_enabled)

    def test_reads_empty_roster_without_inventing_a_leader(self) -> None:
        process, _ = _fixture(empty=True)

        observation = NativeGroupReader(_profile(), process).observe()

        self.assertFalse(observation.grouped)
        self.assertEqual((), observation.members)
        self.assertIsNone(observation.leader)

    def test_rejects_roster_that_changes_during_stability_check(self) -> None:
        process, addresses = _fixture()
        process.read_overrides[(addresses["sentinel"], 4)] = [
            _pointer(addresses["node"]),
            _pointer(addresses["sentinel"]),
        ]

        with self.assertRaisesRegex(NativeGroupReadError, "changed"):
            NativeGroupReader(_profile(), process, stability_attempts=1).observe()

    def test_executable_hash_mismatch_fails_before_reads(self) -> None:
        process, _ = _fixture()
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativeGroupCompatibilityError, "SHA-256"):
            NativeGroupReader(_profile(), process)


class NativeGroupProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_static_client_offsets(self) -> None:
        profile = load_bundled_native_group_profile()

        self.assertEqual(0x16A7BFC, profile.window_pointer_rva)
        self.assertEqual(0x98, profile.group_manager_offset)
        self.assertEqual(
            (0x98, 0x99, 0x9C),
            (
                profile.split_gold_offset,
                profile.local_follow_offset,
                profile.member_list_offset,
            ),
        )
        self.assertEqual(
            (0, 8),
            (
                profile.list_node_next_offset,
                profile.list_node_value_offset,
            ),
        )
        self.assertEqual(
            (0x5C, 0x68, 0x74, 0x78),
            (
                profile.member_health_percent_offset,
                profile.member_position_x_offset,
                profile.member_role_offset,
                profile.member_follow_offset,
            ),
        )

    def test_profile_loader_rejects_unknown_fields(self) -> None:
        bundled = load_bundled_native_group_profile()
        raw = {field: getattr(bundled, field) for field in bundled.__dataclass_fields__}
        raw["unknown"] = True

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_native_group_profile_text(json.dumps(raw))


class FakeNativeGroupReader:
    process_id = 81

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def observe(self) -> NativeGroupObservation:
        return NativeGroupObservation(
            split_gold_enabled=True,
            local_follow_enabled=False,
            members=(
                NativeGroupMemberObservation(
                    first_name="Ashen",
                    last_name="Blade",
                    object_type=10,
                    object_uuid=73421,
                    health_percent=87,
                    stamina_percent=62,
                    mana_percent=49,
                    lt=106662.0,
                    lg=52432.0,
                    altitude=148.0,
                    role_code=0x16,
                    follow_enabled=True,
                ),
            ),
        )


class NativeGroupCliTests(unittest.TestCase):
    def test_command_emits_native_group_roster(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_group_profile",
                return_value=_profile(),
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_group_reader",
                return_value=FakeNativeGroupReader(),
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "observe-native-group", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["grouped"])
        self.assertEqual(73421, payload["leader_uuid"])
        self.assertEqual("Ashen Blade", payload["members"][0]["full_name"])
        self.assertEqual(106662.0, payload["members"][0]["lt"])
        self.assertEqual(52432.0, payload["members"][0]["lg"])


if __name__ == "__main__":
    unittest.main()
