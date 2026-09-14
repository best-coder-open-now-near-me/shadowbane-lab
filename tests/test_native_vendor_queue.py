import io
import json
import struct
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.client_observation.native_vendor_queue import read_native_vendor_queue


class Memory:
    base_address = 0x400000
    executable_name = "sb.exe"
    executable_sha256 = "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87"
    pointer_size = 4
    pid = 988
    process_creation_filetime_utc = 100

    def __init__(self):
        self.data = {}
        self.reads = {}
        self.change = None

    def put(self, address, fmt, *values):
        for offset, byte in enumerate(struct.pack(fmt, *values)):
            self.data[address + offset] = byte

    def read_block(self, address, size):
        self.reads[address, size] = self.reads.get((address, size), 0) + 1
        if self.change and self.change[:2] == (address, size) and self.reads[address, size] == 2:
            return self.change[2]
        return bytes(self.data.get(address + i, 0) for i in range(size))


ROOT, MANAGER, HUD, LIST = 0x100000, 0x110000, 0x120000, 0x130000
CONTROL, ENTRY = 0x140000, 0x150000
VENDOR = 0x1D0000


def fixture():
    m = Memory()
    for address, value in (
        (0x1AA7BFC, ROOT), (ROOT, 0x1574884), (ROOT + 0x64, 2),
        (ROOT + 0xA4, MANAGER), (MANAGER, 0x1571ADC), (MANAGER + 0x78, HUD),
        (HUD, 0x156A058), (HUD + 0x104, MANAGER), (LIST, 0x156ACF0),
        (LIST + 0x3BC, HUD), (CONTROL, 0x156AEBC), (CONTROL + 0x3BC, HUD),
        (CONTROL + 0x458, LIST), (CONTROL + 0x44C, ENTRY), (ENTRY, 0x1569560),
    ):
        m.put(address, "<I", value)
    m.put(ROOT + 0x20, "<I", 0x190000)
    m.put(0x190000, "<II", 0x190100, 0x190100)
    m.put(0x190100, "<III", 0x190000, 0x190000, HUD)
    m.put(MANAGER + 0xF0, "<II", 2229645, 8)
    m.put(MANAGER + 0xF8, "<II", 2229645, 8)
    m.put(MANAGER + 0x384, "<I", VENDOR)
    m.put(VENDOR, "<I", 0x1569518)
    m.put(VENDOR + 0x10, "<II", 2517204, 42)
    m.put(HUD + 0x54, "<III", 0x160000, 0x160004, 0x160010)
    m.put(0x160000, "<I", LIST)
    m.put(LIST + 0x408, "<III", 0x170000, 0x170004, 0x170010)
    m.put(0x170000, "<I", CONTROL)
    return m


