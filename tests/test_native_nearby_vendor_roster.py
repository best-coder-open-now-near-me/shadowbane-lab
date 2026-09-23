import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from shadowbane_lab.client_observation.native_nearby_vendor_roster import (
    read_native_nearby_vendor_roster,
)
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from tests.test_native_vendor_queue import HUD, MANAGER, ROOT, fixture
from tests.test_native_vendor_roster import text

HEADER, NODE, SECOND = 0x4000000, 0x4000100, 0x4000200
BLOCK, BLOCK2, HIRELING, HIRELING2 = 0x4100000, 0x4101000, 0x4200000, 0x4201000
VHEAD, VNODE, VHEAD2, VNODE2 = 0x4300000, 0x4300100, 0x4301000, 0x4301100


def one_tree(m, field, header, node, key, payload):
    m.put(field, "<II", header, 1)
    m.put(header + 4, "<III", node, node, node)
    m.put(node + 4, "<6I", header, 0, 0, *key, payload)


def nearby_fixture():
    m = fixture()
    for address, value in (
        (ROOT + 0xD4, MANAGER), (MANAGER, 0x1571BCC),
        (MANAGER + 0x44, 2), (MANAGER + 0x4C, HUD),
        (HUD, 0x1566234), (BLOCK, 0x157A7A8), (BLOCK2, 0x157A7A8),
        (HIRELING, 0x157A7BC), (HIRELING2, 0x157A7BC),
    ):
        m.put(address, "<I", value)
    one_tree(m, MANAGER + 0x74, HEADER, NODE, (202, 8), BLOCK)
    m.put(MANAGER + 0x78, "<I", 2)
    m.put(HEADER + 8, "<I", SECOND)
    m.put(NODE + 8, "<I", SECOND)
    m.put(SECOND + 4, "<6I", NODE, 0, 0, 101, 8, BLOCK2)
    m.put(BLOCK + 0x20, "<II", 202, 8)
    m.put(BLOCK2 + 0x20, "<II", 101, 8)
    one_tree(m, BLOCK + 0x38, VHEAD, VNODE, (401, 42), HIRELING)
    one_tree(m, BLOCK2 + 0x38, VHEAD2, VNODE2, (402, 42), HIRELING2)
    for field, buf, value in (
        (BLOCK + 8, 0x4400000, "Sages"),
        (BLOCK2 + 8, 0x4401000, "Armorers"),
        (HIRELING + 4, 0x4402000, "Same name"),
        (HIRELING2 + 4, 0x4403000, "Same name"),
    ):
        text(m, field, buf, value)
    return m


