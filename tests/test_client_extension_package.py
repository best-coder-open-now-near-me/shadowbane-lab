from __future__ import annotations

import hashlib
import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.client_extension.__main__ import main
from shadowbane_lab.client_extension.baseline import freeze_client_baseline
from shadowbane_lab.client_extension.manifest import (
    ExtensionArtifact,
    MaskedSignature,
    PatchManifest,
    PatchSite,
    SourceExecutable,
)
from shadowbane_lab.client_extension.package import (
    ClientPatchPackageError,
    audit_patched_client_copy,
    discard_patched_client_copy,
    discard_runtime_drifted_client_copy,
    prepare_patched_client_copy,
    verify_frozen_client_baseline,
    verify_patched_client_copy,
)
from tests.client_alignment_fixture import build_pe

_TEXT_RVA = 0x1000
_TEXT_OFFSET = 0x200
_SITE_RVA = 0x1020
_ORIGINAL = b"\x11\x22"
_REPLACEMENT = b"\x33\x44"
_SIGNATURE = b"\xAA\xBB" + _ORIGINAL + b"\xCC"
_CREATED_AT = datetime(2026, 8, 30, 12, 30, tzinfo=UTC)


def _file_offset(rva: int) -> int:
    return _TEXT_OFFSET + rva - _TEXT_RVA


def _source_executable() -> bytes:
    result = bytearray(build_pe())
    offset = _file_offset(_SITE_RVA - 2)
    result[offset : offset + len(_SIGNATURE)] = _SIGNATURE
    return bytes(result)


def _extension_dll() -> bytes:
    result = bytearray(build_pe(text_byte=0xCC, data_byte=0x77))
    characteristics_offset = 0x80 + 4 + 18
    (characteristics,) = struct.unpack_from("<H", result, characteristics_offset)
    struct.pack_into("<H", result, characteristics_offset, characteristics | 0x2000)
    return bytes(result)


def _patched(source: bytes) -> bytes:
    result = bytearray(source)
    offset = _file_offset(_SITE_RVA)
    result[offset : offset + len(_ORIGINAL)] = _REPLACEMENT
    return bytes(result)


def _manifest(source: bytes, extension: bytes) -> PatchManifest:
    return PatchManifest(
        patch_id="fixture.bootstrap-v1",
        source=SourceExecutable(
            file_name="sb.exe",
            sha256=hashlib.sha256(source).hexdigest(),
            length=len(source),
            machine=0x14C,
            pointer_size=4,
        ),
        patched_executable_sha256=hashlib.sha256(_patched(source)).hexdigest(),
        extension=ExtensionArtifact(
            file_name="wonderbane-extension.dll",
            sha256=hashlib.sha256(extension).hexdigest(),
            version="1.0.0",
            machine=0x14C,
            bootstrap_export="WonderBaneExtensionInitialize",
        ),
        sites=(
            PatchSite(
                site_id="bootstrap-entry",
                section=".text",
                reviewed_rva=_SITE_RVA,
                expected_original=_ORIGINAL,
                replacement=_REPLACEMENT,
                signature=MaskedSignature(
                    value=b"\xAA\xBB\x00\x00\xCC",
                    mask=b"\xFF\xFF\x00\x00\xFF",
                ),
                signature_site_offset=2,
                search_radius=0x80,
            ),
        ),
    )


def _freeze(root: Path, executable: bytes) -> tuple[Path, Path]:
    source = root / "official"
    source.mkdir()
    (source / "sb.exe").write_bytes(executable)
    (source / "Config").mkdir()
    (source / "Config" / "ArcaneIP.cfg").write_text("SERVER=fixture\n", encoding="utf-8")
    (source / "Config" / "ArcanePref.cfg").write_text("PREF=fixture\n", encoding="utf-8")
    frozen = root / "frozen"
    freeze_client_baseline(
        source,
        frozen,
        repository_revision="443bfc5",
        captured_at=_CREATED_AT,
    )
    return source, frozen


