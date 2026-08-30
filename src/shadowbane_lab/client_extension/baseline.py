"""Immutable client-folder baseline capture for extension patch development."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from shadowbane_lab.client_alignment import PeImage, inspect_pe_bytes

CLIENT_BASELINE_SCHEMA_VERSION = 1
_BASELINE_FILE_NAME = "client-baseline.json"
_DEFAULT_MAX_FILES = 100_000
_DEFAULT_MAX_TOTAL_BYTES = 16 * 1024 * 1024 * 1024


class ClientBaselineError(RuntimeError):
    """Raised when a pristine client baseline cannot be captured safely."""


@dataclass(frozen=True, slots=True)
class BaselineFile:
    """One regular client file copied and verified into the frozen baseline."""

    relative_path: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        _validate_relative_path(self.relative_path)
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise ValueError("baseline file size must be a non-negative integer")
        _validate_sha256(self.sha256, "baseline file sha256")

    def as_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class ClientBaseline:
    """Evidence that one client tree was copied and reread without source mutation."""

    captured_at_utc: str
    repository_revision: str
    source_directory: str
    frozen_directory: str
    executable_relative_path: str
    tree_sha256: str
    files: tuple[BaselineFile, ...]
    executable: PeImage
    schema_version: int = CLIENT_BASELINE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CLIENT_BASELINE_SCHEMA_VERSION:
            raise ValueError("unsupported client baseline schema version")
        try:
            captured = datetime.fromisoformat(self.captured_at_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("captured_at_utc must be an ISO-8601 timestamp") from exc
        if captured.tzinfo is None:
            raise ValueError("captured_at_utc must include a timezone")
        if not isinstance(self.repository_revision, str) or not self.repository_revision:
            raise ValueError("repository_revision must be non-empty")
        for value, field_name in (
            (self.source_directory, "source_directory"),
            (self.frozen_directory, "frozen_directory"),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be non-empty")
        _validate_relative_path(self.executable_relative_path)
        _validate_sha256(self.tree_sha256, "tree_sha256")
        if not self.files:
            raise ValueError("client baseline must contain at least one file")
        if tuple(sorted(self.files, key=lambda item: item.relative_path.casefold())) != self.files:
            raise ValueError("client baseline files must use canonical sorted order")
        if len({item.relative_path.casefold() for item in self.files}) != len(self.files):
            raise ValueError("client baseline contains duplicate case-insensitive paths")
        if not isinstance(self.executable, PeImage):
            raise ValueError("executable must be inspected PE evidence")
        matches = tuple(
            item
            for item in self.files
            if item.relative_path.casefold() == self.executable_relative_path.casefold()
        )
        if len(matches) != 1 or matches[0].sha256 != self.executable.sha256:
            raise ValueError("executable evidence does not match the frozen file inventory")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "captured_at_utc": self.captured_at_utc,
            "repository_revision": self.repository_revision,
            "source_directory": self.source_directory,
            "frozen_directory": self.frozen_directory,
            "executable_relative_path": self.executable_relative_path,
            "tree_sha256": self.tree_sha256,
            "file_count": len(self.files),
            "total_file_bytes": sum(item.size for item in self.files),
            "files": [item.as_dict() for item in self.files],
            "executable": self.executable.as_dict(),
        }


def freeze_client_baseline(
    source_directory: str | Path,
    frozen_directory: str | Path,
    *,
    executable_relative_path: str = "sb.exe",
    repository_revision: str,
    captured_at: datetime | None = None,
    max_files: int = _DEFAULT_MAX_FILES,
    max_total_bytes: int = _DEFAULT_MAX_TOTAL_BYTES,
) -> ClientBaseline:
    """Copy, reread, and atomically publish one untouched client-folder baseline."""

    source = Path(source_directory).resolve()
    destination = Path(frozen_directory).resolve()
    executable_relative = _validate_relative_path(executable_relative_path)
    _validate_limits(max_files=max_files, max_total_bytes=max_total_bytes)
    if not source.is_dir():
        raise ClientBaselineError(f"client source directory does not exist: {source}")
    if destination.exists():
        raise ClientBaselineError(f"frozen baseline destination already exists: {destination}")
    if _is_within(destination, source) or _is_within(source, destination):
        raise ClientBaselineError(
            "source and frozen baseline directories must not contain each other"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)

    source_files = _inventory_paths(
        source,
        max_files=max_files,
        max_total_bytes=max_total_bytes,
    )
    executable_matches = tuple(
        path
        for path in source_files
        if path.relative_to(source).as_posix().casefold() == executable_relative.casefold()
    )
    if len(executable_matches) != 1:
        raise ClientBaselineError(
            f"client executable is not uniquely present: {executable_relative}"
        )

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=str(destination.parent))
    )
    published = False
    try:
        copied_files = _copy_inventory(source, temporary, source_files)
        reread_files = _hash_inventory(temporary, copied_files)
        executable_record = next(
            item
            for item in reread_files
            if item.relative_path.casefold() == executable_relative.casefold()
        )
        executable_data = (temporary / Path(executable_record.relative_path)).read_bytes()
        executable = inspect_pe_bytes(executable_data, path=executable_record.relative_path)
        if executable.sha256 != executable_record.sha256:
            raise ClientBaselineError("frozen executable changed during verification")
        baseline = ClientBaseline(
            captured_at_utc=_canonical_timestamp(captured_at),
            repository_revision=repository_revision,
            source_directory=str(source),
            frozen_directory=str(destination),
            executable_relative_path=executable_relative,
            tree_sha256=_tree_sha256(reread_files),
            files=reread_files,
            executable=executable,
        )
        _write_new_json(temporary / _BASELINE_FILE_NAME, baseline.as_dict())
        os.replace(temporary, destination)
        published = True
        return baseline
    except ClientBaselineError:
        raise
    except (OSError, ValueError) as exc:
        raise ClientBaselineError(f"could not freeze client baseline: {exc}") from exc
    finally:
        if not published:
            shutil.rmtree(temporary, ignore_errors=True)


def _validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ValueError("relative path must be a non-empty POSIX-style path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("relative path must remain beneath the client root")
    canonical = path.as_posix()
    if canonical != value:
        raise ValueError("relative path must be canonical POSIX form")
    return canonical


def _validate_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.casefold()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be lowercase hexadecimal SHA-256")


def _validate_limits(*, max_files: int, max_total_bytes: int) -> None:
    for value, field_name in ((max_files, "max_files"), (max_total_bytes, "max_total_bytes")):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{field_name} must be a positive integer")


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def _inventory_paths(root: Path, *, max_files: int, max_total_bytes: int) -> tuple[Path, ...]:
    files: list[Path] = []
    total_bytes = 0
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(directory)
        directory_names.sort(key=str.casefold)
        file_names.sort(key=str.casefold)
        for name in tuple(directory_names):
            path = current / name
            if _is_reparse_point(path):
                raise ClientBaselineError(f"client tree contains a reparse directory: {path}")
        for name in file_names:
            path = current / name
            if _is_reparse_point(path) or not path.is_file():
                raise ClientBaselineError(f"client tree contains a non-regular file: {path}")
            size = path.stat().st_size
            total_bytes += size
            files.append(path)
            if len(files) > max_files:
                raise ClientBaselineError("client tree exceeds the configured file-count limit")
            if total_bytes > max_total_bytes:
                raise ClientBaselineError("client tree exceeds the configured byte limit")
    files.sort(key=lambda path: path.relative_to(root).as_posix().casefold())
    if not files:
        raise ClientBaselineError("client source directory contains no regular files")
    return tuple(files)


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def _copy_inventory(source: Path, destination: Path, files: tuple[Path, ...]) -> tuple[Path, ...]:
    copied: list[Path] = []
    for source_path in files:
        relative = source_path.relative_to(source)
        destination_path = destination / relative
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        copied.append(destination_path)
    return tuple(copied)


def _hash_inventory(root: Path, files: tuple[Path, ...]) -> tuple[BaselineFile, ...]:
    results = []
    for path in files:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
        results.append(
            BaselineFile(
                relative_path=path.relative_to(root).as_posix(),
                size=size,
                sha256=digest.hexdigest(),
            )
        )
    results.sort(key=lambda item: item.relative_path.casefold())
    return tuple(results)


def _tree_sha256(files: tuple[BaselineFile, ...]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item.size).encode("ascii"))
        digest.update(b"\0")
        digest.update(item.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _canonical_timestamp(value: datetime | None) -> str:
    current = datetime.now(UTC) if value is None else value
    if current.tzinfo is None:
        raise ValueError("captured_at must include a timezone")
    return current.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    )
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.write("\n")


__all__ = [
    "CLIENT_BASELINE_SCHEMA_VERSION",
    "BaselineFile",
    "ClientBaseline",
    "ClientBaselineError",
    "freeze_client_baseline",
]
