from __future__ import annotations

import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation.native_health import NativeMemoryRegion
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogBreakpoint,
    NativeVendorDialogCompatibilityError,
    NativeVendorDialogDebugHit,
    NativeVendorDialogProfile,
    NativeVendorDialogTracer,
    NativeVendorDialogTraceSummary,
    load_bundled_native_vendor_dialog_profile,
    load_bundled_native_vendor_dialog_profiles,
)


def _profile() -> NativeVendorDialogProfile:
    return NativeVendorDialogProfile(
        profile_id="vendor-dialog-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        preferred_image_base=0x400000,
        message_vtable_rva=0x115463C,
        message_object_size=0x114,
        message_type_offset=0x60,
        language_offset=0x64,
        language_text_offset=0x68,
        source_cache_id_offset=0x80,
        vendor_cache_id_offset=0x88,
        options_tree_offset=0xE8,
        options_count_offset=0xEC,
        string_begin_offset=4,
        string_end_offset=8,
        string_capacity_offset=12,
        stream_snapshot_size=64,
        pointer_window_size=32,
        maximum_pointer_windows=4,
        maximum_string_bytes=1024,
        maximum_option_count=16,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        breakpoints=(
            NativeVendorDialogBreakpoint("inbound_entry", 0x1000, "558BEC6A"),
            NativeVendorDialogBreakpoint("inbound_complete", 0x1100, "8B4DF45F"),
            NativeVendorDialogBreakpoint("outbound_entry", 0x1200, "558BEC53"),
            NativeVendorDialogBreakpoint("outbound_complete", 0x1300, "5F5E5B5D"),
        ),
    )


class FakeVendorDialogDebugBackend:
    pid = 77
    executable_name = "sb.exe"
    executable_path = Path("C:/Wonderbane/sb.exe")
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4
    process_creation_filetime_utc = 123456

    def __init__(self, profile: NativeVendorDialogProfile) -> None:
        self.memory: dict[int, bytes] = {}
        self.hits: list[tuple[NativeVendorDialogDebugHit, dict[int, bytes]]] = []
        self.attached: dict[str, int] | None = None
        self.continued: list[str] = []
        self.closed = False
        self.elapsed_seconds = 0.0
        for breakpoint in profile.breakpoints:
            self.memory[self.base_address + breakpoint.rva] = breakpoint.signature

    def read_block(self, address: int, size: int) -> bytes:
        for start, value in self.memory.items():
            if start <= address and address + size <= start + len(value):
                offset = address - start
                return value[offset : offset + size]
        raise OSError(f"unmapped test read at 0x{address:X}")

    def query_region(self, address: int) -> NativeMemoryRegion:
        return NativeMemoryRegion(0x10000, 0x70000000, 4, 0x20000)

    def attach(self, breakpoints: dict[str, int]) -> None:
        self.attached = dict(breakpoints)

    def wait_for_hit(self, timeout_ms: int) -> NativeVendorDialogDebugHit | None:
        if not self.hits:
            self.elapsed_seconds += timeout_ms / 1000
            return None
        self.elapsed_seconds += 0.001
        hit, mutations = self.hits.pop(0)
        self.memory.update(mutations)
        return hit

    def continue_hit(
        self,
        hit: NativeVendorDialogDebugHit,
        *,
        disable_role: bool = False,
    ) -> None:
        self.continued.append(hit.role)

    def close(self) -> None:
        self.closed = True


def _message(profile: NativeVendorDialogProfile, message_type: int) -> bytearray:
    raw = bytearray(profile.message_object_size)
    vtable = FakeVendorDialogDebugBackend.base_address + profile.message_vtable_rva
    struct.pack_into("<I", raw, 0, vtable)
    struct.pack_into("<I", raw, profile.message_type_offset, message_type)
    struct.pack_into("<II", raw, profile.source_cache_id_offset, 7, 101)
    struct.pack_into("<II", raw, profile.vendor_cache_id_offset, 8, 202)
    return raw


