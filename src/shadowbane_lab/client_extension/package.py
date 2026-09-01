"""Atomic disposable client-copy packaging and verified rollback."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from shadowbane_lab.client_alignment.model import PeImage
from shadowbane_lab.client_alignment.pe import PeInspectionError, inspect_pe_bytes
from shadowbane_lab.client_extension.baseline import BaselineFile
from shadowbane_lab.client_extension.manifest import PatchManifest
from shadowbane_lab.client_extension.resolver import (
    PatchPlan,
    PatchResolutionError,
    apply_patch_plan,
    build_patch_plan,
)
from shadowbane_lab.client_extension.texture_patch import (
    TexturePatchError,
    TexturePatchManifest,
    TexturePatchPlan,
    apply_texture_patch_plan,
    build_texture_patch_evidence,
    build_texture_patch_plan,
)

PATCH_PACKAGE_SCHEMA_VERSION = 1
PACKAGE_DRIFT_SCHEMA_VERSION = 1
ROLLBACK_RECEIPT_SCHEMA_VERSION = 1
RUNTIME_DRIFT_ROLLBACK_RECEIPT_SCHEMA_VERSION = 2
_BASELINE_FILE_NAME = "client-baseline.json"
_EVIDENCE_DIRECTORY_NAME = ".wonderbane-extension"
_PACKAGE_FILE_NAME = "package.json"
_TEXTURE_PATCH_FILE_NAME = "texture-patches.json"
_DEFAULT_MAX_FILES = 100_000
_DEFAULT_MAX_TOTAL_BYTES = 16 * 1024 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
_IMAGE_FILE_DLL = 0x2000


class ClientPatchPackageError(RuntimeError):
    """Raised when a disposable client package cannot be proven safe."""


@dataclass(frozen=True, slots=True)
class VerifiedClientBaseline:
    directory: str
    repository_revision: str
    executable_relative_path: str
    tree_sha256: str
    files: tuple[BaselineFile, ...]
    executable: PeImage


@dataclass(frozen=True, slots=True)
class PatchPackageEvidence:
    created_at_utc: str
    destination_directory: str
    baseline_directory: str
    baseline_tree_sha256: str
    repository_revision: str
    patch_id: str
    manifest_sha256: str
    source_executable_sha256: str
    result_executable_sha256: str
    executable_relative_path: str
    extension_relative_path: str
    extension_sha256: str
    already_patched: bool
    working_tree_sha256: str
    files: tuple[BaselineFile, ...]
    schema_version: int = PATCH_PACKAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PATCH_PACKAGE_SCHEMA_VERSION:
            raise ValueError("unsupported patch-package schema version")
        _timestamp(self.created_at_utc, "created_at_utc")
        for value, name in (
            (self.destination_directory, "destination_directory"),
            (self.baseline_directory, "baseline_directory"),
            (self.repository_revision, "repository_revision"),
            (self.patch_id, "patch_id"),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be non-empty")
        for value, name in (
            (self.baseline_tree_sha256, "baseline_tree_sha256"),
            (self.manifest_sha256, "manifest_sha256"),
            (self.source_executable_sha256, "source_executable_sha256"),
            (self.result_executable_sha256, "result_executable_sha256"),
            (self.extension_sha256, "extension_sha256"),
            (self.working_tree_sha256, "working_tree_sha256"),
        ):
            _sha256(value, name)
        _relative_path(self.executable_relative_path)
        _relative_path(self.extension_relative_path)
        if not isinstance(self.already_patched, bool):
            raise ValueError("already_patched must be boolean")
        _validate_records(self.files)
        if _tree_sha256(self.files) != self.working_tree_sha256:
            raise ValueError("working tree digest does not match its file inventory")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at_utc": self.created_at_utc,
            "destination_directory": self.destination_directory,
            "baseline_directory": self.baseline_directory,
            "baseline_tree_sha256": self.baseline_tree_sha256,
            "repository_revision": self.repository_revision,
            "patch_id": self.patch_id,
            "manifest_sha256": self.manifest_sha256,
            "source_executable_sha256": self.source_executable_sha256,
            "result_executable_sha256": self.result_executable_sha256,
            "executable_relative_path": self.executable_relative_path,
            "extension_relative_path": self.extension_relative_path,
            "extension_sha256": self.extension_sha256,
            "already_patched": self.already_patched,
            "file_count": len(self.files),
            "total_file_bytes": sum(item.size for item in self.files),
            "working_tree_sha256": self.working_tree_sha256,
            "files": [item.as_dict() for item in self.files],
        }


@dataclass(frozen=True, slots=True)
class PatchPackageResult:
    dry_run: bool
    destination_published: bool
    plan: PatchPlan
    texture_plan: TexturePatchPlan | None
    evidence: PatchPackageEvidence | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "destination_published": self.destination_published,
            "plan": self.plan.as_dict(),
            "texture_plan": (
                None if self.texture_plan is None else self.texture_plan.as_dict()
            ),
            "evidence": None if self.evidence is None else self.evidence.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class PackageFileChange:
    """One packaged path whose content or canonical spelling changed."""

    expected: BaselineFile
    actual: BaselineFile

    def as_dict(self) -> dict[str, object]:
        return {
            "expected": self.expected.as_dict(),
            "actual": self.actual.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class PatchPackageDrift:
    """Read-only comparison of a disposable copy with its package evidence."""

    directory: str
    expected_working_tree_sha256: str
    actual_working_tree_sha256: str
    added: tuple[BaselineFile, ...]
    missing: tuple[BaselineFile, ...]
    changed: tuple[PackageFileChange, ...]
    schema_version: int = PACKAGE_DRIFT_SCHEMA_VERSION

    @property
    def matches(self) -> bool:
        return not self.added and not self.missing and not self.changed

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "directory": self.directory,
            "matches": self.matches,
            "expected_working_tree_sha256": self.expected_working_tree_sha256,
            "actual_working_tree_sha256": self.actual_working_tree_sha256,
            "added": [item.as_dict() for item in self.added],
            "missing": [item.as_dict() for item in self.missing],
            "changed": [item.as_dict() for item in self.changed],
        }


@dataclass(frozen=True, slots=True)
class RollbackReceipt:
    discarded_at_utc: str
    discarded_directory: str
    patch_id: str
    working_tree_sha256: str
    baseline_directory: str
    baseline_tree_sha256: str
    receipt_path: str
    schema_version: int = ROLLBACK_RECEIPT_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "discarded_at_utc": self.discarded_at_utc,
            "discarded_directory": self.discarded_directory,
            "patch_id": self.patch_id,
            "working_tree_sha256": self.working_tree_sha256,
            "baseline_directory": self.baseline_directory,
            "baseline_tree_sha256": self.baseline_tree_sha256,
            "receipt_path": self.receipt_path,
        }


@dataclass(frozen=True, slots=True)
class RuntimeDriftRollbackReceipt:
    """Evidence for retirement after archiving recognized runtime-written files."""

    discarded_at_utc: str
    discarded_directory: str
    patch_id: str
    expected_working_tree_sha256: str
    actual_working_tree_sha256: str
    baseline_directory: str
    baseline_tree_sha256: str
    archived_runtime_files_directory: str
    changed_files: tuple[BaselineFile, ...]
    missing_files: tuple[BaselineFile, ...]
    receipt_path: str
    schema_version: int = RUNTIME_DRIFT_ROLLBACK_RECEIPT_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "discarded_at_utc": self.discarded_at_utc,
            "discarded_directory": self.discarded_directory,
            "patch_id": self.patch_id,
            "expected_working_tree_sha256": self.expected_working_tree_sha256,
            "actual_working_tree_sha256": self.actual_working_tree_sha256,
            "baseline_directory": self.baseline_directory,
            "baseline_tree_sha256": self.baseline_tree_sha256,
            "archived_runtime_files_directory": self.archived_runtime_files_directory,
            "changed_files": [item.as_dict() for item in self.changed_files],
            "missing_files": [item.as_dict() for item in self.missing_files],
            "receipt_path": self.receipt_path,
        }


def verify_frozen_client_baseline(
    frozen_directory: str | Path,
    *,
    max_files: int = _DEFAULT_MAX_FILES,
    max_total_bytes: int = _DEFAULT_MAX_TOTAL_BYTES,
) -> VerifiedClientBaseline:
    """Reread a frozen baseline and require exact agreement with its evidence."""

    root = Path(frozen_directory).resolve()
    if not root.is_dir() or _is_reparse_point(root):
        raise ClientPatchPackageError(f"frozen baseline is not a regular directory: {root}")
    payload = _load_json(root / _BASELINE_FILE_NAME)
    _fields(
        payload,
        {
            "schema_version",
            "captured_at_utc",
            "repository_revision",
            "source_directory",
            "frozen_directory",
            "executable_relative_path",
            "tree_sha256",
            "file_count",
            "total_file_bytes",
            "files",
            "executable",
        },
        "client baseline",
    )
    if payload["schema_version"] != 1:
        raise ClientPatchPackageError("unsupported client-baseline schema version")
    _timestamp_value(payload["captured_at_utc"], "captured_at_utc")
    repository_revision = _nonempty_text(payload["repository_revision"], "repository_revision")
    _nonempty_text(payload["source_directory"], "source_directory")
    recorded_root = Path(_nonempty_text(payload["frozen_directory"], "frozen_directory")).resolve()
    if recorded_root != root:
        raise ClientPatchPackageError("client baseline is bound to a different frozen directory")
    executable_relative = _relative_path_value(
        payload["executable_relative_path"],
        "executable_relative_path",
    )
    tree_sha256 = _sha256_value(payload["tree_sha256"], "tree_sha256")
    expected_files = _parse_records(payload["files"])
    _require_count(payload["file_count"], len(expected_files), "file_count")
    _require_count(
        payload["total_file_bytes"],
        sum(item.size for item in expected_files),
        "total_file_bytes",
    )
    if _tree_sha256(expected_files) != tree_sha256:
        raise ClientPatchPackageError("client baseline tree digest is internally inconsistent")

    actual_files = _inventory(
        root,
        excluded=frozenset({_BASELINE_FILE_NAME.casefold()}),
        max_files=max_files,
        max_total_bytes=max_total_bytes,
    )
    if actual_files != expected_files:
        raise ClientPatchPackageError("frozen client tree differs from its baseline inventory")
    executable_record = _unique_record(expected_files, executable_relative)
    executable_data = (root / Path(executable_record.relative_path)).read_bytes()
    try:
        executable = inspect_pe_bytes(executable_data, path=executable_relative)
    except PeInspectionError as exc:
        raise ClientPatchPackageError(f"frozen executable is no longer a valid PE: {exc}") from exc
    executable_payload = payload["executable"]
    if not isinstance(executable_payload, dict) or executable.as_dict() != executable_payload:
        raise ClientPatchPackageError("frozen executable differs from its PE evidence")
    return VerifiedClientBaseline(
        directory=str(root),
        repository_revision=repository_revision,
        executable_relative_path=executable_relative,
        tree_sha256=tree_sha256,
        files=expected_files,
        executable=executable,
    )


def prepare_patched_client_copy(
    frozen_directory: str | Path,
    destination_directory: str | Path,
    manifest: PatchManifest,
    extension_artifact: str | Path,
    *,
    texture_patch_manifest: TexturePatchManifest | None = None,
    texture_artifact_directory: str | Path | None = None,
    dry_run: bool = False,
    created_at: datetime | None = None,
) -> PatchPackageResult:
    """Verify inputs and atomically publish a new disposable patched client copy."""

    if not isinstance(manifest, PatchManifest):
        raise ClientPatchPackageError("manifest must be a validated PatchManifest")
    baseline_root = Path(frozen_directory).resolve()
    destination = Path(destination_directory).resolve()
    if destination.exists():
        raise ClientPatchPackageError(f"destination already exists: {destination}")
    if _is_within(destination, baseline_root) or _is_within(baseline_root, destination):
        raise ClientPatchPackageError("baseline and destination must not contain each other")
    baseline = verify_frozen_client_baseline(baseline_root)
    if PurePosixPath(baseline.executable_relative_path).name.casefold() != (
        manifest.source.file_name.casefold()
    ):
        raise ClientPatchPackageError("manifest source file name differs from baseline executable")
    if baseline.executable.sha256 not in {
        manifest.source.sha256,
        manifest.patched_executable_sha256,
    }:
        raise ClientPatchPackageError("baseline executable is not recognized by the manifest")

    extension_path = Path(extension_artifact).resolve()
    extension_data = _verified_extension(extension_path, manifest)
    executable_path = baseline_root / Path(baseline.executable_relative_path)
    executable_data = executable_path.read_bytes()
    try:
        plan = build_patch_plan(executable_data, manifest)
    except PatchResolutionError as exc:
        raise ClientPatchPackageError(f"patch plan was rejected: {exc}") from exc

    texture_plan = None
    if texture_patch_manifest is None:
        if texture_artifact_directory is not None:
            raise ClientPatchPackageError(
                "texture_artifact_directory requires texture_patch_manifest"
            )
    else:
        if texture_artifact_directory is None:
            raise ClientPatchPackageError(
                "texture_patch_manifest requires texture_artifact_directory"
            )
        texture_cache = baseline_root / Path(texture_patch_manifest.cache_relative_path)
        try:
            texture_plan = build_texture_patch_plan(
                texture_cache,
                texture_patch_manifest,
                texture_artifact_directory,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise ClientPatchPackageError(f"texture patch plan was rejected: {exc}") from exc

    extension_relative = (
        PurePosixPath(baseline.executable_relative_path).parent / manifest.extension.file_name
    ).as_posix()
    if extension_relative == ".":
        extension_relative = manifest.extension.file_name
    reserved = {
        _EVIDENCE_DIRECTORY_NAME.casefold(),
        extension_relative.casefold(),
    }
    for record in baseline.files:
        first_part = PurePosixPath(record.relative_path).parts[0].casefold()
        if record.relative_path.casefold() in reserved or first_part == (
            _EVIDENCE_DIRECTORY_NAME.casefold()
        ):
            raise ClientPatchPackageError(
                f"baseline collides with extension package output: {record.relative_path}"
            )

    if dry_run:
        return PatchPackageResult(
            dry_run=True,
            destination_published=False,
            plan=plan,
            texture_plan=texture_plan,
            evidence=None,
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=str(destination.parent))
    )
    published = False
    completed = False
    try:
        _copy_baseline_inventory(baseline_root, temporary, baseline.files)
        copied = _inventory(
            temporary,
            max_files=_DEFAULT_MAX_FILES,
            max_total_bytes=_DEFAULT_MAX_TOTAL_BYTES,
        )
        if copied != baseline.files:
            raise ClientPatchPackageError("copied client tree differs from the frozen baseline")

        patched_data = apply_patch_plan(executable_data, plan.writes)
        temporary_executable = temporary / Path(baseline.executable_relative_path)
        temporary_executable.write_bytes(patched_data)
        temporary_extension = temporary / Path(extension_relative)
        temporary_extension.parent.mkdir(parents=True, exist_ok=True)
        with temporary_extension.open("xb") as stream:
            stream.write(extension_data)

        evidence_directory = temporary / _EVIDENCE_DIRECTORY_NAME
        if texture_plan is not None and texture_patch_manifest is not None:
            temporary_cache = temporary / Path(texture_plan.cache_relative_path)
            apply_texture_patch_plan(temporary_cache, texture_plan)
            texture_evidence = build_texture_patch_evidence(
                texture_patch_manifest,
                texture_plan,
                temporary_cache,
            )
            evidence_directory.mkdir()
            _write_new_json(
                evidence_directory / _TEXTURE_PATCH_FILE_NAME,
                texture_evidence.as_dict(),
            )

        working_files = _inventory(
            temporary,
            max_files=_DEFAULT_MAX_FILES,
            max_total_bytes=_DEFAULT_MAX_TOTAL_BYTES,
        )
        working_tree_sha256 = _tree_sha256(working_files)
        evidence = PatchPackageEvidence(
            created_at_utc=_canonical_timestamp(created_at),
            destination_directory=str(destination),
            baseline_directory=baseline.directory,
            baseline_tree_sha256=baseline.tree_sha256,
            repository_revision=baseline.repository_revision,
            patch_id=manifest.patch_id,
            manifest_sha256=_manifest_sha256(manifest),
            source_executable_sha256=baseline.executable.sha256,
            result_executable_sha256=manifest.patched_executable_sha256,
            executable_relative_path=baseline.executable_relative_path,
            extension_relative_path=extension_relative,
            extension_sha256=manifest.extension.sha256,
            already_patched=plan.already_patched,
            working_tree_sha256=working_tree_sha256,
            files=working_files,
        )
        evidence_directory.mkdir(exist_ok=True)
        _write_new_json(evidence_directory / _PACKAGE_FILE_NAME, evidence.as_dict())
        os.replace(temporary, destination)
        published = True
        verified = verify_patched_client_copy(destination)
        if verified != evidence:
            raise ClientPatchPackageError("published package evidence changed after publication")
        verify_frozen_client_baseline(baseline_root)
        completed = True
        return PatchPackageResult(
            dry_run=False,
            destination_published=True,
            plan=plan,
            texture_plan=texture_plan,
            evidence=evidence,
        )
    except ClientPatchPackageError as exc:
        if published:
            shutil.rmtree(destination, ignore_errors=True)
            if destination.exists():
                raise ClientPatchPackageError(
                    f"invalid new package could not be removed: {destination}"
                ) from exc
        raise
    except (OSError, TexturePatchError, ValueError) as exc:
        if published:
            shutil.rmtree(destination, ignore_errors=True)
            if destination.exists():
                raise ClientPatchPackageError(
                    f"invalid new package could not be removed: {destination}"
                ) from exc
        raise ClientPatchPackageError(f"could not prepare patched client copy: {exc}") from exc
    finally:
        if not completed and published and destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def verify_patched_client_copy(directory: str | Path) -> PatchPackageEvidence:
    """Require a disposable copy and every packaged byte to match its marker."""

    root = Path(directory).resolve()
    if not root.is_dir() or _is_reparse_point(root):
        raise ClientPatchPackageError(f"patched client copy is not a regular directory: {root}")
    evidence = _load_package_evidence(root / _EVIDENCE_DIRECTORY_NAME / _PACKAGE_FILE_NAME)
    if Path(evidence.destination_directory).resolve() != root:
        raise ClientPatchPackageError("package evidence is bound to a different destination")
    actual = _inventory(
        root,
        excluded=frozenset(
            {
                f"{_EVIDENCE_DIRECTORY_NAME}/{_PACKAGE_FILE_NAME}".casefold(),
            }
        ),
        max_files=_DEFAULT_MAX_FILES,
        max_total_bytes=_DEFAULT_MAX_TOTAL_BYTES,
    )
    if actual != evidence.files or _tree_sha256(actual) != evidence.working_tree_sha256:
        raise ClientPatchPackageError("patched client copy differs from its package inventory")
    executable = _unique_record(actual, evidence.executable_relative_path)
    extension = _unique_record(actual, evidence.extension_relative_path)
    if executable.sha256 != evidence.result_executable_sha256:
        raise ClientPatchPackageError("packaged executable hash does not match its evidence")
    if extension.sha256 != evidence.extension_sha256:
        raise ClientPatchPackageError("packaged extension hash does not match its evidence")
    return evidence


def verify_runtime_patched_client_copy(directory: str | Path) -> PatchPackageEvidence:
    """Require all drift to be confined to reviewed client-written paths.

    Publication uses :func:`verify_patched_client_copy` before the package has
    ever run. A launched Shadowbane client rewrites a small, reviewed set of
    settings, log, and DoubleFusion runtime files; those writes must not make a
    later launch indistinguishable from immutable package tampering.
    """

    root = Path(directory).resolve()
    drift = audit_patched_client_copy(root)
    unexpected_added = tuple(
        item.relative_path
        for item in drift.added
        if not _is_known_runtime_mutable_path(item.relative_path)
    )
    unexpected_missing = tuple(
        item.relative_path
        for item in drift.missing
        if not _is_known_runtime_mutable_path(item.relative_path)
    )
    unexpected_changed = tuple(
        item.actual.relative_path
        for item in drift.changed
        if not _is_known_runtime_mutable_path(item.actual.relative_path)
    )
    unexpected = (
        tuple(f"added:{path}" for path in unexpected_added)
        + tuple(f"missing:{path}" for path in unexpected_missing)
        + tuple(f"changed:{path}" for path in unexpected_changed)
    )
    if unexpected:
        raise ClientPatchPackageError(
            "runtime client copy contains non-runtime drift: " + ", ".join(unexpected)
        )
    return _load_package_evidence(root / _EVIDENCE_DIRECTORY_NAME / _PACKAGE_FILE_NAME)


def audit_patched_client_copy(directory: str | Path) -> PatchPackageDrift:
    """Report exact package drift without modifying the disposable copy."""

    root = Path(directory).resolve()
    if not root.is_dir() or _is_reparse_point(root):
        raise ClientPatchPackageError(f"patched client copy is not a regular directory: {root}")
    evidence = _load_package_evidence(root / _EVIDENCE_DIRECTORY_NAME / _PACKAGE_FILE_NAME)
    if Path(evidence.destination_directory).resolve() != root:
        raise ClientPatchPackageError("package evidence is bound to a different destination")
    actual = _inventory(
        root,
        excluded=frozenset(
            {
                f"{_EVIDENCE_DIRECTORY_NAME}/{_PACKAGE_FILE_NAME}".casefold(),
            }
        ),
        max_files=_DEFAULT_MAX_FILES,
        max_total_bytes=_DEFAULT_MAX_TOTAL_BYTES,
    )
    expected_by_path = {item.relative_path.casefold(): item for item in evidence.files}
    actual_by_path = {item.relative_path.casefold(): item for item in actual}
    added = tuple(
        actual_by_path[key]
        for key in sorted(actual_by_path.keys() - expected_by_path.keys())
    )
    missing = tuple(
        expected_by_path[key]
        for key in sorted(expected_by_path.keys() - actual_by_path.keys())
    )
    changed = tuple(
        PackageFileChange(expected_by_path[key], actual_by_path[key])
        for key in sorted(expected_by_path.keys() & actual_by_path.keys())
        if expected_by_path[key] != actual_by_path[key]
    )
    return PatchPackageDrift(
        directory=str(root),
        expected_working_tree_sha256=evidence.working_tree_sha256,
        actual_working_tree_sha256=_tree_sha256(actual),
        added=added,
        missing=missing,
        changed=changed,
    )


def discard_patched_client_copy(
    directory: str | Path,
    receipt_path: str | Path,
    *,
    discarded_at: datetime | None = None,
) -> RollbackReceipt:
    """Delete only an exactly verified disposable copy and preserve rollback evidence."""

    root = Path(directory).resolve()
    receipt = Path(receipt_path).resolve()
    if receipt.exists():
        raise ClientPatchPackageError(f"rollback receipt already exists: {receipt}")
    if _is_within(receipt, root):
        raise ClientPatchPackageError("rollback receipt must be outside the discarded directory")
    evidence = verify_patched_client_copy(root)
    baseline = verify_frozen_client_baseline(evidence.baseline_directory)
    if baseline.tree_sha256 != evidence.baseline_tree_sha256:
        raise ClientPatchPackageError("frozen baseline digest changed before rollback")

    receipt.parent.mkdir(parents=True, exist_ok=True)
    result = RollbackReceipt(
        discarded_at_utc=_canonical_timestamp(discarded_at),
        discarded_directory=str(root),
        patch_id=evidence.patch_id,
        working_tree_sha256=evidence.working_tree_sha256,
        baseline_directory=baseline.directory,
        baseline_tree_sha256=baseline.tree_sha256,
        receipt_path=str(receipt),
    )
    temporary_receipt = _write_temporary_json(receipt.parent, result.as_dict())
    quarantine = root.parent / f".{root.name}.discard-{uuid.uuid4().hex}"
    try:
        os.replace(root, quarantine)
        shutil.rmtree(quarantine)
        os.replace(temporary_receipt, receipt)
    except OSError as exc:
        raise ClientPatchPackageError(
            f"could not discard patched client copy; inspect quarantine {quarantine}: {exc}"
        ) from exc
    finally:
        temporary_receipt.unlink(missing_ok=True)
    verify_frozen_client_baseline(baseline.directory)
    return result


def discard_runtime_drifted_client_copy(
    directory: str | Path,
    receipt_path: str | Path,
    archive_directory: str | Path,
    *,
    actual_working_tree_sha256: str,
    discarded_at: datetime | None = None,
) -> RuntimeDriftRollbackReceipt:
    """Archive recognized runtime drift, then discard an otherwise intact copy."""

    _sha256(actual_working_tree_sha256, "actual working tree sha256")
    root = Path(directory).resolve()
    receipt = Path(receipt_path).resolve()
    archive = Path(archive_directory).resolve()
    if receipt.exists():
        raise ClientPatchPackageError(f"rollback receipt already exists: {receipt}")
    if archive.exists():
        raise ClientPatchPackageError(f"runtime-drift archive already exists: {archive}")
    if _is_within(receipt, root) or _is_within(archive, root):
        raise ClientPatchPackageError(
            "rollback receipt and runtime-drift archive must be outside the discarded directory"
        )

    drift = audit_patched_client_copy(root)
    if drift.actual_working_tree_sha256 != actual_working_tree_sha256:
        raise ClientPatchPackageError("patched client copy changed after its reviewed drift audit")
    if drift.matches:
        raise ClientPatchPackageError("patched client copy has no runtime drift; use verified discard")
    if drift.added:
        raise ClientPatchPackageError("runtime-drift retirement does not allow added files")
    unexpected_changed = tuple(
        item.actual.relative_path
        for item in drift.changed
        if not _is_known_runtime_mutable_path(item.actual.relative_path)
    )
    unexpected_missing = tuple(
        item.relative_path
        for item in drift.missing
        if not _is_known_runtime_mutable_path(item.relative_path)
    )
    unexpected = unexpected_changed + unexpected_missing
    if unexpected:
        raise ClientPatchPackageError(
            "runtime-drift retirement found non-runtime changes: " + ", ".join(unexpected)
        )

    evidence = _load_package_evidence(root / _EVIDENCE_DIRECTORY_NAME / _PACKAGE_FILE_NAME)
    baseline = verify_frozen_client_baseline(evidence.baseline_directory)
    if baseline.tree_sha256 != evidence.baseline_tree_sha256:
        raise ClientPatchPackageError("frozen baseline digest changed before rollback")
    changed_files = tuple(item.actual for item in drift.changed)

    receipt.parent.mkdir(parents=True, exist_ok=True)
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary_archive = Path(
        tempfile.mkdtemp(prefix=f".{archive.name}.tmp-", dir=archive.parent)
    )
    temporary_receipt: Path | None = None
    quarantine = root.parent / f".{root.name}.discard-{uuid.uuid4().hex}"
    archive_published = False
    try:
        for record in changed_files:
            relative = Path(*PurePosixPath(record.relative_path).parts)
            destination = temporary_archive / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, destination)
        archived = _inventory(
            temporary_archive,
            max_files=_DEFAULT_MAX_FILES,
            max_total_bytes=_DEFAULT_MAX_TOTAL_BYTES,
        )
        if archived != changed_files:
            raise ClientPatchPackageError("runtime-drift archive failed its hash verification")
        os.replace(temporary_archive, archive)
        archive_published = True

        result = RuntimeDriftRollbackReceipt(
            discarded_at_utc=_canonical_timestamp(discarded_at),
            discarded_directory=str(root),
            patch_id=evidence.patch_id,
            expected_working_tree_sha256=evidence.working_tree_sha256,
            actual_working_tree_sha256=drift.actual_working_tree_sha256,
            baseline_directory=baseline.directory,
            baseline_tree_sha256=baseline.tree_sha256,
            archived_runtime_files_directory=str(archive),
            changed_files=changed_files,
            missing_files=drift.missing,
            receipt_path=str(receipt),
        )
        temporary_receipt = _write_temporary_json(receipt.parent, result.as_dict())
        os.replace(root, quarantine)
        shutil.rmtree(quarantine)
        os.replace(temporary_receipt, receipt)
        temporary_receipt = None
    except OSError as exc:
        raise ClientPatchPackageError(
            f"could not discard runtime-drifted copy; inspect quarantine {quarantine}: {exc}"
        ) from exc
    finally:
        if temporary_archive.exists():
            shutil.rmtree(temporary_archive, ignore_errors=True)
        if temporary_receipt is not None:
            temporary_receipt.unlink(missing_ok=True)
        if archive_published and root.exists() and archive.exists():
            shutil.rmtree(archive, ignore_errors=True)
    verify_frozen_client_baseline(baseline.directory)
    return result


def _is_known_runtime_mutable_path(relative_path: str) -> bool:
    normalized = relative_path.casefold()
    exact = {
        "config/arcanepref.cfg",
        "doublefusion/cache/cache.dat",
        "doublefusion/dftm.dat",
        "doublefusion/dfts.dat",
        "doublefusion/engine.log",
        "doublefusion/user.var",
        "logs/debug.txt",
    }
    if normalized in exact:
        return True
    return (
        normalized.startswith("config/screen_game_")
        and normalized.endswith("_wonderbane.cfg")
        and normalized.count("/") == 1
    )


def _verified_extension(path: Path, manifest: PatchManifest) -> bytes:
    if path.name.casefold() != manifest.extension.file_name.casefold():
        raise ClientPatchPackageError("extension artifact file name differs from the manifest")
    if not path.is_file() or _is_reparse_point(path):
        raise ClientPatchPackageError(f"extension artifact is not a regular file: {path}")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest.extension.sha256:
        raise ClientPatchPackageError("extension artifact SHA-256 differs from the manifest")
    try:
        image = inspect_pe_bytes(data, path=path.name)
    except PeInspectionError as exc:
        raise ClientPatchPackageError(f"extension artifact is not a supported PE: {exc}") from exc
    if image.machine != manifest.extension.machine:
        raise ClientPatchPackageError("extension artifact machine differs from the manifest")
    if image.pointer_size != manifest.source.pointer_size:
        raise ClientPatchPackageError("extension pointer size differs from the client")
    if not image.characteristics & _IMAGE_FILE_DLL:
        raise ClientPatchPackageError("extension artifact is not marked as a PE DLL")
    return data


def _load_package_evidence(path: Path) -> PatchPackageEvidence:
    payload = _load_json(path)
    _fields(
        payload,
        {
            "schema_version",
            "created_at_utc",
            "destination_directory",
            "baseline_directory",
            "baseline_tree_sha256",
            "repository_revision",
            "patch_id",
            "manifest_sha256",
            "source_executable_sha256",
            "result_executable_sha256",
            "executable_relative_path",
            "extension_relative_path",
            "extension_sha256",
            "already_patched",
            "file_count",
            "total_file_bytes",
            "working_tree_sha256",
            "files",
        },
        "patch package",
    )
    files = _parse_records(payload["files"])
    _require_count(payload["file_count"], len(files), "file_count")
    _require_count(
        payload["total_file_bytes"],
        sum(item.size for item in files),
        "total_file_bytes",
    )
    try:
        return PatchPackageEvidence(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            created_at_utc=payload["created_at_utc"],  # type: ignore[arg-type]
            destination_directory=payload["destination_directory"],  # type: ignore[arg-type]
            baseline_directory=payload["baseline_directory"],  # type: ignore[arg-type]
            baseline_tree_sha256=payload["baseline_tree_sha256"],  # type: ignore[arg-type]
            repository_revision=payload["repository_revision"],  # type: ignore[arg-type]
            patch_id=payload["patch_id"],  # type: ignore[arg-type]
            manifest_sha256=payload["manifest_sha256"],  # type: ignore[arg-type]
            source_executable_sha256=payload["source_executable_sha256"],  # type: ignore[arg-type]
            result_executable_sha256=payload["result_executable_sha256"],  # type: ignore[arg-type]
            executable_relative_path=payload["executable_relative_path"],  # type: ignore[arg-type]
            extension_relative_path=payload["extension_relative_path"],  # type: ignore[arg-type]
            extension_sha256=payload["extension_sha256"],  # type: ignore[arg-type]
            already_patched=payload["already_patched"],  # type: ignore[arg-type]
            working_tree_sha256=payload["working_tree_sha256"],  # type: ignore[arg-type]
            files=files,
        )
    except ValueError as exc:
        raise ClientPatchPackageError(f"invalid patch-package evidence: {exc}") from exc


def _inventory(
    root: Path,
    *,
    excluded: frozenset[str] = frozenset(),
    max_files: int,
    max_total_bytes: int,
) -> tuple[BaselineFile, ...]:
    records: list[BaselineFile] = []
    total_bytes = 0
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(directory)
        directory_names.sort(key=str.casefold)
        file_names.sort(key=str.casefold)
        for name in directory_names:
            path = current / name
            if _is_reparse_point(path):
                raise ClientPatchPackageError(f"client tree contains a reparse directory: {path}")
        for name in file_names:
            path = current / name
            relative = path.relative_to(root).as_posix()
            if relative.casefold() in excluded:
                continue
            if _is_reparse_point(path) or not path.is_file():
                raise ClientPatchPackageError(f"client tree contains a non-regular file: {path}")
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
            records.append(BaselineFile(relative, size, digest.hexdigest()))
            total_bytes += size
            if len(records) > max_files:
                raise ClientPatchPackageError("client tree exceeds the file-count limit")
            if total_bytes > max_total_bytes:
                raise ClientPatchPackageError("client tree exceeds the byte limit")
    records.sort(key=lambda item: item.relative_path.casefold())
    return tuple(records)


def _copy_baseline_inventory(
    source: Path,
    destination: Path,
    records: tuple[BaselineFile, ...],
) -> None:
    for record in records:
        source_path = source / Path(record.relative_path)
        destination_path = destination / Path(record.relative_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)


def _parse_records(value: object) -> tuple[BaselineFile, ...]:
    if not isinstance(value, list):
        raise ClientPatchPackageError("files must be an array")
    records: list[BaselineFile] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ClientPatchPackageError("file inventory entry must be an object")
        _fields(raw, {"relative_path", "size", "sha256"}, "file inventory entry")
        try:
            records.append(
                BaselineFile(
                    relative_path=raw["relative_path"],  # type: ignore[arg-type]
                    size=raw["size"],  # type: ignore[arg-type]
                    sha256=raw["sha256"],  # type: ignore[arg-type]
                )
            )
        except ValueError as exc:
            raise ClientPatchPackageError(f"invalid file inventory entry: {exc}") from exc
    result = tuple(records)
    try:
        _validate_records(result)
    except ValueError as exc:
        raise ClientPatchPackageError(str(exc)) from exc
    return result


def _validate_records(records: tuple[BaselineFile, ...]) -> None:
    if not records:
        raise ValueError("file inventory must not be empty")
    if tuple(sorted(records, key=lambda item: item.relative_path.casefold())) != records:
        raise ValueError("file inventory must use canonical sorted order")
    if len({item.relative_path.casefold() for item in records}) != len(records):
        raise ValueError("file inventory contains duplicate case-insensitive paths")


def _unique_record(records: tuple[BaselineFile, ...], relative_path: str) -> BaselineFile:
    matches = tuple(
        record
        for record in records
        if record.relative_path.casefold() == relative_path.casefold()
    )
    if len(matches) != 1:
        raise ClientPatchPackageError(f"file is not unique in inventory: {relative_path}")
    return matches[0]


def _tree_sha256(records: tuple[BaselineFile, ...]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record.size).encode("ascii"))
        digest.update(b"\0")
        digest.update(record.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _manifest_sha256(manifest: PatchManifest) -> str:
    data = json.dumps(
        manifest.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ClientPatchPackageError(f"could not read evidence file: {path}") from exc
    if len(data) > _MAX_EVIDENCE_BYTES:
        raise ClientPatchPackageError("evidence file exceeds the byte limit")
    try:
        payload = json.loads(
            data.decode("utf-8-sig"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ClientPatchPackageError("evidence file is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ClientPatchPackageError("evidence file must contain a JSON object")
    return payload


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ClientPatchPackageError(f"evidence contains duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ClientPatchPackageError(f"evidence contains forbidden JSON constant: {value}")


def _fields(payload: dict[str, object], expected: set[str], context: str) -> None:
    missing = expected - payload.keys()
    unknown = payload.keys() - expected
    if missing:
        raise ClientPatchPackageError(f"{context} is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ClientPatchPackageError(f"{context} has unknown fields: {', '.join(sorted(unknown))}")


def _relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ValueError("relative path must be canonical POSIX form")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("relative path must remain beneath the client root")
    if path.as_posix() != value:
        raise ValueError("relative path must be canonical POSIX form")
    return value


def _relative_path_value(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ClientPatchPackageError(f"{field_name} must be a string")
    try:
        return _relative_path(value)
    except ValueError as exc:
        raise ClientPatchPackageError(f"invalid {field_name}: {exc}") from exc


def _sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.casefold()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be lowercase hexadecimal SHA-256")


def _sha256_value(value: object, field_name: str) -> str:
    try:
        _sha256(value, field_name)  # type: ignore[arg-type]
    except ValueError as exc:
        raise ClientPatchPackageError(str(exc)) from exc
    return value  # type: ignore[return-value]


def _timestamp(value: str, field_name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")


def _timestamp_value(value: object, field_name: str) -> None:
    try:
        _timestamp(value, field_name)  # type: ignore[arg-type]
    except ValueError as exc:
        raise ClientPatchPackageError(str(exc)) from exc


def _nonempty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ClientPatchPackageError(f"{field_name} must be non-empty")
    return value


def _require_count(value: object, expected: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise ClientPatchPackageError(f"{field_name} does not match the inventory")


def _canonical_timestamp(value: datetime | None) -> str:
    current = datetime.now(UTC) if value is None else value
    if current.tzinfo is None:
        raise ClientPatchPackageError("timestamp must include a timezone")
    return current.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    text = _json_text(payload)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def _write_temporary_json(parent: Path, payload: dict[str, object]) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".rollback-receipt.tmp-", dir=str(parent))
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(_json_text(payload))
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _json_text(payload: dict[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return False
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse)


__all__ = [
    "PATCH_PACKAGE_SCHEMA_VERSION",
    "ROLLBACK_RECEIPT_SCHEMA_VERSION",
    "ClientPatchPackageError",
    "PatchPackageEvidence",
    "PatchPackageResult",
    "RollbackReceipt",
    "VerifiedClientBaseline",
    "discard_patched_client_copy",
    "prepare_patched_client_copy",
    "verify_frozen_client_baseline",
    "verify_patched_client_copy",
]
