from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from shadowbane_vanilla_diagnostics.archive import create_portable_archive


class PortableArchiveTests(unittest.TestCase):
    def test_sealed_capture_archives_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "shadowbane-vanilla-test"
            run.mkdir()
            (run / "capture-evidence.json").write_text("{}\n", encoding="utf-8")
            (run / "capture-complete.json").write_text(
                json.dumps({"terminal_state": "completed"}) + "\n",
                encoding="utf-8",
            )

            archive, checksum = create_portable_archive(run)

            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(
                    ["capture-complete.json", "capture-evidence.json"],
                    sorted(bundle.namelist()),
                )
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(f"{expected}  {archive.name}\n", checksum.read_text("ascii"))
            with self.assertRaises(FileExistsError):
                create_portable_archive(run)


if __name__ == "__main__":
    unittest.main()
