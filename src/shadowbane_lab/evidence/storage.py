"""Filesystem-backed immutable content-addressed evidence storage."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from shadowbane_lab.integrity import (
    create_only_json,
    hash_file,
    is_reparse_point,
    load_strict_json,
    validate_identifier,
)

from .model import (
    ArtifactDescriptor,
    ArtifactKind,
    EvidenceError,
    Redaction,
    RedactionState,
    parse_artifact_id,
)

STORE_SCHEMA_VERSION = 1
DEFAULT_MAXIMUM_ARTIFACT_BYTES = 16 * 1024 * 1024 * 1024


class ArtifactStore:
    """One immutable object namespace with create-only content placement."""

    def __init__(
        self, root: str | Path, *, maximum_artifact_bytes: int = DEFAULT_MAXIMUM_ARTIFACT_BYTES
    ):
        self.root = Path(root).resolve(strict=False)
        if (
            isinstance(maximum_artifact_bytes, bool)
            or not isinstance(maximum_artifact_bytes, int)
            or maximum_artifact_bytes <= 0
        ):
            raise ValueError("maximum_artifact_bytes must be a positive integer")
        self.maximum_artifact_bytes = maximum_artifact_bytes
        config = self.root / "store.json"
        try:
            payload = load_strict_json(config)
        except ValueError as exc:
            raise EvidenceError(f"invalid evidence store configuration: {exc}") from exc
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version",
            "store_id",
            "object_layout",
        }:
            raise EvidenceError("evidence store configuration fields are not exact")
        if payload["schema_version"] != STORE_SCHEMA_VERSION:
            raise EvidenceError("unsupported evidence store schema version")
        if payload["object_layout"] != "sha256-v1":
            raise EvidenceError("unsupported evidence object layout")
        self.store_id = validate_identifier(payload["store_id"], "store_id")
        for directory in (self.objects_directory, self.staging_directory):
            if not directory.is_dir() or is_reparse_point(directory):
                raise EvidenceError(
                    f"evidence store directory is unavailable or unsafe: {directory}"
                )

    @classmethod
    def initialize(cls, root: str | Path, *, store_id: str | None = None) -> ArtifactStore:
        target = Path(root).resolve(strict=False)
        if target.exists() and any(target.iterdir()):
            raise EvidenceError(f"evidence store destination is not empty: {target}")
        target.mkdir(parents=True, exist_ok=True)
        if is_reparse_point(target):
            raise EvidenceError("evidence store root cannot be a reparse point")
        identifier = store_id or f"store-{uuid.uuid4().hex}"
        validate_identifier(identifier, "store_id")
        (target / "objects" / "sha256").mkdir(parents=True)
        (target / "staging").mkdir()
        create_only_json(
            target / "store.json",
            {
                "schema_version": STORE_SCHEMA_VERSION,
                "store_id": identifier,
                "object_layout": "sha256-v1",
            },
        )
        return cls(target)

    @property
    def objects_directory(self) -> Path:
        return self.root / "objects" / "sha256"

    @property
    def staging_directory(self) -> Path:
        return self.root / "staging"

    def object_path(self, artifact_id: str) -> Path:
        digest = parse_artifact_id(artifact_id)[7:]
        return self.objects_directory / digest[:2] / digest[2:]

    def ingest_bytes(
        self,
        payload: bytes,
        *,
        artifact_kind: ArtifactKind,
        media_type: str,
        logical_name: str,
        producer_id: str,
        producer_version: str,
        captured_at_utc: str | None = None,
        redaction: Redaction | None = None,
        parents: Iterable[str] = (),
        metadata: Iterable[tuple[str, object]] = (),
    ) -> ArtifactDescriptor:
        if not isinstance(payload, bytes):
            raise TypeError("artifact payload must be bytes")
        if len(payload) > self.maximum_artifact_bytes:
            raise EvidenceError("artifact exceeds the configured byte limit")
        descriptor, stage = self._stage_stream(
            _BytesReader(payload),
            artifact_kind=artifact_kind,
            media_type=media_type,
            logical_name=logical_name,
            producer_id=producer_id,
            producer_version=producer_version,
            captured_at_utc=captured_at_utc,
            redaction=redaction,
            parents=parents,
            metadata=metadata,
        )
        self._publish_stage(stage, descriptor)
        return descriptor

    def ingest_file(
        self,
        source: str | Path,
        *,
        artifact_kind: ArtifactKind,
        media_type: str,
        logical_name: str | None = None,
        producer_id: str,
        producer_version: str,
        captured_at_utc: str | None = None,
        redaction: Redaction | None = None,
        parents: Iterable[str] = (),
        metadata: Iterable[tuple[str, object]] = (),
    ) -> ArtifactDescriptor:
        path = Path(source)
        if not path.is_file() or is_reparse_point(path):
            raise EvidenceError(f"artifact source must be a regular file: {path}")
        try:
            with path.open("rb") as stream:
                descriptor, stage = self._stage_stream(
                    stream,
                    artifact_kind=artifact_kind,
                    media_type=media_type,
                    logical_name=logical_name or path.name,
                    producer_id=producer_id,
                    producer_version=producer_version,
                    captured_at_utc=captured_at_utc,
                    redaction=redaction,
                    parents=parents,
                    metadata=metadata,
                )
        except OSError as exc:
            raise EvidenceError(f"could not read artifact source: {path}: {exc}") from exc
        self._publish_stage(stage, descriptor)
        return descriptor

    def verify_descriptor(self, descriptor: ArtifactDescriptor) -> tuple[bool, str | None]:
        path = self.object_path(descriptor.artifact_id or "")
        if not path.is_file() or is_reparse_point(path):
            return False, "artifact object is missing or unsafe"
        try:
            size, digest = hash_file(path, maximum_bytes=self.maximum_artifact_bytes)
        except ValueError as exc:
            return False, str(exc)
        if size != descriptor.size_bytes:
            return False, "artifact size does not match descriptor"
        if digest != descriptor.sha256:
            return False, "artifact digest does not match descriptor"
        return True, None

    def open_artifact(self, artifact_id: str) -> BinaryIO:
        path = self.object_path(artifact_id)
        if not path.is_file() or is_reparse_point(path):
            raise EvidenceError(f"artifact object is unavailable or unsafe: {artifact_id}")
        return path.open("rb")

    def quarantine_inventory(self) -> tuple[dict[str, object], ...]:
        records: list[dict[str, object]] = []
        for path in sorted(self.staging_directory.iterdir(), key=lambda item: item.name):
            if not path.is_file() or is_reparse_point(path):
                records.append({"name": path.name, "safe": False, "size_bytes": None})
                continue
            records.append({"name": path.name, "safe": True, "size_bytes": path.stat().st_size})
        return tuple(records)

    def _stage_stream(
        self,
        stream: BinaryIO,
        *,
        artifact_kind: ArtifactKind,
        media_type: str,
        logical_name: str,
        producer_id: str,
        producer_version: str,
        captured_at_utc: str | None,
        redaction: Redaction | None,
        parents: Iterable[str],
        metadata: Iterable[tuple[str, object]],
    ) -> tuple[ArtifactDescriptor, Path]:
        descriptor_fd, name = tempfile.mkstemp(
            prefix="artifact-", suffix=".stage", dir=self.staging_directory
        )
        stage = Path(name)
        digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(descriptor_fd, "wb") as destination:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.maximum_artifact_bytes:
                        raise EvidenceError("artifact exceeds the configured byte limit")
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            descriptor = ArtifactDescriptor(
                sha256=digest.hexdigest(),
                size_bytes=size,
                media_type=media_type,
                artifact_kind=artifact_kind,
                logical_name=logical_name,
                producer_id=producer_id,
                producer_version=producer_version,
                captured_at_utc=captured_at_utc,
                redaction=redaction or Redaction(RedactionState.NOT_REQUIRED),
                parents=tuple(sorted(set(parents))),
                metadata=tuple(sorted(metadata)),
            )
            reread_size, reread_digest = hash_file(stage, maximum_bytes=self.maximum_artifact_bytes)
            if reread_size != descriptor.size_bytes or reread_digest != descriptor.sha256:
                raise EvidenceError("staged artifact changed during verification")
            return descriptor, stage
        except Exception:
            stage.unlink(missing_ok=True)
            raise

    def _publish_stage(self, stage: Path, descriptor: ArtifactDescriptor) -> None:
        target = self.object_path(descriptor.artifact_id or "")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(stage, target)
        except FileExistsError as exc:
            valid, issue = self.verify_descriptor(descriptor)
            if not valid:
                raise EvidenceError(f"existing artifact object is corrupt: {issue}") from exc
        except OSError as exc:
            raise EvidenceError(f"could not publish artifact object: {exc}") from exc
        finally:
            stage.unlink(missing_ok=True)
        valid, issue = self.verify_descriptor(descriptor)
        if not valid:
            raise EvidenceError(f"published artifact verification failed: {issue}")


class _BytesReader:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._offset = 0

    def read(self, size: int) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        result = self._payload[self._offset : self._offset + size]
        self._offset += len(result)
        return result


def copy_artifact(store: ArtifactStore, artifact_id: str, destination: Path) -> None:
    if destination.exists():
        raise EvidenceError(f"artifact export destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with store.open_artifact(artifact_id) as source, destination.open("xb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
        target.flush()
        os.fsync(target.fileno())


__all__ = [
    "DEFAULT_MAXIMUM_ARTIFACT_BYTES",
    "STORE_SCHEMA_VERSION",
    "ArtifactStore",
    "copy_artifact",
]
