import json
import struct
import unittest
from pathlib import Path

from shadowbane_lab.client_observation.native_health import NativeMemoryRegion
from shadowbane_lab.client_observation.native_message_hud import (
    NativeMessageHudCompatibilityError,
    NativeMessageHudProfile,
    NativeMessageHudReader,
    NativeMessageHudReadError,
    load_bundled_native_message_hud_profile,
    load_native_message_hud_profile_text,
)

_COMBAT = "255000000"
_POWERS = "000255000"


def _profile() -> NativeMessageHudProfile:
    return NativeMessageHudProfile(
        profile_id="native-message-hud-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        maximum_scan_address=0x20000000,
        scan_memory_type=0x20000,
        scan_protection=4,
        channel_colors=(_COMBAT, _POWERS),
        minimum_markers_per_buffer=3,
        maximum_marker_gap_bytes=4096,
        maximum_prefix_slack_bytes=256,
        maximum_transcript_characters=4096,
        maximum_candidate_buffers=8,
    )


def _record(color: str, message: str) -> str:
    return f"^\\c{color}{message}\n"


class FakeScanningProcess:
    pid = 4320
    executable_name = "sb.exe"
    executable_path = Path("C:/Wonderbane/sb.exe")
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4

    region_base = 0x200000
    region_size = 0x10000
    transcript_begin = 0x202000
    allocator = 0x240000

    def __init__(self, text: str, *, pointer_fields: tuple[int, ...] = (0x300004,)) -> None:
        self.text = text
        self.pointer_fields = pointer_fields
        self.closed = False

    def read(self, address: int, size: int) -> bytes:
        if address in {field - 4 for field in self.pointer_fields} and size == 16:
            encoded = self.text.encode("utf-16-le")
            return struct.pack(
                "<IIII",
                self.allocator,
                self.transcript_begin,
                self.transcript_begin + len(encoded),
                self.transcript_begin + 0x1000,
            )
        raise AssertionError(f"unexpected bounded read at 0x{address:X} ({size})")

    def read_block(self, address: int, size: int) -> bytes:
        region = bytearray(self.region_size)
        encoded = self.text.encode("utf-16-le")
        offset = self.transcript_begin - self.region_base
        region[offset : offset + len(encoded)] = encoded
        start = address - self.region_base
        end = start + size
        if start < 0 or end > len(region):
            raise AssertionError(f"unexpected block read at 0x{address:X} ({size})")
        return bytes(region[start:end])

    def query_region(self, address: int) -> NativeMemoryRegion:
        if not self.region_base <= address < self.region_base + self.region_size:
            raise AssertionError(f"unexpected region query at 0x{address:X}")
        return NativeMemoryRegion(self.region_base, self.region_size, 4, 0x20000)

    def find_all(
        self,
        needles: tuple[bytes, ...],
        *,
        memory_type: int | None = None,
        protection: int | None = None,
        maximum_results_per_needle: int = 20_000,
        maximum_address: int | None = None,
    ) -> dict[bytes, tuple[int, ...]]:
        del maximum_results_per_needle
        if maximum_address != 0x20000000:
            raise AssertionError("reader did not retain the calibrated scan ceiling")
        if memory_type != 0x20000 or protection != 4:
            raise AssertionError("reader did not retain the calibrated scan bounds")
        encoded_prefix = "^\\c".encode("utf-16-le")
        if needles == (encoded_prefix,):
            payload = self.text.encode("utf-16-le")
            hits = []
            start = 0
            while (index := payload.find(encoded_prefix, start)) >= 0:
                hits.append(self.transcript_begin + index)
                start = index + 1
            return {encoded_prefix: tuple(hits)}
        begin_needle = struct.pack("<I", self.transcript_begin)
        if needles != (begin_needle,):
            raise AssertionError(f"unexpected pointer needles: {needles!r}")
        return {begin_needle: self.pointer_fields}

    def find_pointer_values_near(
        self,
        targets: tuple[int, ...],
        *,
        maximum_offset: int,
        memory_type: int | None = None,
        protection: int | None = None,
        maximum_results_per_target: int = 1_000,
        maximum_address: int | None = None,
    ) -> dict[int, tuple[tuple[int, int], ...]]:
        del maximum_results_per_target
        if maximum_offset != 256 or memory_type != 0x20000 or protection != 4:
            raise AssertionError("reader did not retain pointer scan bounds")
        if maximum_address != 0x20000000:
            raise AssertionError("reader did not retain the calibrated scan ceiling")
        if targets != (self.transcript_begin,):
            raise AssertionError(f"unexpected pointer targets: {targets!r}")
        return {
            self.transcript_begin: tuple(
                (field, self.transcript_begin) for field in self.pointer_fields
            )
        }

    def close(self) -> None:
        self.closed = True


