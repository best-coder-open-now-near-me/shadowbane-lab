"""Identifier, timestamp, digest, and path-boundary validation."""

from __future__ import annotations

import re
import stat
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


class PathSecurityError(ValueError):
    """Raised when a path crosses an approved filesystem boundary."""


def validate_identifier(value: object, field_name: str = "identifier") -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be 1-256 characters using letters, digits, dot, underscore, "
            "colon, or hyphen"
        )
    return value


def validate_sha256(value: object, field_name: str = "sha256") -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def canonical_timestamp(value: datetime | None = None) -> str:
    current = datetime.now(UTC) if value is None else value
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return current.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def validate_relative_path(value: object, field_name: str = "relative_path") -> str:
    if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
        raise ValueError(f"{field_name} must be a non-empty canonical POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix():
        raise ValueError(f"{field_name} must be a canonical POSIX relative path")
    if any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"{field_name} must not contain empty, dot, or parent segments")
    if any(part.endswith(".") or part.endswith(" ") for part in path.parts):
        raise ValueError(f"{field_name} contains a Windows-ambiguous segment")
    if any(":" in part for part in path.parts):
        raise ValueError(f"{field_name} must not contain drive or stream separators")
    return value


def is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError as exc:
        raise PathSecurityError(f"cannot inspect path: {path}: {exc}") from exc
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


def resolve_within_root(root: Path, relative_path: str) -> Path:
    validate_relative_path(relative_path)
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise PathSecurityError(f"cannot resolve root: {root}: {exc}") from exc
    candidate = resolved_root.joinpath(*PurePosixPath(relative_path).parts)
    current = resolved_root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.exists() and is_reparse_point(current):
            raise PathSecurityError(f"path crosses a reparse point: {current}")
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise PathSecurityError("path escapes the approved root")
    return candidate


__all__ = [
    "PathSecurityError",
    "canonical_timestamp",
    "is_reparse_point",
    "resolve_within_root",
    "validate_identifier",
    "validate_relative_path",
    "validate_sha256",
]
