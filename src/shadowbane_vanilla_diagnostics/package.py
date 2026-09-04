"""Self-verification for independently published vanilla diagnostic packages."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .model import PACKAGE_ID, PACKAGE_SCHEMA_VERSION

_EXECUTABLE_SUFFIXES = frozenset({".dll", ".exe", ".pyd", ".ps1", ".py", ".pyw"})
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "package_id",
        "package_version",
        "source_revision",
        "created_at_utc",
        "required_output_root",
        "allowed_executable_sha256",
        "files",
        "channels",
    }
)


class PackageVerificationError(ValueError):
    """Raised when a published package is incomplete, altered, or ambiguous."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_reparse(path: Path) -> bool:
    stat = path.lstat()
    attributes = getattr(stat, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse)


def _load_json_strict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageVerificationError(f"could not read package manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise PackageVerificationError("package manifest must be a JSON object")
    unknown = set(payload) - _MANIFEST_FIELDS
    missing = _MANIFEST_FIELDS - set(payload)
    if unknown:
        raise PackageVerificationError(
            f"package manifest has unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise PackageVerificationError(
            f"package manifest is missing fields: {', '.join(sorted(missing))}"
        )
    return payload


def verify_package(package_root: str | Path) -> dict[str, Any]:
    """Verify every executable package input and reject unmanifested code."""

    root = Path(package_root).resolve(strict=True)
    if not root.is_dir() or _is_reparse(root):
        raise PackageVerificationError("package root must be a regular directory")
    manifest_path = root / "package-manifest.json"
    if not manifest_path.is_file() or _is_reparse(manifest_path):
        raise PackageVerificationError("package-manifest.json is missing or is a reparse point")
    payload = _load_json_strict(manifest_path)
    if payload["schema_version"] != PACKAGE_SCHEMA_VERSION:
        raise PackageVerificationError("unsupported package manifest schema")
    if payload["package_id"] != PACKAGE_ID:
        raise PackageVerificationError("unexpected package identity")
    if not isinstance(payload["package_version"], str) or not payload["package_version"]:
        raise PackageVerificationError("package version must be non-empty text")
    revision = payload["source_revision"]
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or any(character not in "0123456789abcdef" for character in revision)
    ):
        raise PackageVerificationError("source revision must be a lowercase Git object ID")
    allowed = payload["allowed_executable_sha256"]
    if (
        not isinstance(allowed, list)
        or not allowed
        or any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in allowed
        )
    ):
        raise PackageVerificationError("allowed executable hashes are invalid")
    entries = payload["files"]
    if not isinstance(entries, list) or not entries:
        raise PackageVerificationError("package file inventory must be non-empty")

    expected_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "length", "sha256"}:
            raise PackageVerificationError("package file entry has an invalid shape")
        relative = entry["path"]
        if (
            not isinstance(relative, str)
            or not relative
            or "\\" in relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise PackageVerificationError("package file path is unsafe")
        canonical = relative.casefold()
        if canonical in expected_paths:
            raise PackageVerificationError("package file inventory has duplicate paths")
        expected_paths.add(canonical)
        candidate = root / relative
        if not candidate.is_file() or _is_reparse(candidate):
            raise PackageVerificationError(f"package file is missing or unsafe: {relative}")
        if candidate.stat().st_size != entry["length"]:
            raise PackageVerificationError(f"package file length mismatch: {relative}")
        if _sha256(candidate) != entry["sha256"]:
            raise PackageVerificationError(f"package file hash mismatch: {relative}")

    for directory, names, files in os.walk(root):
        names[:] = [name for name in names if name != "__pycache__"]
        base = Path(directory)
        for name in files:
            candidate = base / name
            relative = candidate.relative_to(root).as_posix()
            if relative == "package-manifest.json" or candidate.suffix.casefold() == ".pyc":
                continue
            if (
                candidate.suffix.casefold() in _EXECUTABLE_SUFFIXES
                and relative.casefold() not in expected_paths
            ):
                raise PackageVerificationError(f"unmanifested executable file: {relative}")
    return payload


__all__ = ["PackageVerificationError", "verify_package"]