def _initial_text() -> str:
    return "".join(
        (
            _record(_COMBAT, "You hit the Og-Barbatorr for 57 points of damage!"),
            _record(_POWERS, "You begin using Shadow Bolt."),
            _record(_COMBAT, "The Og-Barbatorr misses YOU!"),
        )
    )


class NativeMessageHudReaderTests(unittest.TestCase):
    def test_attaches_structurally_and_emits_only_appended_native_messages(self) -> None:
        process = FakeScanningProcess(_initial_text())
        reader = NativeMessageHudReader(
            _profile(),
            process,
            start_at_end=True,
            timestamp_factory=lambda: "1:02:03",
        )

        self.assertEqual((), reader.read_new_entries())
        process.text += _record(
            _COMBAT,
            "You have killed the Og-Barbatorr!",
        )
        entries = reader.read_new_entries()

        self.assertTrue(reader.attached)
        self.assertEqual(1, len(entries))
        self.assertEqual(0, entries[0].sequence)
        self.assertEqual("1:02:03", entries[0].timestamp)
        self.assertEqual("You have killed the Og-Barbatorr!", entries[0].message)

    def test_can_emit_the_existing_snapshot_when_requested(self) -> None:
        reader = NativeMessageHudReader(
            _profile(),
            FakeScanningProcess(_initial_text()),
            start_at_end=False,
            timestamp_factory=lambda: "4:05:06",
        )

        entries = reader.read_new_entries()

        self.assertEqual(3, len(entries))
        self.assertEqual("You begin using Shadow Bolt.", entries[1].message)

    def test_rolling_hud_uses_record_overlap_without_replaying_history(self) -> None:
        process = FakeScanningProcess(_initial_text())
        reader = NativeMessageHudReader(_profile(), process, start_at_end=True)
        reader.read_new_entries()
        retained = "".join(
            (
                _record(_POWERS, "You begin using Shadow Bolt."),
                _record(_COMBAT, "The Og-Barbatorr misses YOU!"),
                _record(_COMBAT, "You hit the Og-Barbatorr for 99 points of damage!"),
            )
        )
        process.text = retained

        entries = reader.read_new_entries()

        self.assertEqual(1, len(entries))
        self.assertIn("99 points", entries[0].message)

    def test_unrelated_replacement_fails_closed_instead_of_replaying(self) -> None:
        process = FakeScanningProcess(_initial_text())
        reader = NativeMessageHudReader(_profile(), process, start_at_end=True)
        reader.read_new_entries()
        process.text = "".join(
            _record(_COMBAT, f"replacement {index}") for index in range(3)
        )

        with self.assertRaisesRegex(NativeMessageHudReadError, "overlap"):
            reader.read_new_entries()

    def test_incomplete_final_record_is_held_until_a_native_boundary_arrives(self) -> None:
        process = FakeScanningProcess(_initial_text() + f"^\\c{_COMBAT}You hit the target for")
        reader = NativeMessageHudReader(
            _profile(),
            process,
            start_at_end=False,
            timestamp_factory=lambda: "1:00:00",
        )

        first = reader.read_new_entries()
        process.text += " 88 points of damage!\n"
        second = reader.read_new_entries()

        self.assertEqual(3, len(first))
        self.assertEqual(1, len(second))
        self.assertEqual("You hit the target for 88 points of damage!", second[0].message)

    def test_ambiguous_structural_owners_fail_closed(self) -> None:
        process = FakeScanningProcess(
            _initial_text(),
            pointer_fields=(0x300004, 0x310004),
        )
        reader = NativeMessageHudReader(_profile(), process)

        with self.assertRaisesRegex(NativeMessageHudReadError, "ambiguous"):
            reader.attach()

    def test_executable_hash_mismatch_fails_before_scanning(self) -> None:
        process = FakeScanningProcess(_initial_text())
        process.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativeMessageHudCompatibilityError, "SHA-256"):
            NativeMessageHudReader(_profile(), process)

    def test_context_manager_closes_process(self) -> None:
        process = FakeScanningProcess(_initial_text())

        with NativeMessageHudReader(_profile(), process):
            pass

        self.assertTrue(process.closed)


class NativeMessageHudProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_the_live_build_and_native_channels(self) -> None:
        profile = load_bundled_native_message_hud_profile()

        self.assertEqual("sb.exe", profile.executable_name)
        self.assertEqual(
            "0889b39a6f065f2ddf696bad01455e0b691892077105fe27e35de94bfdf59ebc",
            profile.executable_sha256,
        )
        self.assertEqual((_COMBAT, _POWERS), profile.channel_colors)

    def test_unknown_profile_field_fails_closed(self) -> None:
        payload = json.loads(
            (
                Path(__file__).parents[1]
                / "src"
                / "shadowbane_lab"
                / "client_observation"
                / "data"
                / "wonderbane-0889b39a.native-message-hud.json"
            ).read_text(encoding="utf-8")
        )
        payload["surprise"] = True

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            load_native_message_hud_profile_text(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
