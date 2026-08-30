from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from client_alignment_fixture import build_pe
from shadowbane_lab.client_alignment.__main__ import main
from shadowbane_lab.client_alignment.pe import PeInspectionError, inspect_pe_bytes


class ClientAlignmentPeTests(unittest.TestCase):
    def test_inspect_pe_records_stable_structure_and_hashes(self) -> None:
        payload = build_pe()

        image = inspect_pe_bytes(payload, path="fixture.exe")

        self.assertEqual(0x14C, image.machine)
        self.assertEqual(4, image.pointer_size)
        self.assertEqual(0x400000, image.image_base)
        self.assertEqual([".text", ".data"], [section.name for section in image.sections])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), image.sha256)
        self.assertEqual(
            hashlib.sha256(payload[0x200:0x400]).hexdigest(), image.sections[0].sha256
        )

    def test_non_pe_input_is_rejected(self) -> None:
        with self.assertRaises(PeInspectionError):
            inspect_pe_bytes(b"not a PE")

    def test_module_cli_emits_deterministic_json(self) -> None:
        executable = build_pe()
        with tempfile.TemporaryDirectory() as directory_name:
            executable_path = Path(directory_name) / "fixture.exe"
            executable_path.write_bytes(executable)
            output = io.StringIO()
            errors = io.StringIO()

            with redirect_stdout(output), redirect_stderr(errors):
                result = main(["inspect", str(executable_path)])

            self.assertEqual(0, result)
            self.assertEqual("", errors.getvalue())
            payload = json.loads(output.getvalue())
            self.assertEqual(1, payload["schema_version"])
            self.assertEqual(hashlib.sha256(executable).hexdigest(), payload["image"]["sha256"])


if __name__ == "__main__":
    unittest.main()
