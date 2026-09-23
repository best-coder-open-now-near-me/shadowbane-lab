"""Fail-closed binding from deployment evidence to produced runtime slots."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from shadowbane_lab.client_extension.manifest import load_patch_manifest
from shadowbane_lab.client_extension.package import verify_patched_client_copy
from shadowbane_lab.manager.runtime_deployment import RUNTIME_DEPLOYMENT_SCHEMA_VERSION

from .model import (
    DeploymentIdentity,
    DeploymentSlotIdentity,
    RuntimeConsistencyError,
    canonical_sha256,
)

_MAX_DEPLOYMENT_EVIDENCE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProducedRuntimeSlot:
    client_id: str
    runtime_directory: Path


@dataclass(frozen=True, slots=True)
class ProducedDeployment:
    evidence_path: Path
    deployment_directory: Path
    identity: DeploymentIdentity
    slots: tuple[ProducedRuntimeSlot, ...]


def inspect_produced_deployment(path: str | Path) -> ProducedDeployment:
    """Reread deployment and package evidence before any runtime command executes."""

    evidence_path = Path(path).resolve(strict=False)
    payload = _load_evidence(evidence_path)
    required = {
        "schema_version",
        "deployment_id",
        "deployment_kind",
        "created_at_utc",
        "deployment_directory",
        "manager_manifest_path",
        "baseline_directory",
        "baseline_tree_sha256",
        "repository_revision",
        "patch_id",
        "patch_manifest_sha256",
        "resolution",
        "inputs",
        "slot_count",
        "slots",
    }
    _exact(payload, required, "runtime deployment evidence")
    if payload["schema_version"] != RUNTIME_DEPLOYMENT_SCHEMA_VERSION:
        raise RuntimeConsistencyError(
            f"runtime consistency requires deployment schema {RUNTIME_DEPLOYMENT_SCHEMA_VERSION}"
        )

    deployment_text = _string(payload, "deployment_directory")
    deployment_directory = Path(deployment_text).resolve(strict=False)
    if deployment_directory != evidence_path.parent:
        raise RuntimeConsistencyError(
            "deployment evidence path does not match deployment_directory"
        )
    if not deployment_directory.is_dir() or deployment_directory.is_symlink():
        raise RuntimeConsistencyError("deployment directory is not a regular directory")

    patch_id = _string(payload, "patch_id")
    patch_manifest_sha256 = _sha256(payload, "patch_manifest_sha256")
    inputs = _object(payload.get("inputs"), "inputs")
    _exact(inputs, {"patch_manifest", "extension_artifact"}, "deployment inputs")
    patch_manifest_path = _deployment_input(
        deployment_directory,
        inputs.get("patch_manifest"),
        "patch_manifest",
    )
    extension_artifact = _deployment_input(
        deployment_directory,
        inputs.get("extension_artifact"),
        "extension_artifact",
    )
    try:
        manifest = load_patch_manifest(patch_manifest_path)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeConsistencyError(f"stored patch manifest is invalid: {exc}") from exc
    if manifest.patch_id != patch_id:
        raise RuntimeConsistencyError("stored patch manifest patch_id differs from deployment")
    if canonical_sha256(manifest.as_dict()) != patch_manifest_sha256:
        raise RuntimeConsistencyError("stored patch manifest hash differs from deployment")
    if extension_artifact.name.casefold() != manifest.extension.file_name.casefold():
        raise RuntimeConsistencyError("stored extension file name differs from patch manifest")
    if _file_sha256(extension_artifact) != manifest.extension.sha256:
        raise RuntimeConsistencyError("stored extension hash differs from patch manifest")

    raw_slots = payload.get("slots")
    if not isinstance(raw_slots, list) or not raw_slots:
        raise RuntimeConsistencyError("deployment slots must be a non-empty array")
    slot_count = payload.get("slot_count")
    if (
        isinstance(slot_count, bool)
        or not isinstance(slot_count, int)
        or slot_count != len(raw_slots)
    ):
        raise RuntimeConsistencyError("deployment slot_count does not match slots")

    baseline_hash = _sha256(payload, "baseline_tree_sha256")
    repository_revision = _string(payload, "repository_revision")
    slot_identities: list[DeploymentSlotIdentity] = []
    runtime_slots: list[ProducedRuntimeSlot] = []
    for raw_slot in raw_slots:
        slot = _object(raw_slot, "deployment slot")
        _exact(
            slot,
            {
                "client_id",
                "runtime_directory",
                "package_working_tree_sha256",
                "executable_sha256",
                "extension_sha256",
            },
            "deployment slot",
        )
        client_id = _string(slot, "client_id")
        runtime_directory = Path(_string(slot, "runtime_directory")).resolve(strict=False)
        if runtime_directory.parent != deployment_directory:
            raise RuntimeConsistencyError(
                f"runtime slot {client_id} is not a direct child of its deployment"
            )
        if runtime_directory.name != client_id:
            raise RuntimeConsistencyError(
                f"runtime slot directory name differs from client_id {client_id}"
            )
        try:
            package = verify_patched_client_copy(runtime_directory)
        except (OSError, RuntimeError, ValueError) as exc:
            raise RuntimeConsistencyError(
                f"runtime slot {client_id} failed package verification: {exc}"
            ) from exc
        expected = {
            "package_working_tree_sha256": package.working_tree_sha256,
            "executable_sha256": package.result_executable_sha256,
            "extension_sha256": package.extension_sha256,
        }
        for field_name, expected_value in expected.items():
            if _sha256(slot, field_name) != expected_value:
                raise RuntimeConsistencyError(
                    f"runtime slot {client_id} {field_name} differs from package evidence"
                )
        if package.baseline_tree_sha256 != baseline_hash:
            raise RuntimeConsistencyError(
                f"runtime slot {client_id} baseline differs from deployment"
            )
        if package.repository_revision != repository_revision:
            raise RuntimeConsistencyError(
                f"runtime slot {client_id} repository revision differs from deployment"
            )
        if package.patch_id != patch_id or package.manifest_sha256 != patch_manifest_sha256:
            raise RuntimeConsistencyError(
                f"runtime slot {client_id} patch identity differs from deployment"
            )
        slot_identities.append(
            DeploymentSlotIdentity(
                client_id=client_id,
                package_working_tree_sha256=package.working_tree_sha256,
                executable_sha256=package.result_executable_sha256,
                extension_sha256=package.extension_sha256,
            )
        )
        runtime_slots.append(
            ProducedRuntimeSlot(client_id=client_id, runtime_directory=runtime_directory)
        )

    identity = DeploymentIdentity(
        deployment_id=_string(payload, "deployment_id"),
        deployment_kind=_string(payload, "deployment_kind"),
        baseline_tree_sha256=baseline_hash,
        repository_revision=repository_revision,
        patch_id=patch_id,
        patch_manifest_sha256=patch_manifest_sha256,
        resolution=_string(payload, "resolution"),
        slots=tuple(sorted(slot_identities, key=lambda item: item.client_id)),
    )
    return ProducedDeployment(
        evidence_path=evidence_path,
        deployment_directory=deployment_directory,
        identity=identity,
        slots=tuple(sorted(runtime_slots, key=lambda item: item.client_id)),
    )


def _load_evidence(path: Path) -> dict[str, object]:
    try:
        if not path.is_file() or path.is_symlink():
            raise RuntimeConsistencyError(
                f"runtime deployment evidence must be a regular file: {path}"
            )
        data = path.read_bytes()
    except OSError as exc:
        raise RuntimeConsistencyError(f"could not read runtime deployment evidence: {exc}") from exc
    if len(data) > _MAX_DEPLOYMENT_EVIDENCE_BYTES:
        raise RuntimeConsistencyError("runtime deployment evidence is too large")
    try:
        payload = json.loads(data, object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeConsistencyError("runtime deployment evidence is not valid JSON") from exc
    return dict(_object(payload, "runtime deployment evidence"))


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeConsistencyError(f"duplicate deployment evidence field {key!r}")
        result[key] = value
    return result


def _object(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RuntimeConsistencyError(f"{field_name} must be an object")
    return value


def _exact(value: dict[str, object], expected: set[str], field_name: str) -> None:
    if set(value) != expected:
        raise RuntimeConsistencyError(f"{field_name} fields are not exact")


def _string(value: dict[str, object], field_name: str) -> str:
    item = value.get(field_name)
    if not isinstance(item, str) or not item:
        raise RuntimeConsistencyError(f"deployment {field_name} must be non-empty text")
    return item


def _sha256(value: dict[str, object], field_name: str) -> str:
    item = _string(value, field_name)
    if len(item) != 64 or any(character not in "0123456789abcdef" for character in item):
        raise RuntimeConsistencyError(f"deployment {field_name} must be a SHA-256 digest")
    return item


def _deployment_input(root: Path, value: object, field_name: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise RuntimeConsistencyError(f"deployment {field_name} must be a relative path")
    path = (root / value).resolve(strict=False)
    if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
        raise RuntimeConsistencyError(
            f"deployment {field_name} must be a regular file within the deployment"
        )
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = [
    "ProducedDeployment",
    "ProducedRuntimeSlot",
    "inspect_produced_deployment",
]
