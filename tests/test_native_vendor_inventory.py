import unittest

from shadowbane_lab.client_observation.native_inventory_item import INSTANCE_INFO_BYTES
from shadowbane_lab.client_observation.native_vendor_dialog import NativeVendorDialogCaptureError
from shadowbane_lab.client_observation.native_vendor_queue import read_native_vendor_queue
from tests.test_native_vendor_queue import MANAGER, Memory, fixture

HUD, LIST, CONTROL, ENTRY = 0x200000, 0x210000, 0x220000, 0x230000
INSTANCE, ITEM, VECTOR, EFFECT = 0x240000, 0x250000, 0x260000, 0x270000
ITEM_ID = 4294925624


def inventory_fixture() -> Memory:
    m = fixture()
    m.put(MANAGER + 0x7C, "<I", HUD)
    m.put(0x190004, "<I", 0x190200)
    m.put(0x190100, "<I", 0x190200)
    m.put(0x190200, "<III", 0x190000, 0x190100, HUD)
    for address, value in (
        (HUD, 0x156C64C), (HUD + 0x104, MANAGER), (HUD + 0x3F4, MANAGER),
        (HUD + 0x3F0, LIST), (LIST, 0x156ACF0), (LIST + 0x3BC, HUD),
        (CONTROL, 0x156AEBC), (CONTROL + 0x3BC, HUD), (CONTROL + 0x458, LIST),
        (CONTROL + 0x44C, ENTRY), (ENTRY, 0x15696C8), (ENTRY + 0x20, INSTANCE),
        (ENTRY + 0x24, ITEM), (INSTANCE, 0x154BB68), (ITEM, 0x1542748),
    ):
        m.put(address, "<I", value)
    m.put(HUD + 0x54, "<III", VECTOR, VECTOR + 4, VECTOR + 4)
    m.put(VECTOR, "<I", LIST)
    m.put(LIST + 0x408, "<III", VECTOR + 0x100, VECTOR + 0x104, VECTOR + 0x110)
    m.put(VECTOR + 0x100, "<I", CONTROL)
    m.put(ENTRY + 0x10, "<II", ITEM_ID, 40)
    m.put(INSTANCE + 0x10, "<IIII", 26990, 0, ITEM_ID, 40)
    m.put(ITEM + 0x10, "<IIII", 26990, 0, ITEM_ID, 40)
    m.put(INSTANCE + 8, "<BBBB", 1, 1, 0, 0)
    m.put(INSTANCE + 0x60, "<ff", 30, 30)
    m.put(INSTANCE + 0x70, "<II", 151, 7151)
    m.put(INSTANCE + 0xB4, "<III", VECTOR + 0x200, VECTOR + 0x204, VECTOR + 0x208)
    m.put(VECTOR + 0x200, "<I", EFFECT)
    m.put(EFFECT, "<III", 421339000, 0, 1)
    return m