class NativeVendorQueueTests(unittest.TestCase):
    def test_reads_only_rooted_menu_and_does_not_grant_command_permission(self):
        m = fixture()
        # Another correctly typed but disconnected manager is irrelevant.
        m.put(0x180000, "<I", 0x1571ADC)
        out = read_native_vendor_queue(m)
        self.assertEqual(MANAGER, out["manager_address"])
        self.assertEqual("empty", out["slots"][0]["state"])
        self.assertFalse(out["command_admitted"])
        self.assertFalse(any(address == 0x180000 for address, _ in m.reads))

    def test_reads_cooking_and_completed_identity_for_the_selected_vendor(self):
        for complete, expected in ((0, "cooking"), (1, "complete")):
            m = fixture()
            m.put(ENTRY + 0x10, "<II", 4294646291, 40)
            m.put(ENTRY + 0x40, "<IIII", 10151, 1, 600, 10)
            m.put(ENTRY + 0x50, "<d", 10.5)
            m.put(ENTRY + 0x58, "<BBBB", complete, 1, 1, 0)
            out = read_native_vendor_queue(m)
            self.assertEqual(expected, out["slots"][0]["state"])
            self.assertEqual(4294646291, out["slots"][0]["item"]["object_id"])
            self.assertEqual({"object_id": 2517204, "object_type": 42}, out["vendor"])

    def test_rejects_logout_detached_menu_or_broken_parent_links(self):
        for address, value in (
            (ROOT + 0x64, 0), (ROOT + 0xA4, 0), (MANAGER + 0x78, 0),
            (HUD + 0x104, MANAGER + 4), (LIST + 0x3BC, HUD + 4),
            (CONTROL + 0x3BC, HUD + 4), (CONTROL + 0x458, LIST + 4),
            (CONTROL, 0), (MANAGER + 0xF4, 42),
        ):
            m = fixture()
            m.put(address, "<I", value)
            with self.subTest(address=address), self.assertRaises(NativeVendorDialogCaptureError):
                read_native_vendor_queue(m)

    def test_detects_changes_in_root_ownership_payload_and_pointer_array(self):
        for address, size in (
            (0x1AA7BFC, 4), (ROOT + 0xA4, 4), (HUD + 0x104, 4),
            (0x170000, 4), (CONTROL + 0x44C, 4), (ENTRY + 0x10, 8),
        ):
            m = fixture()
            m.change = (address, size, b"\xff" * size)
            with self.subTest(address=address), self.assertRaisesRegex(
                NativeVendorDialogCaptureError, "changed"
            ):
                read_native_vendor_queue(m)

    def test_rejects_malformed_oversized_and_duplicate_vectors(self):
        for values in (
            (0x160000, 0x15FFFF, 0x160010),
            (0x160000, 0x160001, 0x160010),
            (0x160000, 0x161000, 0x161000),
            (0x160000, 0x160008, 0x160010),
        ):
            m = fixture()
            m.put(HUD + 0x54, "<III", *values)
            m.put(0x160004, "<I", LIST)
            with self.subTest(values=values), self.assertRaises(NativeVendorDialogCaptureError):
                read_native_vendor_queue(m)

    def test_rejects_menu_removed_from_active_stack_and_broken_list_cycles(self):
        for address, fmt, values in (
            (0x190000, "<II", (0x190000, 0x190000)),
            (0x190100, "<III", (0x190100, 0x190000, HUD)),
            (0x190100, "<III", (0x190000, 0x190004, HUD)),
            (0x190004, "<I", (0x190104,)),
        ):
            m = fixture()
            m.put(address, fmt, *values)
            with self.subTest(address=address), self.assertRaises(NativeVendorDialogCaptureError):
                read_native_vendor_queue(m)

    def test_services_are_not_free_crafting_slots(self):
        m = fixture()
        m.put(ENTRY, "<I", 0x1569500)
        with self.assertRaisesRegex(NativeVendorDialogCaptureError, "no qualified"):
            read_native_vendor_queue(m)

    def test_rejects_inconsistent_item_flags_and_nonfinite_timer(self):
        for field, fmt, values in (
            (0x10, "<II", (123, 42)), (0x10, "<II", (123, 40)),
            (0x58, "<BBBB", (0, 1, 0, 0)), (0x58, "<BBBB", (2, 0, 0, 0)),
            (0x50, "<d", (float("nan"),)), (0x50, "<d", (-1,)),
        ):
            m = fixture()
            m.put(ENTRY + field, fmt, *values)
            with self.subTest(field=field, values=values), self.assertRaises(
                NativeVendorDialogCaptureError
            ):
                read_native_vendor_queue(m)

    def test_requires_the_exact_build_and_explicit_process_lifetime(self):
        for field, value in (
            ("executable_sha256", "0" * 64), ("pointer_size", 8),
            ("process_creation_filetime_utc", None), ("pid", True),
        ):
            m = fixture()
            setattr(m, field, value)
            with self.subTest(field=field), self.assertRaises(NativeVendorDialogCompatibilityError):
                read_native_vendor_queue(m)


class VendorQueueCommandTests(unittest.TestCase):
    def test_cli_uses_explicit_process_and_closes_the_read_only_handle(self):
        from shadowbane_lab.cli import main
        from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory

        memory = fixture()
        memory.close = unittest.mock.Mock()
        output = io.StringIO()
        with patch.object(
            WindowsReadOnlyProcessMemory, "open_for_process", return_value=memory
        ) as opened, redirect_stdout(output):
            status = main(
                ["client", "observe-native-vendor-queue", "--process-id", "988", "--json"]
            )
        self.assertEqual(0, status)
        opened.assert_called_once_with("sb.exe", 988)
        memory.close.assert_called_once_with()
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["snapshot"]["command_admitted"])

    def test_failure_closes_handle_and_never_reports_an_empty_queue(self):
        from shadowbane_lab.cli_commands.client_inspection import observe_native_vendor_queue
        from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory

        memory = fixture()
        memory.put(MANAGER + 0x78, "<I", 0)
        memory.close = unittest.mock.Mock()
        output = io.StringIO()
        with patch.object(
            WindowsReadOnlyProcessMemory, "open_for_process", return_value=memory
        ), redirect_stdout(output):
            status = observe_native_vendor_queue(988, as_json=True)
        self.assertNotEqual(0, status)
        memory.close.assert_called_once_with()
        self.assertFalse(json.loads(output.getvalue())["ok"])


CREATION, TEMPLATE = 0x1A0000, 0x1B0000


def add_recipe(memory):
    memory.put(0x190004, "<I", 0x190200)
    memory.put(0x190100, "<III", 0x190200, 0x190000, HUD)
    memory.put(0x190200, "<III", 0x190000, 0x190100, CREATION)
    for offset, value in (
        (0, 0x156BF7C), (0x3B8, MANAGER), (0x3C0, 2517204), (0x3C4, 42),
        (0x400, 3362971591), (0x404, 1), (0x408, TEMPLATE),
        (0x40C, 3362971591), (0x434, 3362971591), (0x47C, 12), (0x4D4, 1),
    ):
        memory.put(CREATION + offset, "<I", value)
    memory.put(TEMPLATE, "<I", 0x1542748)
    memory.put(TEMPLATE + 0x10, "<II", 26990, 0)
    return memory


