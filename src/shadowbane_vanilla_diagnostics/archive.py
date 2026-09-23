"""Deterministic, shareable archives for sealed portable capture directories."""

from __future__ import annotations

import hashlib
import os
import uuid
import zipfile
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_create_new(path: Path, source: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        offset = 0
        while offset < len(source):
            offset += os.write(descriptor, source[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_portable_archive(run_directory: Path) -> tuple[Path, Path]:
    """Archive one sealed run and emit a sidecar SHA-256 without overwriting."""

    source = run_directory.resolve(strict=True)
    if not source.is_dir() or not (source / "capture-complete.json").is_file():
        raise ValueError("portable archive input must be one sealed capture directory")
    archive = source.parent / f"{source.name}.zip"
    checksum = source.parent / f"{source.name}.zip.sha256"
    if archive.exists() or checksum.exists():
        raise FileExistsError("portable capture archive already exists")
    staging = source.parent / f".{source.name}.{uuid.uuid4().hex}.writing.zip"
    try:
        with zipfile.ZipFile(
            staging,
            mode="x",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as bundle:
            for candidate in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
                if candidate.is_file():
                    bundle.write(candidate, candidate.relative_to(source).as_posix())
        staging.rename(archive)
        digest = _sha256(archive)
        _write_create_new(checksum, f"{digest}  {archive.name}\n".encode("ascii"))
    finally:
        if staging.exists():
            staging.unlink()
    return archive, checksum


__all__ = ["create_portable_archive"]
