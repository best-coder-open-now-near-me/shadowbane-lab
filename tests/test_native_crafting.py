import json
import struct
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.client_observation.native_crafting import (
    CRAFTING_BREAKPOINTS,
    CRAFTING_EXECUTABLE_HASHES,
    CRAFTING_VTABLE_RVA,
    NativeCraftingTracer,
    capture_crafting_callers,
    decode_crafting_object,
)
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
    NativeVendorDialogDebugHit,
)


class Backend:
    pid = 77
    pointer_size = 4
    executable_name = "sb.exe"
    executable_sha256 = sorted(CRAFTING_EXECUTABLE_HASHES)[0]
    process_creation_filetime_utc = 123
    base_address = 0x400000

    def __init__(self):
        self.memory = {self.base_address + rva: sig for rva, sig in CRAFTING_BREAKPOINTS.values()}
        self.attached = False
        self.closed = False
        self.continued = []
        self.hits = []
        raw = bytearray(0x120)
        for offset, value in {
            0: self.base_address + CRAFTING_VTABLE_RVA,
            0x70: 8,
            0x78: 100,
            0x7C: 8,
            0x80: 200,
            0x84: 42,
            0xC0: 0xFFFFFFFF,
            0xC4: 40,
            0xC8: 1234,
            0x10C: 9000,
        }.items():
            struct.pack_into("<I", raw, offset, value)
        raw[0xE1] = 1
        raw[0x11C] = 1
        self.memory[0x200000] = bytes(raw)

    def read_block(self, address, size):
        return self.memory[address][:size]

    def attach(self, breakpoints):
        self.attached = True

    def close(self):
        self.closed = True

    def continue_hit(self, hit):
        self.continued.append(hit.role)

    def wait_for_hit(self, timeout_ms):
        return self.hits.pop(0) if self.hits else None

    def add_hit(self, role, *, thread=8, pid=77, registers=None):
        self.hits.append(
            NativeVendorDialogDebugHit(
                role,
                pid,
                thread,
                self.base_address + CRAFTING_BREAKPOINTS[role][0],
                {"ecx": 0x200000, **(registers or {})},
            )
        )