class VendorRecipeBindingTests(unittest.TestCase):
    def test_binds_current_recipe_and_vendor_to_the_same_queue_snapshot(self):
        out = read_native_vendor_queue(add_recipe(fixture()))
        self.assertEqual(4, out["schema_version"])
        recipe = out["creation_recipe"]
        self.assertEqual({"object_id": 2517204, "object_type": 42}, recipe["vendor"])
        self.assertEqual({"object_id": 26990, "object_type": 0}, recipe["template"])
        self.assertTrue(recipe["qualified_random_scepter"])
        self.assertFalse(out["command_admitted"])

    def test_quantity_one_multiple_slot_recipe_is_qualified(self):
        m = add_recipe(fixture())
        m.put(CREATION + 0x3D8, "<I", 1)
        recipe = read_native_vendor_queue(m)["creation_recipe"]
        self.assertTrue(recipe["qualified_random_scepter"])
        self.assertTrue(recipe["multiple_slots"])

    def test_absent_or_unselected_recipe_does_not_invent_readiness(self):
        self.assertIsNone(read_native_vendor_queue(fixture())["creation_recipe"])
        m = add_recipe(fixture())
        m.put(CREATION + 0x408, "<I", 0)
        recipe = read_native_vendor_queue(m)["creation_recipe"]
        self.assertIsNone(recipe["template"])
        self.assertFalse(recipe["qualified_random_scepter"])

    def test_different_item_modifiers_count_or_slot_mode_are_not_qualified(self):
        for address, value in (
            (TEMPLATE + 0x10, 123), (CREATION + 0x400, 0), (CREATION + 0x404, 0),
            (CREATION + 0x40C, 0), (CREATION + 0x434, 0),
            (CREATION + 0x47C, 13), (CREATION + 0x4D4, 2),
        ):
            m = add_recipe(fixture())
            m.put(address, "<I", value)
            with self.subTest(address=address):
                self.assertFalse(
                    read_native_vendor_queue(m)["creation_recipe"]["qualified_random_scepter"]
                )

    def test_rejects_detached_recipe_owner_or_wrong_native_identity(self):
        for address, value in (
            (CREATION + 0x3B8, MANAGER + 4), (CREATION + 0x3C0, 0),
            (CREATION + 0x3C4, 40), (CREATION + 0x3D8, 2),
            (TEMPLATE, 0x1569560), (TEMPLATE + 0x14, 40),
        ):
            m = add_recipe(fixture())
            m.put(address, "<I", value)
            with self.subTest(address=address), self.assertRaises(NativeVendorDialogCaptureError):
                read_native_vendor_queue(m)

    def test_detects_changes_to_selection_vendor_and_active_hud_membership(self):
        for address, size in (
            (CREATION + 0x408, 4), (TEMPLATE + 0x10, 8),
            (CREATION + 0x3C0, 8), (CREATION + 0x40C, 4),
            (0x190200, 12),
        ):
            m = add_recipe(fixture())
            m.change = (address, size, b"\xff" * size)
            with self.subTest(address=address), self.assertRaisesRegex(
                NativeVendorDialogCaptureError, "changed"
            ):
                read_native_vendor_queue(m)

    def test_rejects_multiple_active_recipe_windows(self):
        m = add_recipe(fixture())
        m.put(0x190004, "<I", 0x190300)
        m.put(0x190200, "<III", 0x190300, 0x190100, CREATION)
        m.put(0x190300, "<III", 0x190000, 0x190200, 0x1C0000)
        m.put(0x1C0000, "<I", 0x156BF7C)
        with self.assertRaisesRegex(NativeVendorDialogCaptureError, "ambiguous"):
            read_native_vendor_queue(m)


class SelectedVendorOwnershipTests(unittest.TestCase):
    def test_vendor_remains_identified_without_recipe_window(self):
        out = read_native_vendor_queue(fixture())
        self.assertIsNone(out["creation_recipe"])
        self.assertEqual(2517204, out["vendor"]["object_id"])
        self.assertEqual(VENDOR, out["selected_vendor_entry_address"])
        self.assertFalse(out["command_admitted"])

    def test_rejects_missing_foreign_or_mixed_vendor_selection(self):
        for address, value in (
            (MANAGER + 0x384, 0), (VENDOR, 0x1569560), (VENDOR + 0x10, 0),
            (VENDOR + 0x14, 40), (MANAGER + 0xD8, 1),
            (MANAGER + 0xF8, 2229646), (MANAGER + 0xFC, 42),
            (CREATION + 0x3C0, 2517205),
        ):
            m = add_recipe(fixture())
            m.put(address, "<I", value)
            with self.subTest(address=address), self.assertRaises(NativeVendorDialogCaptureError):
                read_native_vendor_queue(m)

    def test_rejects_vendor_or_building_changes_during_observation(self):
        for address, size in (
            (MANAGER + 0x384, 4), (VENDOR, 4), (VENDOR + 0x10, 8),
            (MANAGER + 0xF8, 8), (MANAGER + 0xD8, 4),
        ):
            m = fixture()
            m.change = (address, size, b"\xff" * size)
            with self.subTest(address=address), self.assertRaisesRegex(
                NativeVendorDialogCaptureError, "changed"
            ):
                read_native_vendor_queue(m)
