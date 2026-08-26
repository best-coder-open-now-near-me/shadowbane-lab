import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NativePlayerPositionCompatibilityError,
    NativePlayerPositionObservation,
    NativePlayerPositionProfile,
    NativePlayerPositionReader,
    NativePlayerPositionReadError,
    load_bundled_native_position_profile,
    load_native_position_profile_text,
)


def _profile() -> NativePlayerPositionProfile:
    return NativePlayerPositionProfile(
        profile_id="position-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        player_pointer_rva=0x200,
        player_altitude_offset=0xAD8,
        transform_scale_signature=(1.0, 1.1, 1.0),
        scale_offset=0x1C,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        minimum_world_coordinate=0,
        maximum_world_coordinate=200_000,
        minimum_altitude=-2_000,
        maximum_altitude=20_000,
        player_altitude_tolerance=5,
        cluster_radius=8,
        maximum_cluster_spread=25,
        minimum_cluster_size=3,
        maximum_tracking_delta=2_000,
        maximum_region_size=64 * 1024 * 1024,
    )


class FakePositionProcess:
    pid = 77
    executable_name = "sb.exe"
    executable_path = Path("C:/Wonderbane/sb.exe")
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4

    def __init__(self, addresses: tuple[int, ...], values: dict[int, list[bytes]]) -> None:
        self.addresses = addresses
        self.values = {address: list(items) for address, items in values.items()}
        self.closed = False

    def find_private_pattern(self, pattern: bytes, **_: int) -> tuple[int, ...]:
        if pattern != _profile().signature_bytes:
            raise AssertionError("unexpected signature")
        return self.addresses

    def read(self, address: int, size: int) -> bytes:
        try:
            responses = self.values[address]
            value = responses[0] if len(responses) == 1 else responses.pop(0)
        except (KeyError, IndexError) as exc:
            raise OSError(f"unexpected read at 0x{address:X}") from exc
        if len(value) != size:
            raise AssertionError(f"expected {size} bytes")
        return value

    def close(self) -> None:
        self.closed = True


def _triplet(lt: float, lg: float, altitude: float) -> bytes:
    return struct.pack("<fff", lt, altitude, -lg)


def _fixture(
    player_positions: list[tuple[float, float, float]],
    other_positions: list[tuple[float, float, float]] | None = None,
) -> tuple[FakePositionProcess, tuple[int, ...]]:
    profile = _profile()
    player = 0x35000000
    slot = FakePositionProcess.base_address + profile.player_pointer_rva
    values: dict[int, list[bytes]] = {
        slot: [struct.pack("<I", player)],
        player + profile.player_altitude_offset: [struct.pack("<f", 148.0)],
    }
    signatures = []
    player_addresses = []
    for index, position in enumerate(player_positions):
        address = 0x2B000000 + index * 0x100
        signatures.append(address + profile.scale_offset)
        player_addresses.append(address)
        values[address] = [_triplet(*position)]
    for index, position in enumerate(other_positions or []):
        address = 0x2C000000 + index * 0x100
        signatures.append(address + profile.scale_offset)
        values[address] = [_triplet(*position)]
    return FakePositionProcess(tuple(signatures), values), tuple(player_addresses)


class NativePlayerPositionReaderTests(unittest.TestCase):
    def test_locates_altitude_matched_cluster_and_reads_median_position(self) -> None:
        process, addresses = _fixture(
            [
                (106661.5, 52431.5, 147.5),
                (106662.0, 52432.0, 148.0),
                (106662.5, 52432.5, 148.5),
                (106662.25, 52431.75, 147.75),
            ],
            [
                (88848.0, 45045.0, 28.0),
                (88849.0, 45045.0, 28.5),
                (88848.0, 45046.0, 29.0),
            ],
        )

        reader = NativePlayerPositionReader(_profile(), process)
        observation = reader.observe()

        self.assertEqual(addresses, reader.transform_addresses)
        self.assertAlmostEqual(106662.125, observation.lt)
        self.assertAlmostEqual(52431.875, observation.lg)
        self.assertAlmostEqual(147.875, observation.altitude)
        self.assertEqual(4, observation.transform_count)

    def test_tracks_moving_cluster_at_cached_addresses(self) -> None:
        process, _ = _fixture(
            [
                (1000, 2000, 148),
                (1001, 2001, 148),
                (999, 1999, 148),
            ]
        )
        for address in tuple(process.values):
            if len(process.values[address][0]) == 12:
                initial = process.values[address][0]
                lt, altitude, negative_lg = struct.unpack("<fff", initial)
                process.values[address] = [
                    initial,
                    initial,
                    struct.pack("<fff", lt + 100, altitude, negative_lg - 50),
                ]

        reader = NativePlayerPositionReader(_profile(), process)
        first = reader.observe()
        second = reader.observe()

        self.assertAlmostEqual(1000, first.lt)
        self.assertAlmostEqual(1100, second.lt)
        self.assertAlmostEqual(2050, second.lg)

    def test_fails_closed_when_too_few_transforms_match_player_altitude(self) -> None:
        process, _ = _fixture([(1000, 2000, 148), (1001, 2001, 148)])

        with self.assertRaisesRegex(NativePlayerPositionReadError, "no altitude-matched"):
            NativePlayerPositionReader(_profile(), process)

    def test_executable_hash_mismatch_fails_before_scan(self) -> None:
        process, _ = _fixture(
            [(1000, 2000, 148), (1001, 2001, 148), (999, 1999, 148)]
        )
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativePlayerPositionCompatibilityError, "SHA-256"):
            NativePlayerPositionReader(_profile(), process)


class NativePlayerPositionProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_live_calibration(self) -> None:
        profile = load_bundled_native_position_profile()

        self.assertEqual(0x16A2D98, profile.player_pointer_rva)
        self.assertEqual(0xAD8, profile.player_altitude_offset)
        self.assertEqual(0x1C, profile.scale_offset)
        self.assertEqual(
            (1.0303125381469727, 1.0862499475479126, 1.0303125381469727),
            profile.transform_scale_signature,
        )

    def test_profile_loader_rejects_unknown_fields(self) -> None:
        bundled = load_bundled_native_position_profile()
        raw = {
            field: getattr(bundled, field)
            for field in bundled.__dataclass_fields__
        }
        raw["transform_scale_signature"] = list(raw["transform_scale_signature"])
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
        return NativePlayerPositionObservation(106765.5, 52335.7, 146.7, 44)


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
        self.assertEqual(44, payload["transform_count"])


if __name__ == "__main__":
    unittest.main()
