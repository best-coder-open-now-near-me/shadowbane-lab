"""Read-only manifest verification."""

from __future__ import annotations

from shadowbane_lab.integrity import canonical_timestamp

from .model import ArtifactVerification, EvidenceManifest, VerificationReceipt
from .storage import ArtifactStore


def verify_manifest(
    store: ArtifactStore,
    manifest: EvidenceManifest,
    *,
    verifier_id: str = "shadowbane-lab",
    verifier_version: str = "0.1.0",
) -> VerificationReceipt:
    results: list[ArtifactVerification] = []
    for descriptor in manifest.artifacts:
        path = store.object_path(descriptor.artifact_id or "")
        present = path.is_file()
        size_matches = present and path.stat().st_size == descriptor.size_bytes
        digest_matches = False
        issue: str | None = None
        if present and size_matches:
            valid, issue = store.verify_descriptor(descriptor)
            digest_matches = valid
        elif not present:
            issue = "artifact object is missing"
        else:
            issue = "artifact size does not match descriptor"
        results.append(
            ArtifactVerification(
                artifact_id=descriptor.artifact_id or "",
                present=present,
                size_matches=size_matches,
                digest_matches=digest_matches,
                issue=issue,
            )
        )
    return VerificationReceipt(
        manifest_id=manifest.manifest_id or "",
        verified_at_utc=canonical_timestamp(),
        verifier_id=verifier_id,
        verifier_version=verifier_version,
        store_id=store.store_id,
        results=tuple(results),
    )


__all__ = ["verify_manifest"]
