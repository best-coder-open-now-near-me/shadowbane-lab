from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from client_alignment_fixture import build_pe

from shadowbane_lab.diagnostics import (
    ProcessIdentity,
    collect_graphics_present_evidence,
)


def _present_pe() -> bytes:
    result = bytearray(build_pe())
    optional_offset = 0x80 + 24
    struct.pack_into("<I", result, optional_offset + 92, 16)
    struct.pack_into("<II", result, optional_offset + 96 + 8, 0x2000, 0x80)
    data_offset = 0x400
    struct.pack_into("<IIIII", result, data_offset, 0x2040, 0, 0, 0x2030, 0x2050)
    result[data_offset + 0x30 : data_offset + 0x30 + 10] = b"GDI32.dll\0"
    struct.pack_into("<I", result, data_offset + 0x40, 0x2080)
    struct.pack_into("<I", result, data_offset + 0x44, 0)
    struct.pack_into("<I", result, data_offset + 0x50, 0x2080)
    struct.pack_into("<I", result, data_offset + 0x54, 0)
    struct.pack_into("<H", result, data_offset + 0x80, 0)
    result[data_offset + 0x82 : data_offset + 0x82 + 12] = b"SwapBuffers\0"
    return bytes(result)


def _status(executable: Path, identity: ProcessIdentity) -> dict[str, object]:
    entry = {
        "library": "GDI32.dll",
        "symbol": "SwapBuffers",
        "iat_rva": 0x2050,
    }
    return {
        "schema_version": 1,
        "producer_id": "wonderbane-extension.graphics",
        "extension_version": "1.5.4",
        "process_identity": identity.as_dict(),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "present_entries": [{**entry, "call_count": 12}],
        "active_present_entry": entry,
        "graphics_context": {
            "context_observed": True,
            "gl_version": "1.4 fixture",
            "glsl_version": "1.20 fixture",
            "depth_bits": 24,
            "depth_texture_supported": True,
            "framebuffer_object_supported": False,
            "viewport": [0, 0, 800, 600],
        },
        "depth_edge_pass": {"state": "disabled", "reason": "diagnostic fixture"},
    }


class GraphicsPresentEvidenceTests(unittest.TestCase):
    def test_static_import_is_exact_but_active_route_remains_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "sb.exe"
            executable.write_bytes(_present_pe())
            identity = ProcessIdentity(42, 123456, str(executable))

            result = collect_graphics_present_evidence(executable, identity)

            self.assertTrue(result.complete)
            self.assertEqual(1, result.report["assessment"]["candidate_count"])
            self.assertEqual(
                "unresolved",
                result.report["assessment"]["active_route_authority"],
            )
            self.assertTrue(
                result.report["assessment"]["unresolved_mapping_blocks_dependent_renderer_work"]
            )

    def test_identity_bound_runtime_status_proves_present_and_depth_prerequisites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "sb.exe"
            executable.write_bytes(_present_pe())
            identity = ProcessIdentity(43, 123456, str(executable))
            status = root / "graphics-status.json"
            status.write_text(json.dumps(_status(executable, identity)), encoding="utf-8")

            result = collect_graphics_present_evidence(
                executable,
                identity,
                runtime_status_path=status,
            )

            self.assertTrue(result.complete)
            self.assertEqual("accepted", result.report["runtime_status"]["state"])
            self.assertEqual(
                "runtime-observed-exact-process",
                result.report["assessment"]["active_route_authority"],
            )
            self.assertTrue(result.report["assessment"]["depth_edge_prerequisites_observed"])

    def test_runtime_status_with_wrong_creation_identity_is_retained_as_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "sb.exe"
            executable.write_bytes(_present_pe())
            identity = ProcessIdentity(44, 123456, str(executable))
            wrong_identity = ProcessIdentity(44, 123457, str(executable))
            status = root / "graphics-status.json"
            status.write_text(json.dumps(_status(executable, wrong_identity)), encoding="utf-8")

            result = collect_graphics_present_evidence(
                executable,
                identity,
                runtime_status_path=status,
            )

            self.assertFalse(result.complete)
            self.assertIn("creation identity", result.failure or "")
            self.assertEqual("rejected", result.report["runtime_status"]["state"])


if __name__ == "__main__":
    unittest.main()
