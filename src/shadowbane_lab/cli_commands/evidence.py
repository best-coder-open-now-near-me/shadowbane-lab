"""Evidence-store, manifest, verification, bundle, and index commands."""

from __future__ import annotations

import json
from argparse import Namespace

from shadowbane_lab.evidence import (
    ArtifactKind,
    ArtifactStore,
    EvidenceError,
    EvidenceManifest,
    ManifestTerminalState,
    VerificationStatus,
    create_bundle,
    import_legacy_files,
    load_manifest,
    query_index,
    rebuild_index,
    save_contract,
    verify_manifest,
)
from shadowbane_lab.integrity import canonical_timestamp

from .common import _error


def handle(arguments: Namespace) -> int:
    as_json = bool(getattr(arguments, "json", False))
    try:
        if arguments.evidence_command == "init":
            store = ArtifactStore.initialize(arguments.store, store_id=arguments.store_id)
            return _result(
                {"ok": True, "store_id": store.store_id, "store": str(store.root)},
                as_json=as_json,
            )
        if arguments.evidence_command == "ingest":
            store = ArtifactStore(arguments.store)
            captured = canonical_timestamp()
            descriptors = tuple(
                sorted(
                    (
                        store.ingest_file(
                            path,
                            artifact_kind=ArtifactKind(arguments.kind),
                            media_type=arguments.media_type,
                            producer_id=arguments.producer_id,
                            producer_version=arguments.producer_version,
                            captured_at_utc=captured,
                        )
                        for path in arguments.files
                    ),
                    key=lambda item: item.artifact_id or "",
                )
            )
            manifest = EvidenceManifest(
                created_at_utc=captured,
                artifacts=descriptors,
                terminal_state=ManifestTerminalState.COMPLETE,
                case_id=arguments.case_id,
                run_id=arguments.run_id,
            )
            save_contract(arguments.output, manifest)
            return _result(
                {
                    "ok": True,
                    "manifest_id": manifest.manifest_id,
                    "artifact_count": len(descriptors),
                    "output": str(arguments.output),
                },
                as_json=as_json,
            )
        if arguments.evidence_command == "verify":
            store = ArtifactStore(arguments.store)
            manifest = load_manifest(arguments.manifest)
            receipt = verify_manifest(store, manifest)
            if arguments.output is not None:
                save_contract(arguments.output, receipt)
            payload = {
                "ok": receipt.status is VerificationStatus.PASS,
                "status": receipt.status.value,
                "manifest_id": receipt.manifest_id,
                "receipt_id": receipt.receipt_id,
                "results": [item.as_dict() for item in receipt.results],
                "output": None if arguments.output is None else str(arguments.output),
            }
            _result(payload, as_json=as_json)
            return 0 if receipt.status is VerificationStatus.PASS else 1
        if arguments.evidence_command == "bundle":
            store = ArtifactStore(arguments.store)
            manifest = load_manifest(arguments.manifest)
            output = create_bundle(store, manifest, arguments.output)
            return _result(
                {"ok": True, "manifest_id": manifest.manifest_id, "output": str(output)},
                as_json=as_json,
            )
        if arguments.evidence_command == "rebuild-index":
            count = rebuild_index(arguments.manifest_directory, arguments.index)
            return _result(
                {"ok": True, "manifest_count": count, "index": str(arguments.index)},
                as_json=as_json,
            )
        if arguments.evidence_command == "query":
            rows = query_index(
                arguments.index,
                artifact_kind=arguments.kind,
                case_id=arguments.case_id,
                run_id=arguments.run_id,
                limit=arguments.limit,
            )
            return _result(
                {"ok": True, "count": len(rows), "results": list(rows)},
                as_json=as_json,
            )
        if arguments.evidence_command == "import-legacy":
            store = ArtifactStore(arguments.store)
            manifest, receipt = import_legacy_files(
                store,
                arguments.files,
                artifact_kind=ArtifactKind(arguments.kind),
                media_type=arguments.media_type,
                importer_id=arguments.importer_id,
                importer_version=arguments.importer_version,
                case_id=arguments.case_id,
                run_id=arguments.run_id,
            )
            save_contract(arguments.manifest_output, manifest)
            save_contract(arguments.receipt_output, receipt)
            return _result(
                {
                    "ok": True,
                    "manifest_id": manifest.manifest_id,
                    "receipt_id": receipt.receipt_id,
                    "manifest_output": str(arguments.manifest_output),
                    "receipt_output": str(arguments.receipt_output),
                },
                as_json=as_json,
            )
    except (EvidenceError, OSError, TypeError, ValueError) as exc:
        return _error(str(exc), as_json=as_json)
    return _error("unknown evidence command", as_json=as_json)


def _result(payload: dict[str, object], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, allow_nan=False, sort_keys=True))
    else:
        for name, value in payload.items():
            if name != "ok":
                print(f"{name}: {value}")
    return 0


__all__ = ["handle"]