class NativeVendorInventoryTests(unittest.TestCase):
    def test_matches_owned_entry_instance_native_item_and_effects(self):
        out = read_native_vendor_queue(inventory_fixture())
        inventory = out["inventory"]
        self.assertEqual(2517204, out["vendor"]["object_id"])
        self.assertEqual(ITEM_ID, inventory["items"][0]["item"]["object_id"])
        self.assertEqual(26990, inventory["items"][0]["template"]["object_id"])
        self.assertEqual(421339000, inventory["items"][0]["effects"][0]["token"])
        self.assertEqual(0, inventory["items"][0]["quantity_raw"])
        self.assertEqual("displayed_entries", inventory["scope"])
        self.assertFalse(inventory["complete_inventory"])
        self.assertIsNone(inventory["capacity"])
        self.assertFalse(out["command_admitted"])

    def test_closed_inventory_is_unavailable_not_empty(self):
        self.assertIsNone(read_native_vendor_queue(fixture())["inventory"])
        m = fixture()
        m.put(MANAGER + 0x7C, "<I", HUD)
        self.assertIsNone(read_native_vendor_queue(m)["inventory"])
        self.assertFalse(any(address == HUD for address, _ in m.reads))

    def test_empty_displayed_list_does_not_prove_empty_inventory_or_capacity(self):
        m = inventory_fixture()
        m.put(LIST + 0x408, "<III", 0, 0, 0)
        inventory = read_native_vendor_queue(m)["inventory"]
        self.assertEqual([], inventory["items"])
        self.assertFalse(inventory["complete_inventory"])
        self.assertIsNone(inventory["capacity"])

    def test_rejects_detached_or_wrongly_typed_ownership_links(self):
        for address, value in (
            (HUD, 0), (HUD + 0x104, MANAGER + 4), (HUD + 0x3F4, MANAGER + 4),
            (HUD + 0x3F0, LIST + 4), (VECTOR, LIST + 4), (LIST, 0),
            (LIST + 0x3BC, HUD + 4), (CONTROL, 0), (CONTROL + 0x3BC, HUD + 4),
            (CONTROL + 0x458, LIST + 4), (CONTROL + 0x44C, 0), (ENTRY, 0),
            (ENTRY + 0x20, 0), (ENTRY + 0x24, 0), (INSTANCE, 0), (ITEM, 0),
        ):
            m = inventory_fixture()
            m.put(address, "<I", value)
            with self.subTest(address=address), self.assertRaises(NativeVendorDialogCaptureError):
                read_native_vendor_queue(m)

    def test_rejects_item_and_template_identity_disagreement(self):
        for address, value in (
            (ENTRY + 0x10, 0), (ENTRY + 0x14, 42), (INSTANCE + 0x18, ITEM_ID - 1),
            (ITEM + 0x18, ITEM_ID - 1), (ITEM + 0x1C, 42),
            (ITEM + 0x10, 26991), (ITEM + 0x14, 40),
        ):
            m = inventory_fixture()
            m.put(address, "<I", value)
            with self.subTest(address=address), self.assertRaises(NativeVendorDialogCaptureError):
                read_native_vendor_queue(m)

    def test_duplicate_control_entry_or_item_is_rejected(self):
        for variant in ("control", "entry", "item"):
            m = inventory_fixture()
            m.put(LIST + 0x40C, "<I", VECTOR + 0x108)
            m.put(VECTOR + 0x104, "<I", CONTROL if variant == "control" else CONTROL + 0x1000)
            if variant != "control":
                for offset in (0, 0x3BC, 0x458, 0x44C):
                    m.put(CONTROL + 0x1000 + offset, "<4s", m.read_block(CONTROL + offset, 4))
            if variant == "item":
                m.put(CONTROL + 0x1000 + 0x44C, "<I", ENTRY + 0x1000)
                m.put(ENTRY + 0x1000, "<40s", m.read_block(ENTRY, 40))
            with self.subTest(variant=variant), self.assertRaises(NativeVendorDialogCaptureError):
                read_native_vendor_queue(m)

    def test_mutation_anywhere_in_inventory_chain_or_effects_rejects_snapshot(self):
        for address, size in (
            (MANAGER + 0x7C, 4), (HUD + 0x3F4, 4), (VECTOR, 4),
            (VECTOR + 0x100, 4), (ENTRY + 0x20, 4),
            (INSTANCE, INSTANCE_INFO_BYTES), (ITEM + 0x10, 16),
            (VECTOR + 0x200, 4), (EFFECT, 12),
        ):
            m = inventory_fixture()
            m.change = (address, size, b"\\xff" * size)
            with self.subTest(address=address), self.assertRaisesRegex(
                NativeVendorDialogCaptureError, "changed"
            ):
                read_native_vendor_queue(m)

    def test_unsettled_queue_to_inventory_transition_is_not_confirmed(self):
        from tests.test_native_vendor_queue import ENTRY as PRODUCTION_ENTRY

        m = inventory_fixture()
        m.put(PRODUCTION_ENTRY + 0x10, "<II", ITEM_ID, 40)
        m.put(PRODUCTION_ENTRY + 0x58, "<BBBB", 1, 1, 1, 0)
        with self.assertRaisesRegex(
            NativeVendorDialogCaptureError, "both production and inventory"
        ):
            read_native_vendor_queue(m)
