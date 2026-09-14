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
            0x78: 5,
            0x7C: 100,
            0x80: 42,
            0x84: 200,
            0xC0: 6,
            0xC4: 0xFFFFFFFF,
            0xCC: 1234,
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

    def add_hit(self, role, *, thread=8, pid=77):
        self.hits.append(
            NativeVendorDialogDebugHit(
                role,
                pid,
                thread,
                self.base_address + CRAFTING_BREAKPOINTS[role][0],
                {"ecx": 0x200000},
            )
        )


class NativeCraftingTests(unittest.TestCase):
    def test_native_result_references_and_hidden_balance(self):
        b = Backend()
        result = decode_crafting_object(b, 0x200000)
        self.assertEqual(200, result["vendor"]["object_id"])
        self.assertEqual(0xFFFFFFFF, result["roll"]["item"]["object_id"])
        self.assertEqual(1234, result["roll"]["template"]["object_id"])
        self.assertEqual(9000, result["strongbox_gold"])
        raw = bytearray(b.memory[0x200000])
        raw[0x11C] = 0
        b.memory[0x200000] = bytes(raw)
        self.assertNotIn("strongbox_gold", decode_crafting_object(b, 0x200000))

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
        self.assertEqual("session_end", journal[-1]["record_type"])
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
