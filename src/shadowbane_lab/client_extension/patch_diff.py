"""Verified, content-free evidence for official client patch differences."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from shadowbane_lab.client_alignment import (
    ClientAlignmentError,
    ClientAlignmentReport,
    compare_client_builds,
)
from shadowbane_lab.client_extension.package import (
    ClientPatchPackageError,
    VerifiedClientBaseline,
    verify_frozen_client_baseline,
)
from shadowbane_lab.world_data.cache import CacheArchive, CacheArchiveFormatError

CLIENT_PATCH_DIFF_SCHEMA_VERSION = 1
_BASELINE_FILE_NAME = "client-baseline.json"
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")

FileChangeKind = Literal["added", "removed", "modified", "renamed"]
ResourceChangeKind = Literal["added", "removed", "modified", "repacked"]


class ClientPatchDiffError(RuntimeError):
    """Raised when two frozen client releases cannot be compared safely."""


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    size: int
    sha256: str

    def __post_init__(self) -> None:
        _non_negative_integer(self.size, "file size")
        _sha256(self.sha256, "file sha256")

    def as_dict(self) -> dict[str, object]:
        return {"size": self.size, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class ClientTreeIdentity:
    directory: str
    repository_revision: str
    baseline_evidence_sha256: str
    tree_sha256: str
    executable_relative_path: str
    executable_sha256: str
    file_count: int
    total_file_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.directory, str) or not self.directory:
            raise ValueError("client tree directory must be non-empty")
        if not isinstance(self.repository_revision, str) or not self.repository_revision:
            raise ValueError("repository_revision must be non-empty")
        _sha256(self.baseline_evidence_sha256, "baseline_evidence_sha256")
        _sha256(self.tree_sha256, "tree_sha256")
        _relative_path(self.executable_relative_path)
        _sha256(self.executable_sha256, "executable_sha256")
        _positive_integer(self.file_count, "file_count")
        _non_negative_integer(self.total_file_bytes, "total_file_bytes")

    def as_dict(self) -> dict[str, object]:
        return {
            "directory": self.directory,
            "repository_revision": self.repository_revision,
            "baseline_evidence_sha256": self.baseline_evidence_sha256,
            "tree_sha256": self.tree_sha256,
            "executable_relative_path": self.executable_relative_path,
            "executable_sha256": self.executable_sha256,
            "file_count": self.file_count,
            "total_file_bytes": self.total_file_bytes,
        }


@dataclass(frozen=True, slots=True)
class PatchFileChange:
    kind: FileChangeKind
    before_path: str | None
    before: FileFingerprint | None
    after_path: str | None
    after: FileFingerprint | None

    def __post_init__(self) -> None:
        if self.kind not in {"added", "removed", "modified", "renamed"}:
            raise ValueError("unsupported file change kind")
        if self.before_path is not None:
            _relative_path(self.before_path)
        if self.after_path is not None:
            _relative_path(self.after_path)
        if (self.before_path is None) != (self.before is None):
            raise ValueError("before path and fingerprint must either both be present or absent")
        if (self.after_path is None) != (self.after is None):
            raise ValueError("after path and fingerprint must either both be present or absent")
        if self.kind == "added" and (self.before is not None or self.after is None):
            raise ValueError("added files require only an after value")
        if self.kind == "removed" and (self.before is None or self.after is not None):
            raise ValueError("removed files require only a before value")
        if self.kind in {"modified", "renamed"} and (
            self.before is None or self.after is None
        ):
            raise ValueError(f"{self.kind} files require before and after values")
        if self.kind == "modified":
            assert self.before_path is not None and self.after_path is not None
            assert self.before is not None and self.after is not None
            if self.before_path.casefold() != self.after_path.casefold():
                raise ValueError("modified files must retain their case-insensitive path")
            if self.before == self.after:
                raise ValueError("modified files must have different fingerprints")
        if self.kind == "renamed":
            assert self.before_path is not None and self.after_path is not None
            assert self.before is not None and self.after is not None
            if self.before_path == self.after_path:
                raise ValueError("renamed files must change path")
            if self.before != self.after:
                raise ValueError("renamed files must retain their exact fingerprint")

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "before": _file_side(self.before_path, self.before),
            "after": _file_side(self.after_path, self.after),
        }


@dataclass(frozen=True, slots=True)
class CacheResourceFingerprint:
    uncompressed_size: int
    stored_size: int
    compressed: bool
    payload_sha256: str

    def __post_init__(self) -> None:
        _non_negative_integer(self.uncompressed_size, "resource uncompressed_size")
        _non_negative_integer(self.stored_size, "resource stored_size")
        if not isinstance(self.compressed, bool):
            raise ValueError("resource compressed must be boolean")
        if self.compressed != (self.uncompressed_size != self.stored_size):
            raise ValueError("resource compression flag disagrees with its sizes")
        _sha256(self.payload_sha256, "resource payload_sha256")

    @property
    def logical_identity(self) -> tuple[int, str]:
        return self.uncompressed_size, self.payload_sha256

    def as_dict(self) -> dict[str, object]:
        return {
            "uncompressed_size": self.uncompressed_size,
            "stored_size": self.stored_size,
            "compressed": self.compressed,
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True, slots=True)
class CacheResourceChange:
    kind: ResourceChangeKind
    group_id: int
    resource_id: int
    before: CacheResourceFingerprint | None
    after: CacheResourceFingerprint | None

    def __post_init__(self) -> None:
        if self.kind not in {"added", "removed", "modified", "repacked"}:
            raise ValueError("unsupported cache resource change kind")
        _unsigned_integer(self.group_id, "group_id")
        _unsigned_integer(self.resource_id, "resource_id")
        if self.kind == "added" and (self.before is not None or self.after is None):
            raise ValueError("added resources require only an after value")
        if self.kind == "removed" and (self.before is None or self.after is not None):
            raise ValueError("removed resources require only a before value")
        if self.kind in {"modified", "repacked"} and (
            self.before is None or self.after is None
        ):
            raise ValueError(f"{self.kind} resources require before and after values")
        if self.kind == "modified":
            assert self.before is not None and self.after is not None
            if self.before.logical_identity == self.after.logical_identity:
                raise ValueError("modified resources must change logical payload")
        if self.kind == "repacked":
            assert self.before is not None and self.after is not None
            if self.before.logical_identity != self.after.logical_identity:
                raise ValueError("repacked resources must retain logical payload")
            if self.before == self.after:
                raise ValueError("repacked resources must change storage representation")

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "group_id": self.group_id,
            "resource_id": self.resource_id,
            "before": None if self.before is None else self.before.as_dict(),
            "after": None if self.after is None else self.after.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class CacheArchiveDiff:
    relative_path: str
    source_resource_count: int
    target_resource_count: int
    unchanged_resource_count: int
    changes: tuple[CacheResourceChange, ...]

    def __post_init__(self) -> None:
        _relative_path(self.relative_path)
        if PurePosixPath(self.relative_path).suffix.casefold() != ".cache":
            raise ValueError("cache archive diff must name a .cache file")
        for value, field_name in (
            (self.source_resource_count, "source_resource_count"),
            (self.target_resource_count, "target_resource_count"),
            (self.unchanged_resource_count, "unchanged_resource_count"),
        ):
            _non_negative_integer(value, field_name)
        if tuple(sorted(self.changes, key=_resource_change_key)) != self.changes:
            raise ValueError("cache resource changes must use canonical key order")
        if len({(item.group_id, item.resource_id) for item in self.changes}) != len(
            self.changes
        ):
            raise ValueError("cache archive diff contains duplicate resource keys")
        counts = _kind_counts(self.changes)
        expected_source = (
            self.unchanged_resource_count
            + counts["removed"]
            + counts["modified"]
            + counts["repacked"]
        )
        expected_target = (
            self.unchanged_resource_count
            + counts["added"]
            + counts["modified"]
            + counts["repacked"]
        )
        if expected_source != self.source_resource_count:
            raise ValueError("source cache resource accounting is inconsistent")
        if expected_target != self.target_resource_count:
            raise ValueError("target cache resource accounting is inconsistent")

    def as_dict(self) -> dict[str, object]:
        counts = _kind_counts(self.changes)
        return {
            "relative_path": self.relative_path,
            "source_resource_count": self.source_resource_count,
            "target_resource_count": self.target_resource_count,
            "unchanged_resource_count": self.unchanged_resource_count,
            "summary": {
                "added": counts["added"],
                "removed": counts["removed"],
                "modified": counts["modified"],
                "repacked": counts["repacked"],
            },
            "changes": [item.as_dict() for item in self.changes],
        }


@dataclass(frozen=True, slots=True)
class ClientPatchDiff:
    patch_id: str
    compared_at_utc: str
    source: ClientTreeIdentity
    target: ClientTreeIdentity
    unchanged_file_count: int
    file_changes: tuple[PatchFileChange, ...]
    cache_archive_diffs: tuple[CacheArchiveDiff, ...]
    executable_alignment: ClientAlignmentReport | None
    schema_version: int = CLIENT_PATCH_DIFF_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CLIENT_PATCH_DIFF_SCHEMA_VERSION:
            raise ValueError("unsupported client patch diff schema version")
        if not isinstance(self.patch_id, str) or _IDENTIFIER.fullmatch(self.patch_id) is None:
            raise ValueError("patch_id must be a canonical identifier")
        _timestamp(self.compared_at_utc)
        _non_negative_integer(self.unchanged_file_count, "unchanged_file_count")
        if tuple(sorted(self.file_changes, key=_file_change_key)) != self.file_changes:
            raise ValueError("file changes must use canonical path order")
        if tuple(
            sorted(self.cache_archive_diffs, key=lambda item: item.relative_path.casefold())
        ) != self.cache_archive_diffs:
            raise ValueError("cache archive diffs must use canonical path order")
        counts = _kind_counts(self.file_changes)
        source_count = (
            self.unchanged_file_count
            + counts["removed"]
            + counts["modified"]
            + counts["renamed"]
        )
        target_count = (
            self.unchanged_file_count
            + counts["added"]
            + counts["modified"]
            + counts["renamed"]
        )
        if source_count != self.source.file_count:
            raise ValueError("source file accounting is inconsistent")
        if target_count != self.target.file_count:
            raise ValueError("target file accounting is inconsistent")
        executable_changed = self.source.executable_sha256 != self.target.executable_sha256
        if executable_changed != (self.executable_alignment is not None):
            raise ValueError(
                "executable alignment must be present exactly when the executable changed"
            )

    @property
    def report_sha256(self) -> str:
        return _canonical_sha256(self._content_dict())

    def _content_dict(self) -> dict[str, object]:
        counts = _kind_counts(self.file_changes)
        modified_before = sum(
            item.before.size
            for item in self.file_changes
            if item.kind == "modified" and item.before is not None
        )
        modified_after = sum(
            item.after.size
            for item in self.file_changes
            if item.kind == "modified" and item.after is not None
        )
        return {
            "schema_version": self.schema_version,
            "patch_id": self.patch_id,
            "compared_at_utc": self.compared_at_utc,
            "source": self.source.as_dict(),
            "target": self.target.as_dict(),
            "summary": {
                "unchanged_files": self.unchanged_file_count,
                "added_files": counts["added"],
                "removed_files": counts["removed"],
                "modified_files": counts["modified"],
                "renamed_files": counts["renamed"],
                "added_file_bytes": sum(
                    item.after.size
                    for item in self.file_changes
                    if item.kind == "added" and item.after is not None
                ),
                "removed_file_bytes": sum(
                    item.before.size
                    for item in self.file_changes
                    if item.kind == "removed" and item.before is not None
                ),
                "modified_file_bytes_before": modified_before,
                "modified_file_bytes_after": modified_after,
                "net_tree_bytes": self.target.total_file_bytes - self.source.total_file_bytes,
                "changed_cache_archives": len(self.cache_archive_diffs),
                "executable_changed": self.executable_alignment is not None,
            },
            "file_changes": [item.as_dict() for item in self.file_changes],
            "cache_archive_diffs": [item.as_dict() for item in self.cache_archive_diffs],
            "executable_alignment": (
                None if self.executable_alignment is None else self.executable_alignment.as_dict()
            ),
        }

    def as_dict(self) -> dict[str, object]:
        return {**self._content_dict(), "report_sha256": self.report_sha256}


def compare_frozen_client_baselines(
    source_directory: str | Path,
    target_directory: str | Path,
    *,
    patch_id: str,
    compared_at: datetime | None = None,
    analyze_caches: bool = True,
    profile_directory: str | Path | None = None,
) -> ClientPatchDiff:
    """Verify and compare two immutable official-client snapshots without exposing payloads."""

    try:
        source = verify_frozen_client_baseline(source_directory)
        target = verify_frozen_client_baseline(target_directory)
    except ClientPatchPackageError as exc:
        raise ClientPatchDiffError(f"client baseline verification failed: {exc}") from exc

    source_identity = _tree_identity(source)
    target_identity = _tree_identity(target)
    file_changes, unchanged = _compare_file_inventories(source, target)

    cache_diffs: list[CacheArchiveDiff] = []
    if analyze_caches:
        for change in file_changes:
            if (
                change.kind == "modified"
                and change.before_path is not None
                and change.after_path is not None
                and PurePosixPath(change.after_path).suffix.casefold() == ".cache"
            ):
                cache_diffs.append(
                    compare_cache_archives(
                        Path(source.directory) / Path(change.before_path),
                        Path(target.directory) / Path(change.after_path),
                        relative_path=change.after_path,
                    )
                )

    alignment = None
    if source.executable.sha256 != target.executable.sha256:
        try:
            alignment = compare_client_builds(
                Path(source.directory) / Path(source.executable_relative_path),
                Path(target.directory) / Path(target.executable_relative_path),
                profile_directory=profile_directory,
            )
        except ClientAlignmentError as exc:
            raise ClientPatchDiffError(f"executable alignment failed: {exc}") from exc

    try:
        return ClientPatchDiff(
            patch_id=patch_id,
            compared_at_utc=_canonical_timestamp(compared_at),
            source=source_identity,
            target=target_identity,
            unchanged_file_count=unchanged,
            file_changes=file_changes,
            cache_archive_diffs=tuple(
                sorted(cache_diffs, key=lambda item: item.relative_path.casefold())
            ),
            executable_alignment=alignment,
        )
    except ValueError as exc:
        raise ClientPatchDiffError(str(exc)) from exc


def compare_cache_archives(
    source_path: str | Path,
    target_path: str | Path,
    *,
    relative_path: str,
) -> CacheArchiveDiff:
    """Compare logical resources in two Shadowbane cache archives by decompressed payload hash."""

    try:
        source = _cache_inventory(Path(source_path))
        target = _cache_inventory(Path(target_path))
    except (CacheArchiveFormatError, OSError, ValueError) as exc:
        raise ClientPatchDiffError(f"cache analysis failed for {relative_path}: {exc}") from exc

    changes: list[CacheResourceChange] = []
    unchanged = 0
    for key in sorted(set(source) | set(target)):
        before = source.get(key)
        after = target.get(key)
        if before is None:
            kind: ResourceChangeKind = "added"
        elif after is None:
            kind = "removed"
        elif before == after:
            unchanged += 1
            continue
        elif before.logical_identity == after.logical_identity:
            kind = "repacked"
        else:
            kind = "modified"
        changes.append(
            CacheResourceChange(
                kind=kind,
                group_id=key[0],
                resource_id=key[1],
                before=before,
                after=after,
            )
        )
    return CacheArchiveDiff(
        relative_path=relative_path,
        source_resource_count=len(source),
        target_resource_count=len(target),
        unchanged_resource_count=unchanged,
        changes=tuple(changes),
    )


def write_client_patch_diff(
    output_path: str | Path,
    report: ClientPatchDiff,
    *,
    pretty: bool = True,
) -> Path:
    """Publish one create-new JSON report and reread it before returning."""

    if not isinstance(report, ClientPatchDiff):
        raise TypeError("report must be a ClientPatchDiff")
    output = Path(output_path).resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = report.as_dict()
    text = json.dumps(
        payload,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    try:
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.write("\n")
        reread = json.loads(output.read_text(encoding="utf-8"))
    except FileExistsError as exc:
        raise ClientPatchDiffError(f"patch diff output already exists: {output}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ClientPatchDiffError(f"could not publish patch diff output: {output}") from exc
    if reread != payload:
        raise ClientPatchDiffError("published patch diff changed during verification")
    return output


def _compare_file_inventories(
    source: VerifiedClientBaseline,
    target: VerifiedClientBaseline,
) -> tuple[tuple[PatchFileChange, ...], int]:
    before_by_path = {item.relative_path.casefold(): item for item in source.files}
    after_by_path = {item.relative_path.casefold(): item for item in target.files}
    changes: list[PatchFileChange] = []
    unchanged = 0

    for key in sorted(set(before_by_path) & set(after_by_path)):
        before_record = before_by_path[key]
        after_record = after_by_path[key]
        before = FileFingerprint(before_record.size, before_record.sha256)
        after = FileFingerprint(after_record.size, after_record.sha256)
        if before == after and before_record.relative_path == after_record.relative_path:
            unchanged += 1
            continue
        changes.append(
            PatchFileChange(
                kind="renamed" if before == after else "modified",
                before_path=before_record.relative_path,
                before=before,
                after_path=after_record.relative_path,
                after=after,
            )
        )

    removed = {
        key: before_by_path[key] for key in set(before_by_path) - set(after_by_path)
    }
    added = {key: after_by_path[key] for key in set(after_by_path) - set(before_by_path)}

    removed_by_fingerprint: dict[tuple[int, str], list[str]] = {}
    added_by_fingerprint: dict[tuple[int, str], list[str]] = {}
    for key, record in removed.items():
        removed_by_fingerprint.setdefault((record.size, record.sha256), []).append(key)
    for key, record in added.items():
        added_by_fingerprint.setdefault((record.size, record.sha256), []).append(key)
    for fingerprint in sorted(set(removed_by_fingerprint) & set(added_by_fingerprint)):
        old_keys = removed_by_fingerprint[fingerprint]
        new_keys = added_by_fingerprint[fingerprint]
        if len(old_keys) != 1 or len(new_keys) != 1:
            continue
        old_key = old_keys[0]
        new_key = new_keys[0]
        before_record = removed.pop(old_key)
        after_record = added.pop(new_key)
        identity = FileFingerprint(*fingerprint)
        changes.append(
            PatchFileChange(
                kind="renamed",
                before_path=before_record.relative_path,
                before=identity,
                after_path=after_record.relative_path,
                after=identity,
            )
        )

    for record in removed.values():
        changes.append(
            PatchFileChange(
                kind="removed",
                before_path=record.relative_path,
                before=FileFingerprint(record.size, record.sha256),
                after_path=None,
                after=None,
            )
        )
    for record in added.values():
        changes.append(
            PatchFileChange(
                kind="added",
                before_path=None,
                before=None,
                after_path=record.relative_path,
                after=FileFingerprint(record.size, record.sha256),
            )
        )
    return tuple(sorted(changes, key=_file_change_key)), unchanged


def _tree_identity(baseline: VerifiedClientBaseline) -> ClientTreeIdentity:
    evidence = Path(baseline.directory) / _BASELINE_FILE_NAME
    return ClientTreeIdentity(
        directory=baseline.directory,
        repository_revision=baseline.repository_revision,
        baseline_evidence_sha256=_file_sha256(evidence),
        tree_sha256=baseline.tree_sha256,
        executable_relative_path=baseline.executable_relative_path,
        executable_sha256=baseline.executable.sha256,
        file_count=len(baseline.files),
        total_file_bytes=sum(item.size for item in baseline.files),
    )


def _cache_inventory(path: Path) -> dict[tuple[int, int], CacheResourceFingerprint]:
    results: dict[tuple[int, int], CacheResourceFingerprint] = {}
    with CacheArchive(path) as archive:
        for entry in archive.entries:
            key = entry.group_id, entry.resource_id
            if key in results:
                raise ValueError(f"cache contains duplicate resource key {key[0]}:{key[1]}")
            payload = archive.read_resource(entry)
            results[key] = CacheResourceFingerprint(
                uncompressed_size=entry.uncompressed_size,
                stored_size=entry.stored_size,
                compressed=entry.is_compressed,
                payload_sha256=hashlib.sha256(payload).hexdigest(),
            )
    return results


def _file_side(
    path: str | None,
    fingerprint: FileFingerprint | None,
) -> dict[str, object] | None:
    if path is None or fingerprint is None:
        return None
    return {"relative_path": path, **fingerprint.as_dict()}


def _file_change_key(change: PatchFileChange) -> tuple[str, str, str]:
    return (
        (change.before_path or change.after_path or "").casefold(),
        (change.after_path or "").casefold(),
        change.kind,
    )


def _resource_change_key(change: CacheResourceChange) -> tuple[int, int]:
    return change.group_id, change.resource_id


def _kind_counts(values: tuple[Any, ...]) -> dict[str, int]:
    counts = {
        "added": 0,
        "removed": 0,
        "modified": 0,
        "renamed": 0,
        "repacked": 0,
    }
    for value in values:
        counts[value.kind] += 1
    return counts


def _relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ValueError("relative path must be a non-empty POSIX-style path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("relative path must remain beneath the client root")
    if path.as_posix() != value:
        raise ValueError("relative path must be canonical POSIX form")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(serialized).hexdigest()


def _canonical_timestamp(value: datetime | None) -> str:
    current = datetime.now(UTC) if value is None else value
    if current.tzinfo is None:
        raise ValueError("compared_at must include a timezone")
    return current.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _timestamp(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("compared_at_utc must be text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("compared_at_utc must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("compared_at_utc must include a timezone")


def _sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.casefold()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be lowercase hexadecimal SHA-256")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _unsigned_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"{field_name} must be a 32-bit unsigned integer")


__all__ = [
    "CLIENT_PATCH_DIFF_SCHEMA_VERSION",
    "CacheArchiveDiff",
    "CacheResourceChange",
    "CacheResourceFingerprint",
    "ClientPatchDiff",
    "ClientPatchDiffError",
    "ClientTreeIdentity",
    "FileFingerprint",
    "PatchFileChange",
    "compare_cache_archives",
    "compare_frozen_client_baselines",
    "write_client_patch_diff",
]
