from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.client_extension.bootstrap_inspection import (
    BootstrapInspectionError,
    inspect_bootstrap_candidate,
    inspect_bootstrap_file,
    inspect_pe_imports,
)
from tests.client_alignment_fixture import build_pe


def _bootstrap_pe(*, include_get_proc_address: bool = True) -> bytes:
    result = bytearray(build_pe())
    optional_offset = 0x80 + 24
    struct.pack_into("<I", result, optional_offset + 92, 16)
    struct.pack_into("<II", result, optional_offset + 96 + 8, 0x2000, 0x80)
    data_offset = 0x400
    struct.pack_into(
        "<IIIII",
        result,
        data_offset,
        0x2040,
        0,
        0,
        0x2030,
        0x2050,
    )
    result[data_offset + 0x30 : data_offset + 0x30 + 13] = b"KERNEL32.dll\0"
    names = [(0x2080, b"LoadLibraryA\0")]
    if include_get_proc_address:
        names.append((0x20A0, b"GetProcAddress\0"))
    for index, (rva, name) in enumerate(names):
        struct.pack_into("<I", result, data_offset + 0x40 + index * 4, rva)
        struct.pack_into("<I", result, data_offset + 0x50 + index * 4, rva)
        name_offset = data_offset + rva - 0x2000
        struct.pack_into("<H", result, name_offset, 0)
        result[name_offset + 2 : name_offset + 2 + len(name)] = name
    struct.pack_into("<I", result, data_offset + 0x40 + len(names) * 4, 0)
    struct.pack_into("<I", result, data_offset + 0x50 + len(names) * 4, 0)
    result[0x300:0x400] = b"\0" * 0x100
    return bytes(result)


class BootstrapInspectionTests(unittest.TestCase):
    def test_import_inspection_does_not_require_bootstrap_site_review(self) -> None:
        report = inspect_pe_imports(_bootstrap_pe())

        self.assertEqual("evidence_only_no_runtime_route_authority", report["authorization"])
        self.assertEqual(
            ["LoadLibraryA", "GetProcAddress"],
            [item["symbol"] for item in report["imports"]],
        )

    def test_reports_import_slots_entry_boundary_and_only_trailing_raw_padding(self) -> None:
        report = inspect_bootstrap_candidate(_bootstrap_pe())

        self.assertEqual("evidence_only_no_patch_authority", report["authorization"])
        self.assertEqual(0x14C, report["executable"]["machine"])
        self.assertEqual(56, report["pe_layout"]["section_header_slack_bytes"])
        self.assertEqual(
            ["LoadLibraryA", "GetProcAddress"],
            [item["symbol"] for item in report["bootstrap_imports"]],
        )
        self.assertEqual([0x2050, 0x2054], [item["iat_rva"] for item in report["imports"]])
        self.assertEqual(5, report["entry_point"]["disassembly"]["five_byte_prefix"]["length"])
        self.assertEqual(
            {
                "section": ".text",
                "rva": 0x1100,
                "file_offset": 0x300,
                "length": 0x100,
                "fill_byte": 0,
                "within_declared_virtual_size": False,
            },
            report["trailing_executable_padding"][0],
        )
        self.assertTrue(report["assessment"]["candidate_ready_for_manual_stub_review"])

    def test_missing_mechanical_prerequisite_never_becomes_patch_authority(self) -> None:
        report = inspect_bootstrap_candidate(_bootstrap_pe(include_get_proc_address=False))

        self.assertFalse(report["assessment"]["imported_get_proc_address_available"])
        self.assertFalse(report["assessment"]["candidate_ready_for_manual_stub_review"])
        self.assertEqual("evidence_only_no_patch_authority", report["authorization"])

    def test_file_output_is_atomic_create_new_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "sb.exe"
            executable.write_bytes(_bootstrap_pe())
            output = root / "evidence" / "bootstrap.json"

            report = inspect_bootstrap_file(executable, output_path=output)

            self.assertEqual(report, json.loads(output.read_text(encoding="utf-8")))
            self.assertFalse(any(output.parent.glob(".bootstrap.json.tmp-*")))
            with self.assertRaisesRegex(BootstrapInspectionError, "already exists"):
                inspect_bootstrap_file(executable, output_path=output)


if __name__ == "__main__":
    unittest.main()
