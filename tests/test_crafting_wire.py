"""Synthetic upstream fixtures; these do not prove WonderBane compatibility."""

import contextlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation.crafting_wire import ProductionAction, parse_crafting_wire
from shadowbane_lab.client_observation.vendor_wire import VendorWireFormatError


def words(*values: int) -> bytes:
    return struct.pack(">" + "I" * len(values), *values)


def request(action: int = 1) -> bytes:
    return (
        words(0x3CCE8E30, action, 5, 100, 42, 200, 0, 1234, 1, 0, 0, 0)
        + words(2)
        + "鍛A".encode("utf-16-be")
        + words(0, 0)
        + (b"\0\0" if action == 1 else b"\0")
    )


def update(*, complete: bool = True) -> bytes:
    return (
        words(
            0x3CCE8E30,
            8,
            5,
            100,
            42,
            200,
            0,
            0,
            1,
            0xA6C53AAA,
            111 if complete else 0,
            222 if complete else 0,
            0,
            6,
            0xFFFFFFFF,
            0,
            1234,
            900,
            0 if complete else 30,
            0 if complete else 60,
            0 if complete else 1,
        )
        + bytes((0, int(complete), 0, 1))
        + words(50000, 0, 0)
    )


class CraftingWireTests(unittest.TestCase):
    def test_random_produce_and_unicode(self) -> None:
        msg = parse_crafting_wire(request(), direction="client_to_server")
        self.assertEqual(ProductionAction.PRODUCE, msg.action)
        self.assertEqual((100, 200), (msg.building_id, msg.vendor_id))
        fields = dict(msg.fields)
        self.assertEqual("鍛A", fields["name"])
        self.assertEqual(0, fields["prefix_token"])
        self.assertEqual(0, fields["suffix_token"])
        self.assertEqual(1234, fields["item_or_template_id"])
        self.assertEqual("upstream_source_only", msg.to_dict()["compatibility"])

    def test_complete_and_junk_request_trailers(self) -> None:
        for action in (2, 4):
            msg = parse_crafting_wire(request(action), direction="client_to_server")
            self.assertEqual(action, int(msg.action))

    def test_cooking_and_ready_are_distinct(self) -> None:
        for complete in (False, True):
            msg = parse_crafting_wire(update(complete=complete), direction="server_to_client")
            fields = dict(msg.fields)
            self.assertEqual(int(complete), fields["complete_flag"])
            self.assertEqual(0xFFFFFFFF, fields["item_id"])
            self.assertEqual(1234, fields["template_id"])
            self.assertEqual(50000, fields["strongbox_gold"])

    def test_every_truncation_is_rejected(self) -> None:
        for payload, direction in ((request(), "client_to_server"), (update(), "server_to_client")):
            for size in range(len(payload)):
                with self.subTest(direction=direction, size=size):
                    with self.assertRaises(VendorWireFormatError):
                        parse_crafting_wire(payload[:size], direction=direction)

    def test_wrong_direction_and_trailing_data_are_rejected(self) -> None:
        for payload, direction in (
            (request(), "server_to_client"),
            (update(), "client_to_server"),
            (request() + b"\0", "client_to_server"),
        ):
            with self.assertRaises(VendorWireFormatError):
                parse_crafting_wire(payload, direction=direction)

    def test_unknown_action_opcode_and_oversized_name(self) -> None:
        for offset, value in ((0, 0), (4, 99), (48, 4097)):
            payload = bytearray(request())
            struct.pack_into(">I", payload, offset, value)
            with self.assertRaises(VendorWireFormatError):
                parse_crafting_wire(bytes(payload), direction="client_to_server")

    def test_conflicting_completion_flags(self) -> None:
        payload = bytearray(update())
        payload[-15] = 0
        with self.assertRaisesRegex(VendorWireFormatError, "conflicting"):
            parse_crafting_wire(bytes(payload), direction="server_to_client")

    def test_cli_success_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roll.bin"
            for payload, expected in ((update(), 0), (b"bad", 2), (b"x" * 65537, 2)):
                path.write_bytes(payload)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(
                        [
                            "client",
                            "decode-crafting",
                            str(path),
                            "--direction",
                            "server_to_client",
                            "--json",
                        ]
                    )
                self.assertEqual(expected, code)
                self.assertEqual(expected == 0, json.loads(output.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
