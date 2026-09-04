from __future__ import annotations

import io
import json
import struct
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.client_extension import (
    ClientPatchDiffError,
    compare_frozen_client_baselines,
    freeze_client_baseline,
    write_client_patch_diff,
)
from shadowbane_lab.client_extension.__main__ import main
from tests.client_alignment_fixture import build_pe


class ClientExtensionPatchDiffTests(unittest.TestCase):
    def test_compares_verified_trees_caches_and_executable_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = _freeze_release_pair(root)

            report = compare_frozen_client_baselines(
                source,
                target,
                patch_id="wonderbane-1.0.5-to-1.0.6",
                compared_at=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
            )
            payload = report.as_dict()

        self.assertEqual("2026-08-31T12:00:00.000Z", report.compared_at_utc)
        self.assertEqual(
            {
                "added": 1,
                "modified": 3,
                "removed": 1,
                "renamed": 1,
            },
            _file_kind_counts(report),
        )
        self.assertEqual(1, report.unchanged_file_count)
        renamed = next(change for change in report.file_changes if change.kind == "renamed")
        self.assertEqual("old-name.dat", renamed.before_path)
        self.assertEqual("new-name.dat", renamed.after_path)
        self.assertEqual(1, len(report.cache_archive_diffs))
        cache = report.cache_archive_diffs[0]
        self.assertEqual(1, cache.unchanged_resource_count)
        self.assertEqual(
            {"added": 1, "modified": 1, "removed": 1, "repacked": 1},
            _resource_kind_counts(cache),
        )
        self.assertIsNotNone(report.executable_alignment)
        assert report.executable_alignment is not None
        self.assertIn(".text", report.executable_alignment.changed_sections)
        self.assertTrue(payload["summary"]["executable_changed"])
        self.assertEqual(report.report_sha256, payload["report_sha256"])
        serialized = json.dumps(payload)
        self.assertNotIn("new configuration contents", serialized)
        self.assertNotIn("new logical resource", serialized)

    def test_publishes_create_new_report_and_cli_can_disable_cache_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = _freeze_release_pair(root)
            output_path = root / "reports" / "patch.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    (
                        "diff-baselines",
                        str(source),
                        str(target),
                        "--patch-id",
                        "wonderbane-1.0.5-to-1.0.6",
                        "--output",
                        str(output_path),
                        "--no-cache-analysis",
                        "--pretty",
                    )
                )
            published = json.loads(output_path.read_text(encoding="utf-8"))
            emitted = json.loads(stdout.getvalue())
            report = compare_frozen_client_baselines(
                source,
                target,
                patch_id="second-report",
                analyze_caches=False,
            )
            with self.assertRaisesRegex(ClientPatchDiffError, "already exists"):
                write_client_patch_diff(output_path, report)

        self.assertEqual(0, result)
        self.assertEqual(published, emitted)
        self.assertEqual([], published["cache_archive_diffs"])

    def test_refuses_a_client_tree_that_changed_after_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = _freeze_release_pair(root)
            (target / "Config" / "settings.cfg").write_text("tampered\n", encoding="utf-8")

            with self.assertRaisesRegex(ClientPatchDiffError, "verification failed"):
                compare_frozen_client_baselines(
                    source,
                    target,
                    patch_id="wonderbane-tampered",
                )


def _freeze_release_pair(root: Path) -> tuple[Path, Path]:
    source_client = root / "source-client"
    target_client = root / "target-client"
    for directory in (source_client, target_client):
        (directory / "Config").mkdir(parents=True)
        (directory / "cache").mkdir()

    (source_client / "sb.exe").write_bytes(build_pe(text_byte=0x90))
    (target_client / "sb.exe").write_bytes(build_pe(text_byte=0x91))
    (source_client / "Config" / "settings.cfg").write_text(
        "old configuration contents\n", encoding="utf-8"
    )
    (target_client / "Config" / "settings.cfg").write_text(
        "new configuration contents\n", encoding="utf-8"
    )
    (source_client / "same.txt").write_text("same\n", encoding="utf-8")
    (target_client / "same.txt").write_text("same\n", encoding="utf-8")
    (source_client / "old-name.dat").write_bytes(b"rename-identity")
    (target_client / "new-name.dat").write_bytes(b"rename-identity")
    (source_client / "removed.dat").write_bytes(b"removed")
    (target_client / "added.dat").write_bytes(b"added")
    (source_client / "cache" / "Objects.cache").write_bytes(
        _build_cache(
            {
                (0, 1): (b"unchanged logical resource", False),
                (0, 2): (b"old logical resource", False),
                (0, 3): (b"removed logical resource", False),
                (0, 5): (b"same payload, new storage", False),
            }
        )
    )
    (target_client / "cache" / "Objects.cache").write_bytes(
        _build_cache(
            {
                (0, 1): (b"unchanged logical resource", False),
                (0, 2): (b"new logical resource", False),
                (0, 4): (b"added logical resource", False),
                (0, 5): (b"same payload, new storage", True),
            }
        )
    )

    source = root / "frozen-source"
    target = root / "frozen-target"
    freeze_client_baseline(source_client, source, repository_revision="source-tool-revision")
    freeze_client_baseline(target_client, target, repository_revision="target-tool-revision")
    return source, target


def _build_cache(resources: dict[tuple[int, int], tuple[bytes, bool]]) -> bytes:
    header = struct.Struct("<IIII")
    directory_entry = struct.Struct("<IIIII")
    ordered = sorted(resources.items())
    data_offset = header.size + len(ordered) * directory_entry.size
    records: list[tuple[int, int, int, int, int]] = []
    stored_payloads: list[bytes] = []
    cursor = data_offset
    for (group_id, resource_id), (payload, compress) in ordered:
        stored = zlib.compress(payload) if compress else payload
        records.append((group_id, resource_id, cursor, len(payload), len(stored)))
        stored_payloads.append(stored)
        cursor += len(stored)
    output = bytearray(header.pack(len(records), data_offset, cursor, 0xCACE))
    for record in records:
        output.extend(directory_entry.pack(*record))
    for stored in stored_payloads:
        output.extend(stored)
    return bytes(output)


def _file_kind_counts(report: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for change in report.file_changes:  # type: ignore[attr-defined]
        counts[change.kind] = counts.get(change.kind, 0) + 1
    return counts


def _resource_kind_counts(cache: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for change in cache.changes:  # type: ignore[attr-defined]
        counts[change.kind] = counts.get(change.kind, 0) + 1
    return counts


if __name__ == "__main__":
    unittest.main()