def _hit(role: str, *, thread_id: int, registers: dict[str, int]) -> NativeVendorDialogDebugHit:
    defaults = {
        "eax": 0,
        "ebx": 0,
        "ecx": 0,
        "edx": 0,
        "esi": 0,
        "edi": 0,
        "ebp": 0,
        "esp": 0,
        "eip": 0,
        "eflags": 0,
        "dr6": 1,
        "dr7": 0x55,
    }
    defaults.update(registers)
    return NativeVendorDialogDebugHit(role, 77, thread_id, defaults["eip"], defaults)


class NativeVendorDialogTracerTests(unittest.TestCase):
    def test_captures_request_and_decoded_menu_with_option(self) -> None:
        profile = _profile()
        backend = FakeVendorDialogDebugBackend(profile)
        message_address = 0x200000
        stream_address = 0x210000
        stack_address = 0x220000
        header_address = 0x230000
        node_address = 0x230100
        stream = bytes(profile.stream_snapshot_size)
        stack = bytearray(8)
        struct.pack_into("<I", stack, 4, stream_address)
        request = _message(profile, 1)
        menu = _message(profile, 3)
        struct.pack_into("<II", menu, profile.options_tree_offset, header_address, 1)
        header = bytearray(16)
        struct.pack_into("<I", header, 8, node_address)
        node = bytearray(0x1C)
        struct.pack_into("<III", node, 0x10, 0x10, 0x20, 0)
        backend.memory.update(
            {
                message_address: bytes(request),
                stream_address: stream,
                stack_address: bytes(stack),
                header_address: bytes(header),
                node_address: bytes(node),
            }
        )
        backend.hits = [
            (
                _hit(
                    "outbound_entry",
                    thread_id=5,
                    registers={"ecx": message_address, "esp": stack_address, "eip": 0x401200},
                ),
                {message_address: bytes(request)},
            ),
            (
                _hit(
                    "outbound_complete",
                    thread_id=5,
                    registers={"ebx": message_address, "esi": stream_address, "eip": 0x401300},
                ),
                {},
            ),
            (
                _hit(
                    "inbound_entry",
                    thread_id=5,
                    registers={"ecx": message_address, "esp": stack_address, "eip": 0x401000},
                ),
                {message_address: bytes(_message(profile, 0))},
            ),
            (
                _hit(
                    "inbound_complete",
                    thread_id=5,
                    registers={"eip": 0x401100},
                ),
                {message_address: bytes(menu)},
            ),
        ]
        tracer = NativeVendorDialogTracer(profile, backend)

        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            patch(
                "shadowbane_lab.client_observation.native_vendor_dialog.time",
                SimpleNamespace(monotonic=lambda: backend.elapsed_seconds),
            ),
        ):
            path = Path(temporary_directory) / "pelt.jsonl"
            summary = tracer.trace(
                path,
                label="pelt-light-armor-fence",
                timeout_seconds=0.1,
                settle_seconds=0.01,
            )
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(4, summary.hit_count)
        self.assertEqual(2, summary.complete_message_count)
        self.assertGreaterEqual(summary.elapsed_seconds, 0.01)
        self.assertLess(summary.elapsed_seconds, 0.1)
        self.assertEqual(
            ["outbound_entry", "outbound_complete", "inbound_entry", "inbound_complete"],
            backend.continued,
        )
        self.assertTrue(backend.closed)
        request_record = records[1]
        reply_record = records[4]
        self.assertEqual("client_to_server", request_record["direction"])
        self.assertEqual(
            "initial_request",
            request_record["decoded_message"]["message_type_semantics"],
        )
        self.assertEqual("server_to_client", reply_record["direction"])
        self.assertEqual("dialog_menu", reply_record["decoded_message"]["message_type_semantics"])
        self.assertEqual(1, reply_record["decoded_message"]["option_count"])
        self.assertEqual(0, reply_record["decoded_message"]["options"][0]["option_id"])
        self.assertFalse(records[0]["client_code_modified"])

    def test_timeout_without_events_uses_backend_wait_clock(self) -> None:
        profile = _profile()
        backend = FakeVendorDialogDebugBackend(profile)
        tracer = NativeVendorDialogTracer(profile, backend)
        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            patch(
                "shadowbane_lab.client_observation.native_vendor_dialog.time",
                SimpleNamespace(monotonic=lambda: backend.elapsed_seconds),
            ),
        ):
            summary = tracer.trace(
                Path(temporary_directory) / "timeout.jsonl",
                label="no-events",
                timeout_seconds=0.1,
                settle_seconds=0.01,
            )
        self.assertTrue(summary.timed_out_without_events)
        self.assertEqual(0, summary.hit_count)
        self.assertGreaterEqual(summary.elapsed_seconds, 0.1)
        self.assertLessEqual(summary.elapsed_seconds, 0.101)
        self.assertTrue(backend.closed)

    def test_executable_hash_mismatch_fails_before_attach(self) -> None:
        profile = _profile()
        backend = FakeVendorDialogDebugBackend(profile)
        backend.executable_sha256 = "cd" * 32

        with self.assertRaisesRegex(NativeVendorDialogCompatibilityError, "SHA-256"):
            NativeVendorDialogTracer(profile, backend)

        self.assertIsNone(backend.attached)


