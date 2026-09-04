"""Portable verified evidence bundles."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from shadowbane_lab.integrity import canonical_json_bytes, strict_json_loads

from .codec import parse_manifest
from .model import EvidenceError, EvidenceManifest
from .storage import ArtifactStore

BUNDLE_SCHEMA_VERSION = 1


def create_bundle(
    store: ArtifactStore,
    manifest: EvidenceManifest,
    destination: str | Path,
) -> Path:
    output = Path(destination)
    if output.exists():
        raise EvidenceError(f"bundle destination already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output, mode="x", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("bundle.json", _bundle_index(manifest))
            archive.writestr("manifest.json", canonical_json_bytes(manifest.as_dict()))
            for descriptor in manifest.artifacts:
                path = store.object_path(descriptor.artifact_id or "")
                valid, issue = store.verify_descriptor(descriptor)
                if not valid:
                    raise EvidenceError(
                        f"cannot bundle unverified artifact {descriptor.artifact_id}: {issue}"
                    )
                archive.write(path, _bundle_object_name(descriptor.sha256))
    except Exception:
        output.unlink(missing_ok=True)
        raise
    verify_bundle(output)
    return output


def verify_bundle(path: str | Path) -> EvidenceManifest:
    source = Path(path)
    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise EvidenceError("bundle contains duplicate member names")
            if "bundle.json" not in names or "manifest.json" not in names:
                raise EvidenceError("bundle is missing its index or manifest")
            index = strict_json_loads(archive.read("bundle.json"))
            manifest = parse_manifest(strict_json_loads(archive.read("manifest.json")))
            expected_names = {
                "bundle.json",
                "manifest.json",
                *(_bundle_object_name(item.sha256) for item in manifest.artifacts),
            }
            if set(names) != expected_names:
                raise EvidenceError("bundle members do not match the manifest")
            if index != strict_json_loads(_bundle_index(manifest)):
                raise EvidenceError("bundle index does not match the manifest")
            for descriptor in manifest.artifacts:
                data = archive.read(_bundle_object_name(descriptor.sha256))
                if len(data) != descriptor.size_bytes:
                    raise EvidenceError(f"bundle artifact size mismatch: {descriptor.artifact_id}")
                if hashlib.sha256(data).hexdigest() != descriptor.sha256:
                    raise EvidenceError(
                        f"bundle artifact digest mismatch: {descriptor.artifact_id}"
                    )
            return manifest
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid evidence bundle: {exc}") from exc


def _bundle_index(manifest: EvidenceManifest) -> bytes:
    return canonical_json_bytes(
        {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "manifest_id": manifest.manifest_id,
            "artifact_ids": [item.artifact_id for item in manifest.artifacts],
        }
    )


def _bundle_object_name(digest: str) -> str:
    return f"objects/sha256/{digest[:2]}/{digest[2:]}"


__all__ = ["BUNDLE_SCHEMA_VERSION", "create_bundle", "verify_bundle"]
