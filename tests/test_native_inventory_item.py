import struct
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.client_observation.native_crafting import NativeCraftingTracer
from shadowbane_lab.client_observation.native_inventory_item import (
    INSTANCE_INFO_VTABLE_RVA,
    decode_inventory_instance,
)
from shadowbane_lab.client_observation.native_vendor_dialog import NativeVendorDialogCaptureError
from tests.test_native_crafting import Backend


def deposit_backend():
    b = Backend()
    message = bytearray(b.memory[0x200000])
    struct.pack_into("<I", message, 0x70, 10)
    struct.pack_into("<I", message, 0x100, 0x300000)
    message[0x11C] = 0
    b.memory[0x200000] = bytes(message)
    item = bytearray(0xF8)
    for offset, value in {
        0: b.base_address + INSTANCE_INFO_VTABLE_RVA,
        0x10: 26990, 0x14: 0, 0x18: 0xFFFF0011, 0x1C: 40,
        0x70: 151, 0x74: 251, 0xF4: 0,
        0xB4: 0x400000, 0xB8: 0x400008, 0xBC: 0x400010,
        0xD4: 0x500000, 0xD8: 0x500000, 0xDC: 0x500080,
    }.items():
        struct.pack_into("<I", item, offset, value)
    item[8] = item[9] = 1
    struct.pack_into("<ff", item, 0x60, 60, 59)
    b.memory[0x300000] = bytes(item)
    b.memory[0x400000] = struct.pack("<II", 0x600000, 0x600050)
    b.memory[0x600000] = struct.pack("<III", 123, 1, 0)
    b.memory[0x600050] = struct.pack("<III", 456, 2, 1)
    return b


class NativeInventoryItemTests(unittest.TestCase):
    def test_deposit_pairs_real_identity_and_effects_after_resume(self):
        b = deposit_backend()
        b.add_hit("inbound_entry")
        b.add_hit("inbound_complete")
        records = []

        def receive(record):
            self.assertEqual(2, len(b.continued))
            records.append(record)

        with tempfile.TemporaryDirectory() as tmp:
            NativeCraftingTracer(b).trace(
                Path(tmp) / "trace.jsonl", max_messages=1, on_message=receive
            )
        message = records[0]["message"]
        item = message["deposited_item"]
        self.assertEqual({"object_id": 26990, "object_type": 0}, item["template"])
        self.assertEqual({"object_id": 0xFFFF0011, "object_type": 40}, item["item"])
        self.assertEqual([123, 456], [effect["token"] for effect in item["effects"]])
        self.assertEqual(9000, message["strongbox_gold"])
        self.assertEqual(0, item["quantity_raw"])
        self.assertTrue(b.closed)

    def test_invalid_effect_bounds_vtable_and_item_identity_fail(self):
        for offset, value in (
            (0, 0), (0x14, 40), (0x1C, 0), (0x18, 0),
            (0xB8, 0x400009), (0xB8, 0x400200), (0xB4, 0),
        ):
            b = deposit_backend()
            raw = bytearray(b.memory[0x300000])
            struct.pack_into("<I", raw, offset, value)
            b.memory[0x300000] = bytes(raw)
            with self.subTest(offset=offset, value=value):
                with self.assertRaises(NativeVendorDialogCaptureError):
                    decode_inventory_instance(b, 0x300000)

    def test_absent_item_data_does_not_read_stale_effect_pointers(self):
        b = deposit_backend()
        raw = bytearray(b.memory[0x300000])
        raw[9] = 0
        struct.pack_into("<III", raw, 0xB4, 1, 2, 3)
        b.memory[0x300000] = bytes(raw)
        item = decode_inventory_instance(b, 0x300000)
        self.assertFalse(item["has_item_data"])
        self.assertNotIn("effects", item)

    def test_short_effect_read_resumes_and_detaches_without_callback(self):
        b = deposit_backend()
        b.memory[0x600000] = b""
        b.add_hit("inbound_entry")
        b.add_hit("inbound_complete")
        records = []
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(NativeVendorDialogCaptureError):
                NativeCraftingTracer(b).trace(Path(tmp) / "trace.jsonl", on_message=records.append)
        self.assertEqual([], records)
        self.assertEqual(2, len(b.continued))
        self.assertTrue(b.closed)
