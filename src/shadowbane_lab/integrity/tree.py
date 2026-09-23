"""Bounded immutable tree inventory and hashing."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .paths import is_reparse_point, validate_relative_path, validate_sha256


@dataclass(frozen=True, slots=True)
class FileRecord:
    relative_path: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        validate_relative_path(self.relative_path)
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise ValueError("file size must be a non-negative integer")
        validate_sha256(self.sha256)

    def as_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class TreeInventory:
    files: tuple[FileRecord, ...]
    total_bytes: int
    tree_sha256: str

    def __post_init__(self) -> None:
        paths = tuple(item.relative_path for item in self.files)
        if paths != tuple(sorted(paths, key=str.casefold)) or len(paths) != len(
            {path.casefold() for path in paths}
        ):
            raise ValueError("tree files must use unique case-insensitive canonical ordering")
        if self.total_bytes != sum(item.size for item in self.files):
            raise ValueError("tree total_bytes does not match file records")
        validate_sha256(self.tree_sha256, "tree_sha256")
        if self.tree_sha256 != tree_sha256(self.files):
            raise ValueError("tree_sha256 does not match file records")

    def as_dict(self) -> dict[str, object]:
        return {
            "file_count": len(self.files),
            "total_bytes": self.total_bytes,
            "tree_sha256": self.tree_sha256,
            "files": [item.as_dict() for item in self.files],
        }


def hash_file(path: Path, *, maximum_bytes: int | None = None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if maximum_bytes is not None and size > maximum_bytes:
                    raise ValueError(f"file exceeds configured byte limit: {path}")
                digest.update(chunk)
    except OSError as exc:
        raise ValueError(f"cannot hash file: {path}: {exc}") from exc
    return size, digest.hexdigest()


def inventory_tree(
    root: Path,
    *,
    maximum_files: int = 100_000,
    maximum_total_bytes: int = 64 * 1024 * 1024 * 1024,
    maximum_file_bytes: int = 16 * 1024 * 1024 * 1024,
    require_nonempty: bool = True,
) -> TreeInventory:
    for name, value in (
        ("maximum_files", maximum_files),
        ("maximum_total_bytes", maximum_total_bytes),
        ("maximum_file_bytes", maximum_file_bytes),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if not root.is_dir() or is_reparse_point(root):
        raise ValueError("tree root must be a regular directory without reparse indirection")
    files: list[Path] = []
    for path in root.rglob("*"):
        if is_reparse_point(path):
            raise ValueError(f"tree contains a reparse point: {path}")
        if path.is_file():
            files.append(path)
            if len(files) > maximum_files:
                raise ValueError("tree exceeds configured file-count limit")
        elif not path.is_dir():
            raise ValueError(f"tree contains an unsupported entry: {path}")
    files.sort(key=lambda item: item.relative_to(root).as_posix().casefold())
    if require_nonempty and not files:
        raise ValueError("tree contains no regular files")
    records: list[FileRecord] = []
    total = 0
    casefolded: set[str] = set()
    for path in files:
        relative_path = path.relative_to(root).as_posix()
        folded = relative_path.casefold()
        if folded in casefolded:
            raise ValueError(f"tree contains case-colliding paths: {relative_path}")
        casefolded.add(folded)
        size, digest = hash_file(path, maximum_bytes=maximum_file_bytes)
        total += size
        if total > maximum_total_bytes:
            raise ValueError("tree exceeds configured total byte limit")
        records.append(FileRecord(relative_path, size, digest))
    canonical_records = tuple(records)
    return TreeInventory(canonical_records, total, tree_sha256(canonical_records))


def tree_sha256(records: Iterable[FileRecord]) -> str:
    digest = hashlib.sha256()
    for item in records:
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item.size).encode("ascii"))
        digest.update(b"\0")
        digest.update(item.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


__all__ = ["FileRecord", "TreeInventory", "hash_file", "inventory_tree", "tree_sha256"]
