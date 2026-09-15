import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.client_observation.native_vendor_roster import read_native_vendor_roster
from tests.test_native_vendor_queue import CONTROL, ENTRY, HUD, LIST, MANAGER, ROOT, fixture

SECOND_CONTROL, SECOND_ENTRY = 0x210000, 0x220000


def text(memory, field, buffer, value):
    raw = value.encode("utf-16-le")
    memory.put(field + 4, "<III", buffer, buffer + len(raw), buffer + len(raw) + 16)
    memory.put(buffer, f"<{len(raw)}s", raw)


def roster_fixture():
    m = fixture()
    # No vendor selection, production entries, recipe or Inventory is required.
    m.put(MANAGER + 0x384, "<I", 0)
    m.put(LIST + 0x408, "<III", 0x170000, 0x170008, 0x170010)
    m.put(0x170000, "<II", CONTROL, SECOND_CONTROL)
    for control, entry, key, name, service, buf in (
        (CONTROL, ENTRY, 101, "A sage", "Irekei Sage", 0x310000),
        (SECOND_CONTROL, SECOND_ENTRY, 102, "Other sage", "Lizardman Sage", 0x330000),
    ):
        for address, value in (
            (control, 0x156AEBC), (control + 0x3BC, HUD),
            (control + 0x458, LIST), (control + 0x44C, entry), (entry, 0x1569518),
        ):
            m.put(address, "<I", value)
        m.put(entry + 0x10, "<II", key, 42)
        text(m, entry + 0x30, buf, name)
        text(m, entry + 0x48, buf + 0x1000, service)
    text(m, MANAGER + 0x15C, 0x350000, "Magic shop")
    text(m, MANAGER + 0x174, 0x360000, "Owner label")
    return m


class NativeVendorRosterTests(unittest.TestCase):
    def test_reads_owned_building_and_all_visible_hirelings_without_selection(self):
        m = roster_fixture()
        result = read_native_vendor_roster(m)
        self.assertEqual("Magic shop", result["building_name"])
        self.assertEqual("Owner label", result["owner_label"])
        self.assertEqual({"object_id": 2229645, "object_type": 8}, result["building"])
        self.assertEqual([101, 102], [r["vendor"]["object_id"] for r in result["vendors"]])
        self.assertEqual(["Irekei Sage", "Lizardman Sage"],
                         [r["service_label"] for r in result["vendors"]])
        for flag in ("roster_complete", "town_membership_verified",
                     "management_permission_verified", "command_admitted"):
            self.assertFalse(result[flag])
        self.assertNotIn((MANAGER + 0x384, 4), m.reads)

    def test_unknown_service_row_is_not_misidentified_as_a_hireling(self):
        m = roster_fixture()
        m.put(SECOND_ENTRY, "<I", 0x1569560)
        self.assertEqual(1, len(read_native_vendor_roster(m)["vendors"]))

    def test_detached_or_changing_owner_and_broken_membership_are_rejected(self):
        for address, value in (
            (ROOT + 0x64, 0), (MANAGER + 0xD8, 1),
            (HUD + 0x104, MANAGER + 4), (CONTROL + 0x3BC, HUD + 4),
            (CONTROL + 0x458, LIST + 4), (LIST + 0x3BC, HUD + 4),
            (MANAGER + 0xF8, 999), (SECOND_ENTRY + 0x10, 101),
            (SECOND_ENTRY + 0x14, 40), (ENTRY + 0x10, 0),
        ):
            with self.subTest(address=address):
                m = roster_fixture()
                m.put(address, "<I", value)
                with self.assertRaises(NativeVendorDialogCaptureError):
                    read_native_vendor_roster(m)

    def test_unicode_labels_and_changes_during_copy(self):
        m = roster_fixture()
        text(m, ENTRY + 0x30, 0x310000, "Ságe \U0001f409")
        self.assertEqual("Ságe \U0001f409",
                         read_native_vendor_roster(m)["vendors"][0]["display_name"])
        for address, size in ((0x310000, 12), (MANAGER + 0xF0, 8), (0x170000, 8)):
            m = roster_fixture()
            m.change = (address, size, bytes(size))
            with self.subTest(address=address), self.assertRaises(NativeVendorDialogCaptureError):
                read_native_vendor_roster(m)

    def test_malformed_text_and_empty_roster_are_not_success(self):
        for mode in ("length", "encoding", "empty", "control"):
            m = roster_fixture()
            if mode == "length":
                m.put(ENTRY + 0x38, "<I", 0x310000 + 1026)
                m.put(ENTRY + 0x3C, "<I", 0x310000 + 2048)
            elif mode == "encoding":
                m.put(ENTRY + 0x38, "<I", 0x310002)
                m.put(0x310000, "<H", 0xD800)
            elif mode == "control":
                text(m, ENTRY + 0x30, 0x310000, "bad\x00name")
            else:
                m.put(ENTRY, "<I", 0x1569560)
                m.put(SECOND_ENTRY, "<I", 0x1569560)
            with self.subTest(mode=mode), self.assertRaises(NativeVendorDialogCaptureError):
                read_native_vendor_roster(m)

    def test_wrong_build_fails_before_reading_memory(self):
        m = roster_fixture()
        m.executable_sha256 = "0" * 64
        with self.assertRaises(NativeVendorDialogCompatibilityError):
            read_native_vendor_roster(m)
        self.assertEqual({}, m.reads)

    def test_cli_closes_handle_on_success_and_failure(self):
        from shadowbane_lab.cli import main
        from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
        for fail in (False, True):
            m = roster_fixture()
            m.close = Mock()
            if fail:
                m.put(MANAGER + 0x78, "<I", 0)
            output = io.StringIO()
            with patch.object(WindowsReadOnlyProcessMemory, "open_for_process",
                              return_value=m) as opened, redirect_stdout(output):
                status = main(["client", "observe-native-vendor-roster",
                               "--process-id", "988", "--json"])
            opened.assert_called_once_with("sb.exe", 988)
            m.close.assert_called_once_with()
            self.assertEqual(not fail, json.loads(output.getvalue())["ok"])
            self.assertEqual(not fail, status == 0)