class NativeVendorDialogProfileTests(unittest.TestCase):
    def test_bundled_profile_contains_verified_message_layout_and_breakpoints(self) -> None:
        profile = load_bundled_native_vendor_dialog_profile()
        breakpoints = {item.role: item.rva for item in profile.breakpoints}

        self.assertEqual(0x115463C, profile.message_vtable_rva)
        self.assertEqual(0x60, profile.message_type_offset)
        self.assertEqual(0xE8, profile.options_tree_offset)
        self.assertEqual(0x3614D0, breakpoints["inbound_entry"])
        self.assertEqual(0x361A29, breakpoints["outbound_complete"])

    def test_bundled_profiles_cover_original_and_text_fix_executables(self) -> None:
        profiles = load_bundled_native_vendor_dialog_profiles()

        self.assertEqual(
            {
                "ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13",
                "2b186aef864ea1ce16d8ec959c450f1f2e301d1ba25d9daa3b14ab6c65d68c3d",
            },
            {profile.executable_sha256 for profile in profiles},
        )
        self.assertEqual(1, len({profile.message_vtable_rva for profile in profiles}))


class FakeCliTracer:
    backend = SimpleNamespace(pid=77)

    def trace(
        self,
        output_path: Path,
        *,
        label: str,
        timeout_seconds: float,
        settle_seconds: float,
        armed_callback,
    ) -> NativeVendorDialogTraceSummary:
        self.arguments = (timeout_seconds, settle_seconds)
        armed_callback()
        return NativeVendorDialogTraceSummary(
            profile_id="vendor-dialog-test",
            process_id=77,
            label=label,
            output_path=output_path,
            hit_count=4,
            complete_message_count=2,
            timed_out_without_events=False,
            elapsed_seconds=0.25,
        )


class NativeVendorDialogCliTests(unittest.TestCase):
    def test_trace_command_emits_summary_and_armed_notice(self) -> None:
        output = io.StringIO()
        errors = io.StringIO()
        tracer = FakeCliTracer()
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory) / "pelt.jsonl"
            with (
                patch(
                    "shadowbane_lab.cli.open_windows_bundled_native_vendor_dialog_tracer",
                    return_value=(_profile(), tracer),
                ),
                redirect_stdout(output),
                redirect_stderr(errors),
            ):
                result = main(
                    (
                        "client",
                        "trace-native-vendor-dialog",
                        "--output",
                        str(evidence),
                        "--label",
                        "pelt-light-armor-fence",
                        "--timeout-seconds",
                        "30",
                        "--settle-seconds",
                        "1",
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(2, payload["complete_message_count"])
        self.assertEqual([30.0, 1.0], list(tracer.arguments))
        self.assertIn("trace armed", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
