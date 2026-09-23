"""Non-destructive import of existing evidence files."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from shadowbane_lab.integrity import canonical_timestamp

from .model import (
    ArtifactKind,
    EvidenceManifest,
    ManifestTerminalState,
    MigrationReceipt,
)
from .storage import ArtifactStore


def import_legacy_files(
    store: ArtifactStore,
    paths: Iterable[str | Path],
    *,
    artifact_kind: ArtifactKind,
    media_type: str,
    importer_id: str = "shadowbane-lab.legacy-import",
    importer_version: str = "0.1.0",
    case_id: str | None = None,
    run_id: str | None = None,
) -> tuple[EvidenceManifest, MigrationReceipt]:
    resolved = tuple(sorted((Path(path) for path in paths), key=lambda item: str(item).casefold()))
    if not resolved:
        raise ValueError("legacy import requires at least one source path")
    if len({path.name for path in resolved}) != len(resolved):
        raise ValueError("legacy source labels collide; import files in separate manifests")
    captured = canonical_timestamp()
    descriptors = tuple(
        store.ingest_file(
            path,
            artifact_kind=artifact_kind,
            media_type=media_type,
            producer_id=importer_id,
            producer_version=importer_version,
            captured_at_utc=captured,
            logical_name=path.name,
            metadata=(("legacy_source_label", path.name),),
        )
        for path in resolved
    )
    manifest = EvidenceManifest(
        created_at_utc=captured,
        artifacts=tuple(sorted(descriptors, key=lambda item: item.artifact_id or "")),
        terminal_state=ManifestTerminalState.IMPORTED,
        case_id=case_id,
        run_id=run_id,
    )
    receipt = MigrationReceipt(
        imported_at_utc=captured,
        importer_id=importer_id,
        importer_version=importer_version,
        source_labels=tuple(sorted(path.name for path in resolved)),
        source_artifact_ids=tuple(sorted(item.artifact_id or "" for item in descriptors)),
        manifest_id=manifest.manifest_id or "",
    )
    return manifest, receipt


__all__ = ["import_legacy_files"]
