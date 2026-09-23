"""Strict manifest for omitting reviewed files from a disposable client copy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shadowbane_lab.client_extension.baseline import BaselineFile

BASELINE_EXCLUSION_SCHEMA_VERSION = 1
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_EXCLUDED_FILES = 32


class BaselineExclusionError(RuntimeError):
    """Raised when a baseline-exclusion manifest is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class BaselineExclusionManifest:
    """Hash-pinned files intentionally absent from one disposable package."""

    profile_id: str
    files: tuple[BaselineFile, ...]
    schema_version: int = BASELINE_EXCLUSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != BASELINE_EXCLUSION_SCHEMA_VERSION:
            raise ValueError("unsupported baseline-exclusion schema version")
        if (
            not isinstance(self.profile_id, str)
            or not self.profile_id
            or len(self.profile_id) > 128
            or not self.profile_id.isascii()
        ):
            raise ValueError("profile_id must be non-empty ASCII text of at most 128 characters")
        if not self.files:
            raise ValueError("baseline-exclusion manifest must contain at least one file")
        if len(self.files) > _MAX_EXCLUDED_FILES:
            raise ValueError("baseline-exclusion manifest exceeds the file-count limit")
        if tuple(sorted(self.files, key=lambda item: item.relative_path.casefold())) != self.files:
            raise ValueError("excluded files must use canonical sorted order")
        if len({item.relative_path.casefold() for item in self.files}) != len(self.files):
            raise ValueError("excluded files contain duplicate case-insensitive paths")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "file_count": len(self.files),
            "files": [item.as_dict() for item in self.files],
        }


def load_baseline_exclusion_manifest(path: str | Path) -> BaselineExclusionManifest:
    manifest_path = Path(path)
    try:
        data = manifest_path.read_bytes()
    except OSError as exc:
        raise BaselineExclusionError(
            f"could not read baseline-exclusion manifest: {manifest_path}"
        ) from exc
    if len(data) > _MAX_MANIFEST_BYTES:
        raise BaselineExclusionError("baseline-exclusion manifest exceeds the byte limit")
    try:
        payload = json.loads(
            data.decode("utf-8-sig"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BaselineExclusionError("baseline-exclusion manifest is not valid JSON") from exc
    return parse_baseline_exclusion_manifest(payload)


def parse_baseline_exclusion_manifest(value: object) -> BaselineExclusionManifest:
    if not isinstance(value, dict):
        raise BaselineExclusionError("baseline-exclusion manifest must be a JSON object")
    _fields(value, {"schema_version", "profile_id", "file_count", "files"})
    raw_files = value["files"]
    if not isinstance(raw_files, list):
        raise BaselineExclusionError("baseline-exclusion files must be an array")
    files: list[BaselineFile] = []
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise BaselineExclusionError("baseline-exclusion file must be an object")
        _fields(raw, {"relative_path", "size", "sha256"})
        try:
            files.append(
                BaselineFile(
                    relative_path=raw["relative_path"],  # type: ignore[arg-type]
                    size=raw["size"],  # type: ignore[arg-type]
                    sha256=raw["sha256"],  # type: ignore[arg-type]
                )
            )
        except ValueError as exc:
            raise BaselineExclusionError(f"invalid excluded file: {exc}") from exc
    if isinstance(value["file_count"], bool) or value["file_count"] != len(files):
        raise BaselineExclusionError("baseline-exclusion file_count does not match files")
    try:
        return BaselineExclusionManifest(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            profile_id=value["profile_id"],  # type: ignore[arg-type]
            files=tuple(files),
        )
    except ValueError as exc:
        raise BaselineExclusionError(f"invalid baseline-exclusion manifest: {exc}") from exc


def _fields(payload: dict[str, object], expected: set[str]) -> None:
    missing = expected - payload.keys()
    unknown = payload.keys() - expected
    if missing:
        raise BaselineExclusionError(
            f"baseline-exclusion manifest is missing fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise BaselineExclusionError(
            f"baseline-exclusion manifest has unknown fields: {', '.join(sorted(unknown))}"
        )


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BaselineExclusionError(
                f"baseline-exclusion manifest contains duplicate field: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise BaselineExclusionError(
        f"baseline-exclusion manifest contains forbidden JSON constant: {value}"
    )


__all__ = [
    "BASELINE_EXCLUSION_SCHEMA_VERSION",
    "BaselineExclusionError",
    "BaselineExclusionManifest",
    "load_baseline_exclusion_manifest",
    "parse_baseline_exclusion_manifest",
]
