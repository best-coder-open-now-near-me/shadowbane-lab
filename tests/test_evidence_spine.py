from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from shadowbane_lab.cli import main
from shadowbane_lab.evidence import (
    ArtifactKind,
    ArtifactStore,
    EvidenceError,
    EvidenceManifest,
    ManifestTerminalState,
    Redaction,
    RedactionState,
    VerificationStatus,
    create_bundle,
    import_legacy_files,
    load_manifest,
    load_migration_receipt,
    load_verification_receipt,
    query_index,
    rebuild_index,
    save_contract,
    verify_bundle,
    verify_manifest,
)
from shadowbane_lab.integrity import PathSecurityError, canonical_timestamp


class EvidenceSpineTests(unittest.TestCase):
    def _store(self, root: Path) -> ArtifactStore:
        return ArtifactStore.initialize(root / "store", store_id="test-store")

    def _descriptor(self, store: ArtifactStore, payload: bytes = b"evidence"):
        return store.ingest_bytes(
            payload,
            artifact_kind=ArtifactKind.SEMANTIC_TRACE,
            media_type="application/json",
            logical_name="trace.json",
            producer_id="test-producer",
            producer_version="1.0.0",
            captured_at_utc="2026-08-31T12:00:00.000Z",
            metadata=(("channel", "semantic"),),
        )

    def _manifest(self, store: ArtifactStore) -> EvidenceManifest:
        descriptor = self._descriptor(store)
        return EvidenceManifest(
            created_at_utc="2026-08-31T12:00:01.000Z",
            artifacts=(descriptor,),
            terminal_state=ManifestTerminalState.COMPLETE,
            required_channels=("semantic",),
            completed_channels=("semantic",),
            fingerprint_id="fingerprint-test",
            case_id="case-test",
            experiment_id="experiment-test-v1",
            run_id="run-test-1",
        )

    def test_store_deduplicates_and_verifies_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root)
            first = self._descriptor(store)
            second = self._descriptor(store)
            self.assertEqual(first.artifact_id, second.artifact_id)
            self.assertEqual(1, len(tuple(store.objects_directory.rglob(first.sha256[2:]))))
            self.assertEqual((True, None), store.verify_descriptor(first))
            with store.open_artifact(first.artifact_id or "") as stream:
                self.assertEqual(b"evidence", stream.read())

    def test_store_streams_chunks_without_joining_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            streamed = store.ingest_chunks(
                (chunk for chunk in (b"evi", b"dence")),
                artifact_kind=ArtifactKind.SEMANTIC_TRACE,
                media_type="application/json",
                logical_name="streamed-trace.json",
                producer_id="test-producer",
                producer_version="1.0.0",
                captured_at_utc="2026-08-31T12:00:00.000Z",
            )
            ordinary = self._descriptor(store)

            self.assertEqual(ordinary.artifact_id, streamed.artifact_id)
            self.assertEqual((True, None), store.verify_descriptor(streamed))

    def test_object_path_rejects_reparse_at_every_existing_segment(self) -> None:
        payload = b"reparse containment"
        digest = hashlib.sha256(payload).hexdigest()
        artifact_id = f"sha256:{digest}"
        for segment in ("algorithm", "prefix", "object"):
            with self.subTest(segment=segment), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                store = self._store(root)
                outside_directory = root / f"outside-{segment}"
                outside_directory.mkdir()
                if segment == "algorithm":
                    unsafe = store.objects_directory
                    unsafe.rmdir()
                    target = outside_directory
                    directory_link = True
                elif segment == "prefix":
                    unsafe = store.objects_directory / digest[:2]
                    target = outside_directory
                    directory_link = True
                else:
                    unsafe = store.objects_directory / digest[:2] / digest[2:]
                    unsafe.parent.mkdir()
                    target = outside_directory / "object"
                    target.write_bytes(payload)
                    directory_link = False
                try:
                    unsafe.symlink_to(target, target_is_directory=directory_link)
                except OSError:
                    self.skipTest("symlink creation is not permitted")

                with self.assertRaisesRegex(EvidenceError, "object path is unsafe"):
                    store.object_path(artifact_id)

    def test_publication_revalidation_is_fail_closed_without_symlink_support(self) -> None:
        payload = b"deterministic publication containment"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root)
            target = store.objects_directory / digest[:2] / digest[2:]
            calls = 0

            def reject_second_resolution(_root: Path, _relative: str) -> Path:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise PathSecurityError("simulated prefix replacement")
                return target

            with (
                patch(
                    "shadowbane_lab.evidence.storage.resolve_within_root",
                    side_effect=reject_second_resolution,
                ),
                self.assertRaisesRegex(EvidenceError, "object path is unsafe"),
            ):
                self._descriptor(store, payload)

            self.assertEqual(2, calls)
            self.assertEqual((), store.quarantine_inventory())
            self.assertFalse(target.exists())

    def test_publication_revalidates_containment_and_cleans_stage(self) -> None:
        payload = b"publication containment"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root)
            outside = root / "outside"
            outside.mkdir()
            probe = root / "symlink-probe"
            try:
                probe.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation is not permitted")
            probe.unlink()
            prefix = store.objects_directory / digest[:2]
            original_object_path = store.object_path
            calls = 0

            def swap_before_revalidation(artifact_id: str) -> Path:
                nonlocal calls
                calls += 1
                if calls == 2:
                    prefix.rmdir()
                    prefix.symlink_to(outside, target_is_directory=True)
                return original_object_path(artifact_id)

            with (
                patch.object(store, "object_path", side_effect=swap_before_revalidation),
                self.assertRaisesRegex(EvidenceError, "object path is unsafe"),
            ):
                self._descriptor(store, payload)

            self.assertEqual((), store.quarantine_inventory())

    def test_manifest_and_receipt_round_trip_and_refuse_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root)
            manifest = self._manifest(store)
            manifest_path = root / "manifests" / "run.json"
            save_contract(manifest_path, manifest)
            self.assertEqual(manifest, load_manifest(manifest_path))
            with self.assertRaises(EvidenceError):
                save_contract(manifest_path, manifest)
            receipt = verify_manifest(store, manifest)
            self.assertEqual(VerificationStatus.PASS, receipt.status)
            receipt_path = root / "receipts" / "verify.json"
            save_contract(receipt_path, receipt)
            self.assertEqual(receipt, load_verification_receipt(receipt_path))

    def test_corrupt_object_fails_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            manifest = self._manifest(store)
            descriptor = manifest.artifacts[0]
            store.object_path(descriptor.artifact_id or "").write_bytes(b"corrupt!")
            receipt = verify_manifest(store, manifest)
            self.assertEqual(VerificationStatus.FAIL, receipt.status)
            self.assertFalse(receipt.results[0].passed)

    def test_bundle_is_portable_and_detects_member_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root)
            manifest = self._manifest(store)
            bundle = create_bundle(store, manifest, root / "bundle.zip")
            self.assertEqual(manifest, verify_bundle(bundle))

    def test_index_is_rebuildable_and_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root)
            manifest = self._manifest(store)
            manifest_directory = root / "manifests"
            save_contract(manifest_directory / "run.json", manifest)
            index = root / "index" / "evidence.sqlite"
            self.assertEqual(1, rebuild_index(manifest_directory, index))
            rows = query_index(index, artifact_kind="semantic_trace", case_id="case-test")
            self.assertEqual(1, len(rows))
            self.assertEqual(manifest.manifest_id, rows[0]["manifest_id"])
            self.assertEqual("trace.json", rows[0]["logical_name"])

    def test_legacy_import_preserves_sources_and_emits_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "legacy.json"
            source.write_text('{"legacy":true}\n', encoding="utf-8")
            original = source.read_bytes()
            store = self._store(root)
            manifest, receipt = import_legacy_files(
                store,
                (source,),
                artifact_kind=ArtifactKind.SOURCE_SNAPSHOT,
                media_type="application/json",
                case_id="case-import",
            )
            self.assertEqual(original, source.read_bytes())
            self.assertEqual(ManifestTerminalState.IMPORTED, manifest.terminal_state)
            self.assertEqual(manifest.manifest_id, receipt.manifest_id)
            receipt_path = root / "migration.json"
            save_contract(receipt_path, receipt)
            self.assertEqual(receipt, load_migration_receipt(receipt_path))

    def test_redaction_requires_explicit_derivation(self) -> None:
        with self.assertRaises(ValueError):
            Redaction(RedactionState.REDACTED, policy_id="privacy-v1")
        with self.assertRaises(ValueError):
            Redaction(
                RedactionState.NOT_REQUIRED,
                policy_id="privacy-v1",
                source_artifact_id="sha256:" + "0" * 64,
            )

    def test_complete_manifest_requires_every_channel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            descriptor = self._descriptor(store)
            with self.assertRaisesRegex(ValueError, "missing required"):
                EvidenceManifest(
                    created_at_utc=canonical_timestamp(),
                    artifacts=(descriptor,),
                    terminal_state=ManifestTerminalState.COMPLETE,
                    required_channels=("native",),
                )

    def test_manifest_loader_rejects_duplicate_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaises(EvidenceError):
                load_manifest(path)

    def test_store_config_is_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "store"
            ArtifactStore.initialize(root, store_id="strict-store")
            payload = json.loads((root / "store.json").read_text(encoding="utf-8"))
            payload["unknown"] = True
            (root / "store.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(EvidenceError):
                ArtifactStore(root)

    def test_public_json_schemas_accept_every_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root)
            manifest = self._manifest(store)
            verification = verify_manifest(store, manifest)
            source = root / "legacy.json"
            source.write_text("{}\n", encoding="utf-8")
            _, migration = import_legacy_files(
                store,
                (source,),
                artifact_kind=ArtifactKind.SOURCE_SNAPSHOT,
                media_type="application/json",
            )
            schema_root = Path(__file__).parents[1] / "schemas"
            names = (
                "artifact-descriptor-v1.schema.json",
                "evidence-manifest-v1.schema.json",
                "verification-receipt-v1.schema.json",
                "migration-receipt-v1.schema.json",
            )
            schemas = {
                name: json.loads((schema_root / name).read_text(encoding="utf-8")) for name in names
            }
            registry = Registry().with_resources(
                (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
            )
            values = {
                names[0]: manifest.artifacts[0].as_dict(),
                names[1]: manifest.as_dict(),
                names[2]: verification.as_dict(),
                names[3]: migration.as_dict(),
            }
            for name, value in values.items():
                with self.subTest(schema=name):
                    Draft202012Validator(schemas[name], registry=registry).validate(value)

    def test_cli_initializes_ingests_verifies_and_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "store"
            source = root / "capture.json"
            source.write_text('{"capture":true}\n', encoding="utf-8")
            manifest = root / "manifests" / "capture.json"
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(("evidence", "init", str(store), "--store-id", "cli-store", "--json"))
            self.assertEqual(0, result)
            self.assertEqual("cli-store", json.loads(output.getvalue())["store_id"])

            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    (
                        "evidence",
                        "ingest",
                        str(store),
                        str(manifest),
                        str(source),
                        "--kind",
                        "source_snapshot",
                        "--media-type",
                        "application/json",
                        "--case-id",
                        "cli-case",
                        "--json",
                    )
                )
            self.assertEqual(0, result)
            self.assertEqual(1, json.loads(output.getvalue())["artifact_count"])

            output = io.StringIO()
            with redirect_stdout(output):
                result = main(("evidence", "verify", str(store), str(manifest), "--json"))
            self.assertEqual(0, result)
            self.assertEqual("pass", json.loads(output.getvalue())["status"])

            index = root / "evidence.sqlite"
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    (
                        "evidence",
                        "rebuild-index",
                        str(manifest.parent),
                        str(index),
                        "--json",
                    )
                )
            self.assertEqual(0, result)
            self.assertEqual(1, json.loads(output.getvalue())["manifest_count"])


if __name__ == "__main__":
    unittest.main()