class NearbyVendorRosterTests(unittest.TestCase):
    def test_groups_multiple_buildings_by_native_identity_without_selected_vendor(self):
        m = nearby_fixture()
        result = read_native_nearby_vendor_roster(m)
        self.assertEqual([101, 202], [b["building"]["object_id"] for b in result["buildings"]])
        self.assertEqual([402, 401], [
            b["vendors"][0]["vendor"]["object_id"] for b in result["buildings"]
        ])
        self.assertEqual("Armorers", result["buildings"][0]["display_name"])
        self.assertEqual("Same name", result["buildings"][1]["vendors"][0]["display_name"])
        self.assertNotIn((ROOT + 0xA4, 4), m.reads)
        for flag in ("roster_complete", "town_membership_verified", "server_response_verified",
                     "management_permission_verified", "command_admitted"):
            self.assertFalse(result[flag])
        self.assertNotIn("pointer", json.dumps(result))
        self.assertNotIn("address", json.dumps(result))

    def test_closed_pending_detached_and_wrong_types_are_unavailable(self):
        cases = (
            (ROOT + 0x64, 0), (ROOT + 0xD4, 0), (MANAGER, 0x1571ADC),
            (MANAGER + 0x44, 0), (MANAGER + 0x4C, 0),
            (HUD, 0x156A058), (HUD + 0x104, MANAGER + 4),
            (HUD + 0x568, 0x10000), (0x190100 + 8, HUD + 4),
            (BLOCK, 0), (HIRELING, 0), (BLOCK + 0x20, 999),
        )
        for address, value in cases:
            with self.subTest(address=address):
                m = nearby_fixture()
                m.put(address, "<I", value)
                with self.assertRaises(NativeVendorDialogCaptureError):
                    read_native_nearby_vendor_roster(m)

    def test_corrupt_nested_trees_and_identities_are_rejected(self):
        cases = (
            (MANAGER + 0x78, 513), (MANAGER + 0x78, 1), (MANAGER + 0x78, 3),
            (HEADER + 4, 0), (HEADER + 8, NODE), (HEADER + 12, SECOND),
            (NODE + 4, 0), (NODE + 8, NODE), (NODE + 12, SECOND),
            (SECOND + 4, HEADER), (SECOND + 0x10, 202),
            (SECOND + 0x18, BLOCK), (NODE + 0x10, 0), (NODE + 0x14, 42),
            (BLOCK + 0x3C, 257), (VNODE + 0x14, 8),
            (VNODE2 + 0x10, 401), (VNODE2 + 0x18, HIRELING), (VNODE + 4, HEADER),
            (VNODE + 8, VNODE), (VHEAD + 12, HEADER),
            (VNODE + 0x18, 0), (MANAGER + 0x74, 0x10001),
        )
        for address, value in cases:
            with self.subTest(address=address):
                m = nearby_fixture()
                m.put(address, "<I", value)
                with self.assertRaises(NativeVendorDialogCaptureError):
                    read_native_nearby_vendor_roster(m)

    def test_empty_cache_is_not_a_verified_zero_building_response(self):
        m = nearby_fixture()
        m.put(MANAGER + 0x78, "<I", 0)
        m.put(HEADER + 4, "<III", 0, HEADER, HEADER)
        with self.assertRaisesRegex(
            NativeVendorDialogCaptureError, "server response is unverified"
        ):
            read_native_nearby_vendor_roster(m)

    def test_buildings_without_hirelings_are_retained(self):
        m = nearby_fixture()
        m.put(BLOCK + 0x3C, "<I", 0)
        m.put(VHEAD + 4, "<III", 0, VHEAD, VHEAD)
        self.assertEqual([], read_native_nearby_vendor_roster(m)["buildings"][1]["vendors"])
        m = nearby_fixture()
        m.put(BLOCK + 0x3C, "<I", 0)
        with self.assertRaisesRegex(NativeVendorDialogCaptureError, "invalid empty"):
            read_native_nearby_vendor_roster(m)

    def test_changes_to_roots_nodes_text_and_pending_state_are_rejected(self):
        for address, size in (
            (ROOT + 0xD4, 4), (MANAGER + 0x74, 8), (NODE + 4, 24),
            (BLOCK + 0x20, 8), (VNODE + 4, 24), (0x4402000, 18),
            (HUD + 0x568, 4),
        ):
            with self.subTest(address=address):
                m = nearby_fixture()
                m.change = (address, size, b"\xff" * size)
                with self.assertRaises(NativeVendorDialogCaptureError):
                    read_native_nearby_vendor_roster(m)

    def test_build_guard_precedes_all_reads(self):
        for attribute, value in (("executable_sha256", "0" * 64),
                                 ("executable_name", "other.exe"), ("pointer_size", 8)):
            m = nearby_fixture()
            setattr(m, attribute, value)
            with self.subTest(attribute=attribute):
                with self.assertRaises(NativeVendorDialogCompatibilityError):
                    read_native_nearby_vendor_roster(m)
                self.assertFalse(m.reads)

    def test_cli_json_text_errors_and_handle_lifetime(self):
        from shadowbane_lab.cli import main
        from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory

        for fail, as_json in ((False, True), (True, True), (False, False)):
            m = nearby_fixture()
            m.close = Mock()
            if fail:
                m.put(MANAGER + 0x44, "<I", 0)
            output = io.StringIO()
            args = ["client", "observe-native-nearby-vendors", "--process-id", "988"]
            if as_json:
                args.append("--json")
            with patch.object(WindowsReadOnlyProcessMemory, "open_for_process",
                              return_value=m) as opened, redirect_stdout(output):
                code = main(args)
            opened.assert_called_once_with("sb.exe", 988)
            m.close.assert_called_once_with()
            self.assertEqual(2 if fail else 0, code)
            if as_json:
                self.assertEqual(not fail, json.loads(output.getvalue())["ok"])
            else:
                self.assertIn("Armorers: 1 hirelings", output.getvalue())
                self.assertIn("town coverage", output.getvalue())
