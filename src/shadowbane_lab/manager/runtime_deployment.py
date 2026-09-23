"""Transactional deployment of one verified, guest-local runtime per client slot."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.client_extension.manifest import PatchManifest, load_patch_manifest
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
from .runtime_paths import (
    GuestWindowsPath,
    HostRuntimePath,
    RuntimePathMapper,
    local_windows_runtime_mapper,
)

RUNTIME_DEPLOYMENT_SCHEMA_VERSION = 2
_DEPLOYMENT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DEPLOYMENT_FILE_NAME = "runtime-deployment.json"
_INPUT_DIRECTORY_NAME = ".deployment-inputs"
_PATCH_MANIFEST_FILE_NAME = "bootstrap-manifest.json"
_MAX_DEPLOYMENT_EVIDENCE_BYTES = 4 * 1024 * 1024


class RuntimeDeploymentError(RuntimeError):
    """Raised when isolated client runtimes cannot be published as one deployment."""


@dataclass(frozen=True, slots=True)
class _RuntimeInputs:
    baseline_directory: Path
    baseline_tree_sha256: str
    patch_manifest: PatchManifest
    extension_artifact: Path
    resolution_width: int
    resolution_height: int


@dataclass(slots=True)
class PreparedIsolatedRuntimeSlot:
    """One verified unpublished slot that can be committed to the manager manifest."""

    manifest: ManagerManifest
    client_id: str
    deployment_directory: Path
    runtime_root: Path
    _discarded: bool = False

    def discard(self) -> None:
        """Remove only this newly prepared deployment before its manifest is committed."""

        if self._discarded:
            return
        deployment = self.deployment_directory.resolve(strict=False)
        runtime_root = self.runtime_root.resolve(strict=False)
        if deployment.parent != runtime_root or not deployment.name.startswith("live-"):
            raise RuntimeDeploymentError(
                f"refusing to discard an unexpected runtime deployment: {deployment}"
            )
        if deployment.exists():
            if _is_reparse_point(deployment):
                raise RuntimeDeploymentError(
                    f"refusing to discard a reparse-point deployment: {deployment}"
                )
            evidence_path = deployment / _DEPLOYMENT_FILE_NAME
            if not evidence_path.is_file() or evidence_path.is_symlink():
                raise RuntimeDeploymentError(
                    "refusing to discard a prepared runtime without exact deployment evidence: "
                    f"{deployment}"
                )
            shutil.rmtree(deployment)
            if deployment.exists():
                raise RuntimeDeploymentError(
                    f"prepared runtime could not be discarded: {deployment}"
                )
        self._discarded = True


class IsolatedRuntimeCapacityProvisioner:
    """Prepare fresh isolated slots from immutable deployment inputs."""

    def __init__(
        self,
        manager_manifest_path: str | Path,
        *,
        path_mapper: RuntimePathMapper | None = None,
    ) -> None:
        manifest_path = Path(manager_manifest_path).resolve(strict=False)
        _require_host_local_path(manifest_path, field_name="manager_manifest_path")
        self._manifest_path = manifest_path
        self._path_mapper = path_mapper or local_windows_runtime_mapper(
            Path(manifest_path.anchor)
        )
        self._runtime_root = manifest_path.parent / "client-runtimes"

    def prepare(self, manifest: ManagerManifest) -> PreparedIsolatedRuntimeSlot:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        if any(client.window_tile is not None for client in manifest.clients):
            raise RuntimeDeploymentError(
                "isolated runtime provisioning requires a completely tile-less manifest"
            )
        if len(manifest.clients) >= MAX_MANAGER_CLIENT_SLOTS:
            raise RuntimeDeploymentError(
                f"no more than {MAX_MANAGER_CLIENT_SLOTS} clients can be managed"
            )

        inputs = _resolve_runtime_inputs(self._manifest_path, manifest, self._path_mapper)
        expanded = expand_manager_slots(manifest, len(manifest.clients) + 1)
        client_id = expanded.clients[-1].client_id
        timestamp = datetime.now(UTC)
        deployment_id = (
            f"live-{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:8]}"
        )
        deployment_path = self._runtime_root / deployment_id
        _require_host_local_path(deployment_path, field_name="deployment_directory")
        if deployment_path.exists():
            raise RuntimeDeploymentError(
                f"generated live deployment already exists: {deployment_path}"
            )

        self._runtime_root.mkdir(parents=True, exist_ok=True)
        deployment_path.mkdir()
        try:
            stored_manifest, stored_extension = _persist_runtime_inputs(
                deployment_path,
                inputs.patch_manifest,
                inputs.extension_artifact,
            )
            runtime_path = deployment_path / client_id
            result = prepare_patched_client_copy(
                inputs.baseline_directory,
                runtime_path,
                stored_manifest,
                stored_extension,
                created_at=timestamp,
            )
            if not result.destination_published or result.evidence is None:
                raise RuntimeDeploymentError(
                    f"client package was not published for {client_id}"
                )

            template = replace(manifest.clients[0], client_id=client_id)
            isolated = retarget_manager_client_directories(
                ManagerManifest(node_id=manifest.node_id, clients=(template,)),
                {
                    client_id: str(
                        self._path_mapper.host_to_guest(
                            HostRuntimePath(runtime_path)
                        ).path
                    )
                },
                executable_name=inputs.patch_manifest.source.file_name,
                resolution_width=inputs.resolution_width,
                resolution_height=inputs.resolution_height,
            ).clients[0]
            replacement = ManagerManifest(
                node_id=manifest.node_id,
                clients=(*manifest.clients, isolated),
            )
            slot = RuntimeDeploymentSlot(
                client_id=client_id,
                runtime_directory=result.evidence.destination_directory,
                package_working_tree_sha256=result.evidence.working_tree_sha256,
                executable_sha256=result.evidence.result_executable_sha256,
                extension_sha256=result.evidence.extension_sha256,
            )
            _write_new_json(
                deployment_path / _DEPLOYMENT_FILE_NAME,
                _deployment_evidence(
                    deployment_id=deployment_id,
                    deployment_path=deployment_path,
                    manifest_path=self._manifest_path,
                    baseline_directory=str(inputs.baseline_directory),
                    baseline_tree_sha256=inputs.baseline_tree_sha256,
                    repository_revision=result.evidence.repository_revision,
                    patch_manifest=stored_manifest,
                    resolution_width=inputs.resolution_width,
                    resolution_height=inputs.resolution_height,
                    slots=(slot,),
                    created_at=timestamp,
                    deployment_kind="live-slot",
                ),
            )
            return PreparedIsolatedRuntimeSlot(
                manifest=replacement,
                client_id=client_id,
                deployment_directory=deployment_path,
                runtime_root=self._runtime_root,
            )
        except Exception as exc:
            shutil.rmtree(deployment_path, ignore_errors=True)
            if deployment_path.exists():
                raise RuntimeDeploymentError(
                    f"failed live deployment could not be removed: {deployment_path}"
                ) from exc
            raise


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
    path_mapper: RuntimePathMapper | None = None,
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
    _require_host_local_path(manifest_path, field_name="manager_manifest_path")
    _require_host_local_path(baseline_path, field_name="frozen_directory")
    _require_host_local_path(deployment_path, field_name="deployment_directory")
    runtime_path_mapper = path_mapper or local_windows_runtime_mapper(Path(manifest_path.anchor))
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

    published_manifest = False
    deployment_path.parent.mkdir(parents=True, exist_ok=True)
    deployment_path.mkdir()
    try:
        stored_manifest, stored_extension = _persist_runtime_inputs(
            deployment_path,
            patch_manifest,
            extension_path,
        )
        package_evidence: list[tuple[str, PatchPackageEvidence]] = []
        runtime_directories: dict[str, str] = {}
        for client in target.clients:
            runtime_path = deployment_path / client.client_id
            result = prepare_patched_client_copy(
                baseline_path,
                runtime_path,
                stored_manifest,
                stored_extension,
                created_at=timestamp,
            )
            if not result.destination_published or result.evidence is None:
                raise RuntimeDeploymentError(
                    f"client package was not published for {client.client_id}"
                )
            package_evidence.append((client.client_id, result.evidence))
            runtime_directories[client.client_id] = str(
                runtime_path_mapper.host_to_guest(HostRuntimePath(runtime_path)).path
            )

        replacement = retarget_manager_client_directories(
            target,
            runtime_directories,
            executable_name=executable_name,
            resolution_width=resolution_width,
            resolution_height=resolution_height,
        )
        for client_id, evidence in package_evidence:
            executable = (
                HostRuntimePath(Path(evidence.destination_directory)).path / executable_name
            )
            if not executable.is_file():
                raise RuntimeDeploymentError(
                    "published runtime executable was not found for "
                    f"{client_id}: {executable}"
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
        deployment_evidence = _deployment_evidence(
            deployment_id=deployment_id,
            deployment_path=deployment_path,
            manifest_path=manifest_path,
            baseline_directory=baseline.directory,
            baseline_tree_sha256=baseline.tree_sha256,
            repository_revision=baseline.repository_revision,
            patch_manifest=stored_manifest,
            resolution_width=resolution_width,
            resolution_height=resolution_height,
            slots=slots,
            created_at=timestamp,
            deployment_kind="initial",
        )
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


def _persist_runtime_inputs(
    deployment_path: Path,
    patch_manifest: PatchManifest,
    extension_artifact: Path,
) -> tuple[PatchManifest, Path]:
    input_directory = deployment_path / _INPUT_DIRECTORY_NAME
    input_directory.mkdir()
    manifest_path = input_directory / _PATCH_MANIFEST_FILE_NAME
    _write_new_json(manifest_path, patch_manifest.as_dict())
    stored_manifest = load_patch_manifest(manifest_path)
    if stored_manifest != patch_manifest:
        raise RuntimeDeploymentError("stored patch manifest did not round-trip exactly")

    extension_path = Path(extension_artifact).resolve(strict=False)
    if not extension_path.is_file() or extension_path.is_symlink():
        raise RuntimeDeploymentError(
            f"extension artifact must be an existing regular file: {extension_path}"
        )
    stored_extension = input_directory / patch_manifest.extension.file_name
    with extension_path.open("rb") as source, stored_extension.open("xb") as destination:
        shutil.copyfileobj(source, destination)
        destination.flush()
        os.fsync(destination.fileno())
    if _file_sha256(stored_extension) != patch_manifest.extension.sha256:
        raise RuntimeDeploymentError("stored extension artifact does not match its pinned hash")
    return stored_manifest, stored_extension


def _deployment_evidence(
    *,
    deployment_id: str,
    deployment_path: Path,
    manifest_path: Path,
    baseline_directory: str,
    baseline_tree_sha256: str,
    repository_revision: str,
    patch_manifest: PatchManifest,
    resolution_width: int,
    resolution_height: int,
    slots: tuple[RuntimeDeploymentSlot, ...],
    created_at: datetime,
    deployment_kind: str,
) -> dict[str, object]:
    return {
        "schema_version": RUNTIME_DEPLOYMENT_SCHEMA_VERSION,
        "deployment_id": deployment_id,
        "deployment_kind": deployment_kind,
        "created_at_utc": (
            created_at.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        ),
        "deployment_directory": str(deployment_path),
        "manager_manifest_path": str(manifest_path),
        "baseline_directory": baseline_directory,
        "baseline_tree_sha256": baseline_tree_sha256,
        "repository_revision": repository_revision,
        "patch_id": patch_manifest.patch_id,
        "patch_manifest_sha256": _patch_manifest_sha256(patch_manifest),
        "resolution": f"{resolution_width}x{resolution_height}",
        "inputs": {
            "patch_manifest": f"{_INPUT_DIRECTORY_NAME}/{_PATCH_MANIFEST_FILE_NAME}",
            "extension_artifact": (
                f"{_INPUT_DIRECTORY_NAME}/{patch_manifest.extension.file_name}"
            ),
        },
        "slot_count": len(slots),
        "slots": [slot.as_dict() for slot in slots],
    }


def _resolve_runtime_inputs(
    manifest_path: Path,
    manifest: ManagerManifest,
    path_mapper: RuntimePathMapper,
) -> _RuntimeInputs:
    evidence_records: list[tuple[Path, dict[str, object]]] = []
    for client in manifest.clients:
        runtime_path = path_mapper.guest_to_host(
            GuestWindowsPath(client.launch.working_directory)
        ).path
        evidence_path = runtime_path.parent / _DEPLOYMENT_FILE_NAME
        evidence = _load_deployment_evidence(evidence_path)
        manager_manifest_path = evidence.get("manager_manifest_path")
        if not isinstance(manager_manifest_path, str) or (
            Path(manager_manifest_path).resolve(strict=False) != manifest_path
        ):
            raise RuntimeDeploymentError(
                f"deployment evidence belongs to another manager manifest: {evidence_path}"
            )
        deployment_directory = evidence.get("deployment_directory")
        if not isinstance(deployment_directory, str) or (
            Path(deployment_directory).resolve(strict=False) != runtime_path.parent
        ):
            raise RuntimeDeploymentError(
                f"deployment evidence does not own runtime {runtime_path}"
            )
        slots = evidence.get("slots")
        if not isinstance(slots, list) or not any(
            isinstance(slot, dict)
            and slot.get("client_id") == client.client_id
            and isinstance(slot.get("runtime_directory"), str)
            and Path(slot["runtime_directory"]).resolve(strict=False) == runtime_path
            for slot in slots
        ):
            raise RuntimeDeploymentError(
                f"deployment evidence does not name exact slot {client.client_id}"
            )
        evidence_records.append((evidence_path, evidence))

    first_path, first = evidence_records[0]
    baseline_text = first.get("baseline_directory")
    baseline_hash = first.get("baseline_tree_sha256")
    patch_id = first.get("patch_id")
    resolution = first.get("resolution")
    if not all(isinstance(value, str) and value for value in (
        baseline_text,
        baseline_hash,
        patch_id,
        resolution,
    )):
        raise RuntimeDeploymentError(f"deployment evidence is incomplete: {first_path}")
    assert isinstance(baseline_text, str)
    assert isinstance(baseline_hash, str)
    assert isinstance(patch_id, str)
    assert isinstance(resolution, str)
    expected_facts = (baseline_text.casefold(), baseline_hash, patch_id, resolution)
    for evidence_path, evidence in evidence_records[1:]:
        facts = (
            str(evidence.get("baseline_directory", "")).casefold(),
            evidence.get("baseline_tree_sha256"),
            evidence.get("patch_id"),
            evidence.get("resolution"),
        )
        if facts != expected_facts:
            raise RuntimeDeploymentError(
                "current isolated slots do not share one immutable deployment recipe: "
                f"{evidence_path}"
            )

    baseline_path = Path(baseline_text).resolve(strict=False)
    baseline = verify_frozen_client_baseline(baseline_path)
    if baseline.tree_sha256 != baseline_hash:
        raise RuntimeDeploymentError("frozen baseline differs from deployment evidence")
    width, height = _parse_resolution(resolution)

    input_path, input_evidence = next(
        (
            (evidence_path, evidence)
            for evidence_path, evidence in evidence_records
            if evidence.get("schema_version") == RUNTIME_DEPLOYMENT_SCHEMA_VERSION
        ),
        (first_path, first),
    )
    schema_version = input_evidence.get("schema_version")
    if schema_version == RUNTIME_DEPLOYMENT_SCHEMA_VERSION:
        inputs = input_evidence.get("inputs")
        if not isinstance(inputs, dict):
            raise RuntimeDeploymentError(f"deployment inputs are missing: {input_path}")
        patch_path = _resolve_deployment_input(
            input_path.parent,
            inputs.get("patch_manifest"),
            field_name="patch_manifest",
        )
        extension_path = _resolve_deployment_input(
            input_path.parent,
            inputs.get("extension_artifact"),
            field_name="extension_artifact",
        )
        patch_manifest = load_patch_manifest(patch_path)
        manifest_hash = input_evidence.get("patch_manifest_sha256")
        if not isinstance(manifest_hash, str) or (
            _patch_manifest_sha256(patch_manifest) != manifest_hash
        ):
            raise RuntimeDeploymentError(
                f"stored patch manifest differs from deployment evidence: {patch_path}"
            )
    elif schema_version == 1:
        patch_manifest = _find_legacy_patch_manifest(manifest_path.parent, patch_id)
        extension_path = (
            path_mapper.guest_to_host(
                GuestWindowsPath(manifest.clients[0].launch.working_directory)
            ).path
            / patch_manifest.extension.file_name
        )
    else:
        raise RuntimeDeploymentError(
            f"unsupported runtime deployment schema {schema_version!r}: {input_path}"
        )

    if patch_manifest.patch_id != patch_id:
        raise RuntimeDeploymentError("patch manifest differs from deployment evidence")
    if not extension_path.is_file() or extension_path.is_symlink():
        raise RuntimeDeploymentError(
            f"pinned extension artifact is unavailable: {extension_path}"
        )
    if _file_sha256(extension_path) != patch_manifest.extension.sha256:
        raise RuntimeDeploymentError("extension artifact differs from the patch manifest")
    return _RuntimeInputs(
        baseline_directory=baseline_path,
        baseline_tree_sha256=baseline_hash,
        patch_manifest=patch_manifest,
        extension_artifact=extension_path,
        resolution_width=width,
        resolution_height=height,
    )


def _load_deployment_evidence(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeDeploymentError(f"runtime deployment evidence was not found: {path}")
    data = path.read_bytes()
    if len(data) > _MAX_DEPLOYMENT_EVIDENCE_BYTES:
        raise RuntimeDeploymentError(f"runtime deployment evidence is too large: {path}")
    try:
        payload = json.loads(data, object_pairs_hook=_reject_duplicate_json_fields)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeDeploymentError(f"invalid runtime deployment evidence: {path}") from exc
    if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
        raise RuntimeDeploymentError(f"runtime deployment evidence must be an object: {path}")
    return payload


def _resolve_deployment_input(
    deployment_path: Path,
    value: object,
    *,
    field_name: str,
) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise RuntimeDeploymentError(f"deployment {field_name} must be a relative path")
    resolved = (deployment_path / value).resolve(strict=False)
    if not resolved.is_relative_to(deployment_path.resolve(strict=False)):
        raise RuntimeDeploymentError(f"deployment {field_name} escapes its deployment")
    if not resolved.is_file() or _is_reparse_point(resolved):
        raise RuntimeDeploymentError(
            f"deployment {field_name} must be an existing regular file: {resolved}"
        )
    return resolved


def _find_legacy_patch_manifest(state_root: Path, patch_id: str) -> PatchManifest:
    input_root = state_root / "deployment-inputs"
    matches: list[PatchManifest] = []
    if input_root.is_dir() and not input_root.is_symlink():
        for candidate in input_root.rglob("*.json"):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            try:
                manifest = load_patch_manifest(candidate)
            except (OSError, RuntimeError, ValueError):
                continue
            if manifest.patch_id == patch_id:
                matches.append(manifest)
    if not matches:
        raise RuntimeDeploymentError(
            "legacy deployment is missing its local patch manifest; reprovision isolated "
            "runtimes once before adding another client"
        )
    first = matches[0]
    if any(candidate != first for candidate in matches[1:]):
        raise RuntimeDeploymentError(
            f"multiple different local patch manifests claim patch ID {patch_id!r}"
        )
    return first


def _parse_resolution(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"([1-9][0-9]{0,4})x([1-9][0-9]{0,4})", value)
    if match is None:
        raise RuntimeDeploymentError(f"invalid deployment resolution: {value!r}")
    width, height = int(match.group(1)), int(match.group(2))
    if width > 16_384 or height > 16_384:
        raise RuntimeDeploymentError(f"deployment resolution is too large: {value!r}")
    return width, height


def _patch_manifest_sha256(manifest: PatchManifest) -> str:
    data = json.dumps(
        manifest.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(data).hexdigest()


def _reject_duplicate_json_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeDeploymentError(
                f"runtime deployment evidence contains duplicate field {key!r}"
            )
        result[key] = value
    return result


def _is_reparse_point(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction(path))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _require_host_local_path(path: Path, *, field_name: str) -> None:
    text = str(path)
    if text.startswith(("\\\\", "//")):
        raise RuntimeDeploymentError(f"{field_name} must be host-local, not a UNC path")


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
    "IsolatedRuntimeCapacityProvisioner",
    "PreparedIsolatedRuntimeSlot",
    "RuntimeDeploymentError",
    "RuntimeDeploymentResult",
    "RuntimeDeploymentSlot",
    "provision_isolated_client_runtimes",
]
