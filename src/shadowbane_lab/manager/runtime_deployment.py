"""Transactional deployment of one verified, guest-local runtime per client slot."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.client_extension.manifest import PatchManifest
from shadowbane_lab.client_extension.package import (
    ClientPatchPackageError,
    PatchPackageEvidence,
    prepare_patched_client_copy,
    verify_frozen_client_baseline,
)

from .live_configuration import replace_manager_manifest
from .manifest import (
    MAX_MANAGER_CLIENT_SLOTS,
    ManagerManifest,
    ManagerManifestError,
    expand_manager_slots,
    load_manager_manifest,
    retarget_manager_client_directories,
)

RUNTIME_DEPLOYMENT_SCHEMA_VERSION = 1
_DEPLOYMENT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DEPLOYMENT_FILE_NAME = "runtime-deployment.json"


class RuntimeDeploymentError(RuntimeError):
    """Raised when isolated client runtimes cannot be published as one deployment."""


@dataclass(frozen=True, slots=True)
class RuntimeDeploymentSlot:
    client_id: str
    runtime_directory: str
    package_working_tree_sha256: str
    executable_sha256: str
    extension_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "runtime_directory": self.runtime_directory,
            "package_working_tree_sha256": self.package_working_tree_sha256,
            "executable_sha256": self.executable_sha256,
            "extension_sha256": self.extension_sha256,
        }


@dataclass(frozen=True, slots=True)
class RuntimeDeploymentResult:
    deployment_id: str
    deployment_directory: str
    evidence_path: str
    manager_manifest_path: str
    manager_backup_path: str
    baseline_directory: str
    baseline_tree_sha256: str
    patch_id: str
    resolution: str
    slots: tuple[RuntimeDeploymentSlot, ...]
    schema_version: int = RUNTIME_DEPLOYMENT_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "deployment_id": self.deployment_id,
            "deployment_directory": self.deployment_directory,
            "evidence_path": self.evidence_path,
            "manager_manifest_path": self.manager_manifest_path,
            "manager_backup_path": self.manager_backup_path,
            "baseline_directory": self.baseline_directory,
            "baseline_tree_sha256": self.baseline_tree_sha256,
            "patch_id": self.patch_id,
            "resolution": self.resolution,
            "slot_count": len(self.slots),
            "slots": [slot.as_dict() for slot in self.slots],
        }


def provision_isolated_client_runtimes(
    manager_manifest_path: str | Path,
    frozen_directory: str | Path,
    deployment_directory: str | Path,
    patch_manifest: PatchManifest,
    extension_artifact: str | Path,
    *,
    deployment_id: str,
    slot_count: int | None = None,
    executable_name: str = "sb.exe",
    resolution_width: int = 1920,
    resolution_height: int = 955,
    created_at: datetime | None = None,
) -> RuntimeDeploymentResult:
    """Publish verified copies, then atomically point the manager at all of them.

    The deployment directory must be new and local.  Partial copies are never
    exposed through the manager manifest: every package is built and reread,
    immutable deployment evidence is written, and only then is the manifest
    replaced with compare-and-swap semantics.  A failure before that last step
    removes only the new deployment directory created by this call.
    """

    if not isinstance(patch_manifest, PatchManifest):
        raise RuntimeDeploymentError("patch_manifest must be a validated PatchManifest")
    if not isinstance(deployment_id, str) or not _DEPLOYMENT_ID_PATTERN.fullmatch(deployment_id):
        raise RuntimeDeploymentError(
            "deployment_id must contain only letters, digits, '.', '_', or '-'"
        )

    manifest_path = Path(manager_manifest_path).resolve(strict=False)
    baseline_path = Path(frozen_directory).resolve(strict=False)
    deployment_path = Path(deployment_directory).resolve(strict=False)
    extension_path = Path(extension_artifact).resolve(strict=False)
    _require_guest_local_path(manifest_path, field_name="manager_manifest_path")
    _require_guest_local_path(baseline_path, field_name="frozen_directory")
    _require_guest_local_path(deployment_path, field_name="deployment_directory")
    if deployment_path.exists():
        raise RuntimeDeploymentError(f"deployment directory already exists: {deployment_path}")
    if deployment_path.name != deployment_id:
        raise RuntimeDeploymentError("deployment directory name must exactly match deployment_id")

    try:
        current = load_manager_manifest(manifest_path)
        target = _manifest_with_slot_count(current, slot_count)
        baseline = verify_frozen_client_baseline(baseline_path)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeDeploymentError(f"deployment preflight failed: {exc}") from exc

    timestamp = datetime.now(UTC) if created_at is None else created_at
    if timestamp.tzinfo is None:
        raise RuntimeDeploymentError("created_at must include a timezone")
    timestamp_text = (
        timestamp.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )

    published_manifest = False
    deployment_path.parent.mkdir(parents=True, exist_ok=True)
    deployment_path.mkdir()
    try:
        package_evidence: list[tuple[str, PatchPackageEvidence]] = []
        runtime_directories: dict[str, str] = {}
        for client in target.clients:
            runtime_path = deployment_path / client.client_id
            result = prepare_patched_client_copy(
                baseline_path,
                runtime_path,
                patch_manifest,
                extension_path,
                created_at=timestamp,
            )
            if not result.destination_published or result.evidence is None:
                raise RuntimeDeploymentError(
                    f"client package was not published for {client.client_id}"
                )
            package_evidence.append((client.client_id, result.evidence))
            runtime_directories[client.client_id] = str(runtime_path)

        replacement = retarget_manager_client_directories(
            target,
            runtime_directories,
            executable_name=executable_name,
            resolution_width=resolution_width,
            resolution_height=resolution_height,
        )
        for client in replacement.clients:
            executable = Path(str(client.launch.executable))
            if not executable.is_file():
                raise RuntimeDeploymentError(
                    f"published runtime executable was not found: {executable}"
                )

        slots = tuple(
            RuntimeDeploymentSlot(
                client_id=client_id,
                runtime_directory=evidence.destination_directory,
                package_working_tree_sha256=evidence.working_tree_sha256,
                executable_sha256=evidence.result_executable_sha256,
                extension_sha256=evidence.extension_sha256,
            )
            for client_id, evidence in package_evidence
        )
        evidence_path = deployment_path / _DEPLOYMENT_FILE_NAME
        deployment_evidence = {
            "schema_version": RUNTIME_DEPLOYMENT_SCHEMA_VERSION,
            "deployment_id": deployment_id,
            "created_at_utc": timestamp_text,
            "deployment_directory": str(deployment_path),
            "manager_manifest_path": str(manifest_path),
            "baseline_directory": baseline.directory,
            "baseline_tree_sha256": baseline.tree_sha256,
            "repository_revision": baseline.repository_revision,
            "patch_id": patch_manifest.patch_id,
            "resolution": f"{resolution_width}x{resolution_height}",
            "slot_count": len(slots),
            "slots": [slot.as_dict() for slot in slots],
        }
        _write_new_json(evidence_path, deployment_evidence)
        backup_path = replace_manager_manifest(
            manifest_path,
            expected=current,
            replacement=replacement,
        )
        published_manifest = True
        return RuntimeDeploymentResult(
            deployment_id=deployment_id,
            deployment_directory=str(deployment_path),
            evidence_path=str(evidence_path),
            manager_manifest_path=str(manifest_path),
            manager_backup_path=str(backup_path),
            baseline_directory=baseline.directory,
            baseline_tree_sha256=baseline.tree_sha256,
            patch_id=patch_manifest.patch_id,
            resolution=f"{resolution_width}x{resolution_height}",
            slots=slots,
        )
    except RuntimeDeploymentError:
        raise
    except (ClientPatchPackageError, ManagerManifestError, OSError, ValueError) as exc:
        raise RuntimeDeploymentError(f"runtime deployment failed: {exc}") from exc
    finally:
        if not published_manifest and deployment_path.exists():
            shutil.rmtree(deployment_path, ignore_errors=True)
            if deployment_path.exists():
                raise RuntimeDeploymentError(
                    "unpublished deployment could not be removed; inspect "
                    f"{deployment_path} before retrying"
                )


def _manifest_with_slot_count(
    manifest: ManagerManifest,
    slot_count: int | None,
) -> ManagerManifest:
    if slot_count is None:
        return manifest
    if isinstance(slot_count, bool) or not isinstance(slot_count, int) or slot_count <= 0:
        raise RuntimeDeploymentError("slot_count must be a positive integer")
    if slot_count > MAX_MANAGER_CLIENT_SLOTS:
        raise RuntimeDeploymentError(f"slot_count must not exceed {MAX_MANAGER_CLIENT_SLOTS}")
    if slot_count == len(manifest.clients):
        return manifest
    if slot_count < len(manifest.clients):
        return ManagerManifest(node_id=manifest.node_id, clients=manifest.clients[:slot_count])
    return expand_manager_slots(manifest, slot_count)


def _require_guest_local_path(path: Path, *, field_name: str) -> None:
    text = str(path)
    if text.startswith(("\\\\", "//")):
        raise RuntimeDeploymentError(f"{field_name} must be guest-local, not a UNC path")


def _write_new_json(path: Path, payload: dict[str, object]) -> None:
    data = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    with path.open("xb") as destination:
        destination.write(data)
        destination.flush()
        os.fsync(destination.fileno())


__all__ = [
    "RUNTIME_DEPLOYMENT_SCHEMA_VERSION",
    "RuntimeDeploymentError",
    "RuntimeDeploymentResult",
    "RuntimeDeploymentSlot",
    "provision_isolated_client_runtimes",
]
