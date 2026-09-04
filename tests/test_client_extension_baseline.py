from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.client_extension import (
    ClientBaselineError,
    client_content_build_id,
    freeze_client_baseline,
)
from shadowbane_lab.client_extension.__main__ import main
from tests.client_alignment_fixture import build_pe


class ClientExtensionBaselineTests(unittest.TestCase):
    def test_freezes_rereads_and_reports_complete_client_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Wonderbane"
            source.mkdir()
            executable = build_pe()
            (source / "sb.exe").write_bytes(executable)
            (source / "Config").mkdir()
            (source / "Config" / "ArcaneIP.cfg").write_text(
                "SERVER=example.invalid\n",
                encoding="utf-8",
            )
            frozen = root / "frozen"

            baseline = freeze_client_baseline(
                source,
                frozen,
                repository_revision="047147d",
                captured_at=datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
            )

            payload = json.loads((frozen / "client-baseline.json").read_text(encoding="utf-8"))
            frozen_executable = (frozen / "sb.exe").read_bytes()

        self.assertEqual(2, payload["file_count"])
        self.assertEqual("2026-08-30T12:00:00.000Z", baseline.captured_at_utc)
        self.assertEqual(hashlib.sha256(executable).hexdigest(), baseline.executable.sha256)
        self.assertEqual("sb.exe", baseline.executable.path)
        self.assertEqual(
            ["Config/ArcaneIP.cfg", "sb.exe"],
            [item.relative_path for item in baseline.files],
        )
        self.assertEqual(executable, frozen_executable)
        self.assertEqual(
            (
                f"wb-{baseline.executable.sha256[:8]}-"
                f"{baseline.tree_sha256[:8]}"
            ),
            client_content_build_id(
                executable_sha256=baseline.executable.sha256,
                tree_sha256=baseline.tree_sha256,
            ),
        )

    def test_refuses_existing_nested_and_missing_executable_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "client"
            source.mkdir()
            (source / "sb.exe").write_bytes(build_pe())
            existing = root / "existing"
            existing.mkdir()

            with self.assertRaisesRegex(ClientBaselineError, "already exists"):
                freeze_client_baseline(source, existing, repository_revision="revision")
            with self.assertRaisesRegex(ClientBaselineError, "must not contain"):
                freeze_client_baseline(
                    source,
                    source / "frozen",
                    repository_revision="revision",
                )
            with self.assertRaisesRegex(ClientBaselineError, "not uniquely present"):
                freeze_client_baseline(
                    source,
                    root / "wrong-executable",
                    executable_relative_path="Shadowbane.exe",
                    repository_revision="revision",
                )

    def test_refuses_reparse_points_and_cleans_temporary_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "client"
            source.mkdir()
            (source / "sb.exe").write_bytes(build_pe())
            link = source / "linked.exe"
            try:
                link.symlink_to(source / "sb.exe")
            except OSError:
                self.skipTest("symlink creation is unavailable")
            destination = root / "frozen"

            with self.assertRaisesRegex(ClientBaselineError, "non-regular file"):
                freeze_client_baseline(source, destination, repository_revision="revision")

            self.assertFalse(destination.exists())
            self.assertEqual([], list(root.glob(".frozen.tmp-*")))

    def test_cli_freezes_baseline_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "client"
            source.mkdir()
            (source / "sb.exe").write_bytes(build_pe())
            destination = root / "frozen"
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    (
                        "freeze-baseline",
                        str(source),
                        str(destination),
                        "--repository-revision",
                        "047147d",
                    )
                )
            error = io.StringIO()
            with redirect_stderr(error):
                repeated = main(
                    (
                        "freeze-baseline",
                        str(source),
                        str(destination),
                        "--repository-revision",
                        "047147d",
                    )
                )

        self.assertEqual(0, result)
        self.assertEqual(2, repeated)
        self.assertEqual("047147d", json.loads(output.getvalue())["repository_revision"])
        self.assertIn("already exists", error.getvalue())

    def test_cli_identifies_verified_baseline_by_executable_and_tree_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "client"
            source.mkdir()
            (source / "sb.exe").write_bytes(build_pe())
            (source / "Textures.cache").write_bytes(b"reviewed-cache")
            frozen = root / "frozen"
            baseline = freeze_client_baseline(
                source,
                frozen,
                repository_revision="revision",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(("identify-baseline", str(frozen), "--pretty"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(
            f"wb-{baseline.executable.sha256[:8]}-{baseline.tree_sha256[:8]}",
            payload["content_build_id"],
        )
        self.assertEqual(baseline.executable.sha256, payload["executable_sha256"])
        self.assertEqual(baseline.tree_sha256, payload["tree_sha256"])
        self.assertEqual(2, payload["file_count"])


if __name__ == "__main__":
    unittest.main()