class NativeCraftingTests(unittest.TestCase):
    def test_native_result_references_and_hidden_balance(self):
        b = Backend()
        result = decode_crafting_object(b, 0x200000)
        self.assertEqual(200, result["vendor"]["object_id"])
        self.assertEqual(0xFFFFFFFF, result["roll"]["item"]["object_id"])
        self.assertEqual(1234, result["roll"]["template_id"])
        self.assertEqual(9000, result["strongbox_gold"])
        raw = bytearray(b.memory[0x200000])
        raw[0x11C] = 0
        b.memory[0x200000] = bytes(raw)
        self.assertNotIn("strongbox_gold", decode_crafting_object(b, 0x200000))

    def test_live_layout_keeps_zero_single_request_and_decodes_cache_ids(self):
        b = Backend()
        raw = bytearray(b.memory[0x200000])
        for offset, value in {
            0x70: 1,
            0x78: 100,
            0x7C: 8,
            0x80: 200,
            0x84: 42,
            0x88: 26990,
            0x8C: 0,
            0x90: 0,
            0x94: 12,
        }.items():
            struct.pack_into("<I", raw, offset, value)
        b.memory[0x200000] = bytes(raw)
        result = decode_crafting_object(b, 0x200000)
        self.assertEqual({"object_id": 100, "object_type": 8}, result["building"])
        self.assertEqual({"object_id": 200, "object_type": 42}, result["vendor"])
        self.assertEqual({"object_id": 26990, "object_type": 0}, result["item_or_template"])
        self.assertEqual(0, result["quantity_raw"])
        self.assertEqual(12, result["production_marker_raw"])
        self.assertEqual(0, result["multiple_slot_request"])

    def test_allocated_empty_name_does_not_read_zero_bytes(self):
        # The live client can retain a valid buffer after clearing its name.
        for capacity in (0x300000, 0x300080):
            with self.subTest(capacity=capacity):
                b = Backend()
                raw = bytearray(b.memory[0x200000])
                struct.pack_into("<III", raw, 0xE8, 0x300000, 0x300000, capacity)
                b.memory[0x200000] = bytes(raw)
                b.add_hit("outbound_entry")
                b.add_hit("outbound_complete")
                records = []
                with tempfile.TemporaryDirectory() as tmp:
                    summary = NativeCraftingTracer(b).trace(
                        Path(tmp) / "trace.jsonl", max_messages=1, on_message=records.append
                    )
                self.assertEqual("", records[0]["message"]["name"])
                self.assertEqual(1, summary["message_count"])
                self.assertEqual(2, len(b.continued))
                self.assertTrue(b.closed)

    def test_callback_runs_after_resume_with_process_identity(self):
        b = Backend()
        b.add_hit("inbound_entry")
        b.add_hit("inbound_complete")
        records = []

        def callback(record):
            self.assertEqual(2, len(b.continued))
            records.append(record)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            summary = NativeCraftingTracer(b).trace(path, max_messages=1, on_message=callback)
            journal = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(1, summary["message_count"])
        self.assertEqual(123, records[0]["process_creation_filetime_utc"])
        self.assertEqual("server_to_client", records[0]["direction"])
        self.assertNotIn("callers", records[0])
        self.assertEqual("session_end", journal[-1]["record_type"])
        self.assertTrue(b.closed)

    def test_caller_chain_is_bounded_and_stops_before_cycles_or_remote_reads(self):
        for next_frame, reason in (
            (0, "chain_end"),
            (0x500010, "invalid_frame_pointer"),
            (0x500000, "invalid_frame_pointer"),
            (0x500015, "invalid_frame_pointer"),
            (0x700000, "invalid_frame_pointer"),
        ):
            with self.subTest(next_frame=next_frame):
                b = Backend()
                b.memory[0x500000] = struct.pack("<I", 0x401234)
                b.memory[0x500010] = struct.pack("<II", next_frame, 0x402345)
                evidence = capture_crafting_callers(b, {"esp": 0x500000, "ebp": 0x500010})
                self.assertEqual([0x401234, 0x402345], evidence["return_addresses"])
                self.assertEqual(reason, evidence["stop_reason"])
        b = Backend()
        b.memory[0x500000] = struct.pack("<I", 0x401234)
        for i in range(1, 16):
            b.memory[0x500000 + i * 16] = struct.pack(
                "<II", 0x500000 + (i + 1) * 16, 0x401000 + i
            )
        evidence = capture_crafting_callers(b, {"esp": 0x500000, "ebp": 0x500010})
        self.assertEqual(16, len(evidence["return_addresses"]))
        self.assertEqual("frame_limit", evidence["stop_reason"])

    def test_caller_capture_validates_stack_and_preserves_read_failure(self):
        for esp in (None, True, 0, 0x500001, 0x80000000):
            evidence = capture_crafting_callers(Backend(), {"esp": esp})
            self.assertEqual([], evidence["return_addresses"])
            self.assertEqual("invalid_stack_pointer", evidence["stop_reason"])
        b = Backend()
        b.memory[0x500000] = b"x"
        evidence = capture_crafting_callers(b, {"esp": 0x500000})
        self.assertEqual("unreadable_stack", evidence["stop_reason"])
        for address in (0, 0x80000000):
            b.memory[0x500000] = struct.pack("<I", address)
            evidence = capture_crafting_callers(b, {"esp": 0x500000})
            self.assertEqual("invalid_return_address", evidence["stop_reason"])

    def test_caller_evidence_pairs_nested_threads_and_resumes_before_callback(self):
        b = Backend()
        for esp, caller in ((0x500000, 0x401111), (0x600000, 0x402222)):
            b.memory[esp] = struct.pack("<I", caller)
        b.add_hit("outbound_entry", registers={"esp": 0x500000, "ebp": 0})
        b.add_hit("outbound_entry", registers={"esp": 0x600000, "ebp": 0})
        b.add_hit("inbound_entry", thread=9)
        b.add_hit("outbound_complete")
        b.add_hit("inbound_complete", thread=9)
        b.add_hit("outbound_complete")
        records = []

        def callback(record):
            self.assertIn(len(b.continued), (4, 5, 6))
            records.append(record)

        with tempfile.TemporaryDirectory() as tmp:
            NativeCraftingTracer(b).trace(
                Path(tmp) / "trace.jsonl", max_messages=3,
                capture_callers=True, on_message=callback,
            )
        self.assertEqual([0x402222], records[0]["callers"]["return_addresses"])
        self.assertEqual("invalid_stack_pointer", records[1]["callers"]["stop_reason"])
        self.assertEqual([0x401111], records[2]["callers"]["return_addresses"])
        self.assertTrue(b.closed)

    def test_unknown_build_and_changed_signature_never_attach(self):
        for change in ("build", "signature"):
            b = Backend()
            if change == "build":
                b.executable_sha256 = "0" * 64
            else:
                rva, signature = CRAFTING_BREAKPOINTS["inbound_entry"]
                b.memory[b.base_address + rva] = b"x" * len(signature)
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(NativeVendorDialogCompatibilityError):
                    NativeCraftingTracer(b).trace(Path(tmp) / "trace.jsonl")
            self.assertFalse(b.attached)
            self.assertTrue(b.closed)

    def test_unpaired_or_foreign_completion_resumes_and_detaches(self):
        for pid in (77, 88):
            b = Backend()
            b.add_hit("inbound_complete", pid=pid)
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(NativeVendorDialogCaptureError):
                    NativeCraftingTracer(b).trace(Path(tmp) / "trace.jsonl")
            self.assertEqual(["inbound_complete"], b.continued)
            self.assertTrue(b.closed)

    def test_bad_name_and_vtable_fail_before_callback(self):
        for offset, value in ((0, 0), (0xE8, 0x300000), (0xEC, 8193)):
            b = Backend()
            raw = bytearray(b.memory[0x200000])
            struct.pack_into("<I", raw, offset, value)
            b.memory[0x200000] = bytes(raw)
            b.add_hit("inbound_entry")
            b.add_hit("inbound_complete")
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(NativeVendorDialogCaptureError):
                    NativeCraftingTracer(b).trace(Path(tmp) / "trace.jsonl")
            self.assertEqual(2, len(b.continued))
            self.assertTrue(b.closed)

    def test_output_collision_never_attaches(self):
        b = Backend()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            path.write_text("preserved")
            with self.assertRaises(FileExistsError):
                NativeCraftingTracer(b).trace(path)
            self.assertEqual("preserved", path.read_text())
        self.assertFalse(b.attached)
        self.assertTrue(b.closed)

    def test_callback_failure_closes_backend(self):
        b = Backend()
        b.add_hit("outbound_entry")
        b.add_hit("outbound_complete")

        def fail(record):
            raise RuntimeError("consumer failed")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "consumer failed"):
                NativeCraftingTracer(b).trace(Path(tmp) / "trace.jsonl", on_message=fail)
        self.assertTrue(b.closed)
        self.assertEqual(2, len(b.continued))

    def test_timeout_bounds_reject_nan_infinity_bool(self):
        for timeout in (True, float("nan"), float("inf"), 0, 301):
            b = Backend()
            with self.assertRaises(ValueError):
                NativeCraftingTracer(b).trace(Path("unused.jsonl"), timeout_seconds=timeout)
            self.assertTrue(b.closed)
            self.assertFalse(b.attached)


if __name__ == "__main__":
    unittest.main()