class ClientExtensionPackageTests(unittest.TestCase):
    def test_cli_dry_run_emits_machine_readable_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            manifest_path = root / "patch.json"
            manifest_path.write_text(
                json.dumps(_manifest(source, extension).as_dict()),
                encoding="utf-8",
            )
            destination = root / "working"
            output = io.StringIO()

            with redirect_stdout(output):
                result = main(
                    (
                        "prepare-copy",
                        str(frozen),
                        str(destination),
                        str(manifest_path),
                        str(extension_path),
                        "--dry-run",
                    )
                )

            payload = json.loads(output.getvalue())
            self.assertEqual(0, result)
            self.assertTrue(payload["dry_run"])
            self.assertEqual("fixture.bootstrap-v1", payload["plan"]["patch_id"])
            self.assertFalse(destination.exists())

    def test_dry_run_verifies_every_input_without_creating_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"

            result = prepare_patched_client_copy(
                frozen,
                destination,
                _manifest(source, extension),
                extension_path,
                dry_run=True,
            )

            self.assertTrue(result.dry_run)
            self.assertFalse(result.destination_published)
            self.assertIsNone(result.evidence)
            self.assertFalse(destination.exists())
            self.assertFalse(any(root.glob(".working.tmp-*")))

    def test_publishes_and_rereads_complete_disposable_copy_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            baseline_before = verify_frozen_client_baseline(frozen)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"

            result = prepare_patched_client_copy(
                frozen,
                destination,
                _manifest(source, extension),
                extension_path,
                created_at=_CREATED_AT,
            )
            verified = verify_patched_client_copy(destination)
            baseline_after = verify_frozen_client_baseline(frozen)

            self.assertTrue(result.destination_published)
            self.assertEqual(result.evidence, verified)
            self.assertEqual(_patched(source), (destination / "sb.exe").read_bytes())
            self.assertEqual(extension, (destination / "wonderbane-extension.dll").read_bytes())
            self.assertEqual(baseline_before, baseline_after)
            self.assertFalse(any(root.glob(".working.tmp-*")))

    def test_exact_already_patched_baseline_is_recognized_without_rewriting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, _patched(source))
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)

            result = prepare_patched_client_copy(
                frozen,
                root / "working",
                _manifest(source, extension),
                extension_path,
            )

            self.assertTrue(result.plan.already_patched)
            self.assertTrue(result.evidence and result.evidence.already_patched)

    def test_tampered_baseline_and_invalid_extension_fail_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"
            (frozen / "Config" / "ArcaneIP.cfg").write_text("tampered", encoding="utf-8")

            with self.assertRaisesRegex(ClientPatchPackageError, "differs"):
                prepare_patched_client_copy(
                    frozen,
                    destination,
                    _manifest(source, extension),
                    extension_path,
                )
            self.assertFalse(destination.exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(build_pe())
            destination = root / "working"

            with self.assertRaisesRegex(ClientPatchPackageError, "SHA-256"):
                prepare_patched_client_copy(
                    frozen,
                    destination,
                    _manifest(source, extension),
                    extension_path,
                )
            self.assertFalse(destination.exists())

    def test_failed_post_publish_verification_removes_new_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"

            with (
                patch(
                    "shadowbane_lab.client_extension.package.verify_patched_client_copy",
                    side_effect=ClientPatchPackageError("forced reread failure"),
                ),
                self.assertRaisesRegex(ClientPatchPackageError, "forced reread failure"),
            ):
                prepare_patched_client_copy(
                    frozen,
                    destination,
                    _manifest(source, extension),
                    extension_path,
                )

            self.assertFalse(destination.exists())
            self.assertFalse(any(root.glob(".working.tmp-*")))

    def test_verified_discard_removes_only_copy_and_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"
            prepare_patched_client_copy(
                frozen,
                destination,
                _manifest(source, extension),
                extension_path,
            )
            receipt_path = root / "rollback.json"

            receipt = discard_patched_client_copy(
                destination,
                receipt_path,
                discarded_at=_CREATED_AT,
            )
            receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))

            self.assertFalse(destination.exists())
            self.assertTrue(frozen.exists())
            self.assertEqual(receipt.patch_id, receipt_payload["patch_id"])
            self.assertEqual("2026-08-30T12:30:00.000Z", receipt.discarded_at_utc)
            self.assertFalse(any(root.glob(".working.discard-*")))

    def test_audit_reports_added_missing_and_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"
            prepare_patched_client_copy(
                frozen,
                destination,
                _manifest(source, extension),
                extension_path,
            )

            self.assertTrue(audit_patched_client_copy(destination).matches)
            (destination / "Config" / "ArcaneIP.cfg").write_text("changed", encoding="utf-8")
            (destination / "wonderbane-extension.dll").unlink()
            (destination / "runtime.log").write_text("generated", encoding="utf-8")

            drift = audit_patched_client_copy(destination)
            self.assertFalse(drift.matches)
            self.assertEqual(["runtime.log"], [item.relative_path for item in drift.added])
            self.assertEqual(
                ["wonderbane-extension.dll"],
                [item.relative_path for item in drift.missing],
            )
            self.assertEqual(
                ["Config/ArcaneIP.cfg"],
                [item.expected.relative_path for item in drift.changed],
            )

    def test_audit_copy_cli_emits_read_only_drift_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"
            prepare_patched_client_copy(
                frozen,
                destination,
                _manifest(source, extension),
                extension_path,
            )
            (destination / "runtime.log").write_text("generated", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                result = main(["audit-copy", str(destination)])

            payload = json.loads(output.getvalue())
            self.assertEqual(0, result)
            self.assertFalse(payload["matches"])
            self.assertEqual("runtime.log", payload["added"][0]["relative_path"])
            self.assertTrue(destination.exists())

    def test_runtime_drifted_discard_archives_allowed_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"
            prepare_patched_client_copy(
                frozen,
                destination,
                _manifest(source, extension),
                extension_path,
            )
            changed = destination / "Config" / "ArcanePref.cfg"
            changed.write_text("PREF=runtime\n", encoding="utf-8")
            removed = destination / "Logs" / "debug.txt"
            removed.parent.mkdir()
            removed.write_text("baseline\n", encoding="utf-8")
            evidence_path = destination / ".wonderbane-extension" / "package.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            removed_record = {
                "relative_path": "Logs/debug.txt",
                "size": len(b"baseline\n"),
                "sha256": hashlib.sha256(b"baseline\n").hexdigest(),
            }
            evidence["files"].append(removed_record)
            evidence["files"].sort(key=lambda item: item["relative_path"].casefold())
            tree = hashlib.sha256()
            for item in evidence["files"]:
                tree.update(item["relative_path"].encode("utf-8"))
                tree.update(b"\0")
                tree.update(str(item["size"]).encode("ascii"))
                tree.update(b"\0")
                tree.update(item["sha256"].encode("ascii"))
                tree.update(b"\n")
            evidence["working_tree_sha256"] = tree.hexdigest()
            evidence["file_count"] = len(evidence["files"])
            evidence["total_file_bytes"] = sum(item["size"] for item in evidence["files"])
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            removed.unlink()
            drift = audit_patched_client_copy(destination)
            receipt_path = root / "retired.json"
            archive = root / "runtime-files"

            receipt = discard_runtime_drifted_client_copy(
                destination,
                receipt_path,
                archive,
                actual_working_tree_sha256=drift.actual_working_tree_sha256,
                discarded_at=_CREATED_AT,
            )

            self.assertFalse(destination.exists())
            self.assertTrue(receipt_path.is_file())
            self.assertEqual("PREF=runtime\n", (archive / "Config" / "ArcanePref.cfg").read_text())
            self.assertEqual(drift.actual_working_tree_sha256, receipt.actual_working_tree_sha256)
            self.assertEqual(
                ["Logs/debug.txt"],
                [item.relative_path for item in receipt.missing_files],
            )

    def test_runtime_drifted_discard_rejects_unreviewed_or_stale_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"
            prepare_patched_client_copy(
                frozen,
                destination,
                _manifest(source, extension),
                extension_path,
            )
            (destination / "Config" / "ArcaneIP.cfg").write_text("changed", encoding="utf-8")
            drift = audit_patched_client_copy(destination)

            with self.assertRaisesRegex(ClientPatchPackageError, "non-runtime changes"):
                discard_runtime_drifted_client_copy(
                    destination,
                    root / "retired.json",
                    root / "runtime-files",
                    actual_working_tree_sha256=drift.actual_working_tree_sha256,
                )
            with self.assertRaisesRegex(ClientPatchPackageError, "changed after"):
                discard_runtime_drifted_client_copy(
                    destination,
                    root / "retired.json",
                    root / "runtime-files",
                    actual_working_tree_sha256="0" * 64,
                )

            self.assertTrue(destination.exists())
            self.assertFalse((root / "runtime-files").exists())

    def test_tampered_copy_cannot_be_discarded_through_verified_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source_executable()
            extension = _extension_dll()
            _, frozen = _freeze(root, source)
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"
            prepare_patched_client_copy(
                frozen,
                destination,
                _manifest(source, extension),
                extension_path,
            )
            (destination / "Config" / "ArcaneIP.cfg").write_text("changed", encoding="utf-8")

            with self.assertRaisesRegex(ClientPatchPackageError, "differs"):
                discard_patched_client_copy(destination, root / "rollback.json")

            self.assertTrue(destination.exists())
            self.assertFalse((root / "rollback.json").exists())


if __name__ == "__main__":
    unittest.main()
