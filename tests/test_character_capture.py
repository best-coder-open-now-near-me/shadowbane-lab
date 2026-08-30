import json
import struct
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.character_capture import (
    BufferMemoryReader,
    CharacterCaptureError,
    capture_character,
    load_character_layout,
)


class CharacterCaptureTests(unittest.TestCase):
    def _fixture(self):
        base = 0x1000
        data = bytearray(0x900)

        def write(address: int, payload: bytes) -> None:
            start = address - base
            data[start : start + len(payload)] = payload

        def pointer(address: int, target: int) -> None:
            write(address, target.to_bytes(4, "little"))

        character = 0x1100
        equipment = 0x1200
        first_item = 0x1300
        second_item = 0x1380
        first_name = 0x1450
        second_name = 0x1480

        pointer(base + 0x20, character)
        write(character + 0x00, b"Ashara\x00")
        write(character + 0x20, struct.pack("<I", 75))
        write(character + 0x24, struct.pack("<I", 165))
        pointer(character + 0x40, equipment)
        pointer(equipment + 0x00, first_item)
        pointer(equipment + 0x04, second_item)
        write(first_item + 0x04, struct.pack("<I", 1001))
        write(second_item + 0x04, struct.pack("<I", 1002))
        pointer(first_item + 0x10, first_name)
        pointer(second_item + 0x10, second_name)
        write(first_name, b"Khan'Xhir\x00")
        write(second_name, b"Rha'Khanakar\x00")

        reader = BufferMemoryReader(data, base_address=base, pointer_size=4)
        return reader

    def _layout_payload(self, *, enabled=True, expected_hash=None):
        return {
            "schema_version": 1,
            "layout_id": "test.wonderbane.character.v1",
            "target": {
                "executable_names": ["Shadowbane.exe"],
                "pointer_size": 4,
                "expected_sha256": expected_hash,
                "live_capture_enabled": enabled,
            },
            "roots": {
                "character": {
                    "base": "module:Shadowbane.exe",
                    "steps": [{"offset": "0x20", "dereference": True}],
                }
            },
            "values": [
                {
                    "path": "identity.name",
                    "type": "cstring",
                    "address": {
                        "base": "root:character",
                        "steps": [{"offset": 0}],
                    },
                    "max_length": 32,
                    "encoding": "cp1252",
                },
                {
                    "path": "identity.level",
                    "type": "u32",
                    "address": {
                        "base": "root:character",
                        "steps": [{"offset": "0x20"}],
                    },
                },
                {
                    "path": "attributes.intelligence",
                    "type": "u32",
                    "address": {
                        "base": "root:character",
                        "steps": [{"offset": "0x24"}],
                    },
                },
            ],
            "records": [],
            "collections": [
                {
                    "path": "equipment",
                    "address": {
                        "base": "root:character",
                        "steps": [{"offset": "0x40", "dereference": True}],
                    },
                    "count": 2,
                    "stride": 4,
                    "element_pointer": True,
                    "skip_null": True,
                    "labels": ["main_hand", "off_hand"],
                    "values": [
                        {"path": "template_id", "type": "u32", "offset": "0x04"},
                        {
                            "path": "name",
                            "type": "cstring",
                            "steps": [{"offset": "0x10", "dereference": True}],
                            "max_length": 64,
                            "encoding": "cp1252",
                        },
                    ],
                }
            ],
            "notes": [],
        }

    def _load(self, payload):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "layout.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return load_character_layout(path)

    def test_capture_reads_identity_attributes_and_equipment(self):
        reader = self._fixture()
        layout = self._load(
            self._layout_payload(expected_hash=reader.process_info.executable_sha256)
        )

        capture = capture_character(layout, reader).as_dict()

        self.assertEqual("Ashara", capture["character"]["identity"]["name"])
        self.assertEqual(75, capture["character"]["identity"]["level"])
        self.assertEqual(165, capture["character"]["attributes"]["intelligence"])
        equipment = capture["character"]["equipment"]
        self.assertEqual("main_hand", equipment[0]["label"])
        self.assertEqual("Khan'Xhir", equipment[0]["name"])
        self.assertEqual(1002, equipment[1]["template_id"])
        self.assertEqual([], capture["warnings"])

    def test_live_locked_layout_refuses_capture(self):
        layout = self._load(self._layout_payload(enabled=False))
        with self.assertRaisesRegex(CharacterCaptureError, "live-locked"):
            capture_character(layout, self._fixture())

    def test_hash_mismatch_refuses_stale_offsets(self):
        layout = self._load(self._layout_payload(expected_hash="0" * 64))
        with self.assertRaisesRegex(CharacterCaptureError, "hash"):
            capture_character(layout, self._fixture())

    def test_text_and_pointer_scans_are_bounded_and_typed(self):
        reader = self._fixture()
        text_matches = reader.scan_text("Ashara", max_scan_bytes=0x900)
        self.assertTrue(any(item.encoding == "cp1252" for item in text_matches))

        pointer_matches = reader.scan_pointer(0x1100, max_scan_bytes=0x900)
        self.assertEqual(0x1020, pointer_matches[0].address)
        self.assertEqual("pointer32", pointer_matches[0].encoding)


if __name__ == "__main__":
    unittest.main()
