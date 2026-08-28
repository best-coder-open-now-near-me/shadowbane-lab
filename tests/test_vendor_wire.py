import json
import unittest
from pathlib import Path

from shadowbane_lab.client_observation.vendor_wire import (
    VendorDialogMenu,
    VendorDialogRequest,
    VendorWireFormatError,
    VendorWireOpcode,
    parse_vendor_dialog_wire,
    vendor_wire_opcode,
)

FIXTURE = Path(__file__).parent / "fixtures" / "vendor_wire" / "pelt-vendor-dialog.json"


class VendorWireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_decodes_sanitized_live_request(self) -> None:
        payload = bytes.fromhex(self.fixture["request_plaintext_hex"])

        message = parse_vendor_dialog_wire(payload)

        self.assertIsInstance(message, VendorDialogRequest)
        assert isinstance(message, VendorDialogRequest)
        self.assertEqual(1, message.header.message_type)
        self.assertEqual("ENGLISH", message.header.language)
        self.assertEqual(42, message.header.vendor.object_type)
        self.assertEqual(42047, message.header.vendor.object_id)
        self.assertEqual(0x6A022646, message.header.message_values[2])
        self.assertEqual(b"\0" * 6, message.trailing_bytes)

    def test_decodes_sanitized_live_menu_into_semantic_options(self) -> None:
        payload = bytes.fromhex(self.fixture["reply_plaintext_hex"])
        expected = self.fixture["expected"]

        message = parse_vendor_dialog_wire(payload)

        self.assertIsInstance(message, VendorDialogMenu)
        assert isinstance(message, VendorDialogMenu)
        self.assertEqual(expected["vendor_object_type"], message.header.vendor.object_type)
        self.assertEqual(expected["vendor_object_id"], message.header.vendor.object_id)
        self.assertEqual(expected["object_token"], message.header.object_token)
        self.assertEqual(expected["dialog_resource"], message.dialog_resource)
        self.assertEqual(expected["dialog_type"], message.dialog_type)
        self.assertEqual(expected["intro"], message.intro)
        self.assertEqual(expected["heading"], message.heading)
        self.assertEqual(expected["menu_type"], message.menu_type)
        self.assertEqual(expected["options"], [option.to_dict() for option in message.options])
        self.assertEqual(64, len(message.payload_sha256))

    def test_classifies_vendor_family_without_misreading_load_character(self) -> None:
        self.assertIs(VendorWireOpcode.DIALOG, vendor_wire_opcode(bytes.fromhex("98acd594")))
        self.assertIs(VendorWireOpcode.BUY_WINDOW, vendor_wire_opcode(bytes.fromhex("682dab4d")))
        self.assertIs(VendorWireOpcode.SELL_WINDOW, vendor_wire_opcode(bytes.fromhex("267dab90")))
        self.assertIsNone(vendor_wire_opcode(bytes.fromhex("5756bc53")))

    def test_rejects_truncated_and_wrong_opcode_payloads(self) -> None:
        payload = bytes.fromhex(self.fixture["reply_plaintext_hex"])
        with self.assertRaisesRegex(VendorWireFormatError, "truncated"):
            parse_vendor_dialog_wire(payload[:-1])
        with self.assertRaisesRegex(VendorWireFormatError, "expected VENDORDIALOG"):
            parse_vendor_dialog_wire(bytes.fromhex("5756bc53") + payload[4:])

    def test_rejects_unbounded_string_length_before_allocating(self) -> None:
        payload = bytearray(bytes.fromhex(self.fixture["reply_plaintext_hex"]))
        payload[20:24] = (4_097).to_bytes(4, "big")

        with self.assertRaisesRegex(VendorWireFormatError, "exceeds 4096"):
            parse_vendor_dialog_wire(bytes(payload))


if __name__ == "__main__":
    unittest.main()
