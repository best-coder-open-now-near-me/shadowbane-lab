"""Composable offline capture of complete fingerprint envelopes."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shadowbane_lab.client_alignment import inspect_pe_bytes
from shadowbane_lab.integrity import (
    canonical_json_sha256,
    canonical_timestamp,
    hash_file,
    inventory_tree,
    load_strict_json,
)

from .model import Applicability, FingerprintEnvelope, FingerprintSection, SectionName


@dataclass(frozen=True, slots=True)
class FingerprintCaptureInputs:
    client_directory: Path | None = None
    client_executable: Path | None = None
    runtime_executable: Path | None = None
    process_id: int | None = None
    service_profile: str | None = None
    service_endpoint: str | None = None
    environment_id: str | None = None
    fixture_path: Path | None = None
    ruleset_id: str | None = None
    policy_id: str | None = None
    scenario_id: str | None = None
    experiment_id: str | None = None
    source_artifact_ids: tuple[tuple[SectionName, str], ...] = ()
    additional_identity_files: tuple[tuple[str, Path], ...] = ()
    repository_directory: Path | None = None


def capture_fingerprint(inputs: FingerprintCaptureInputs) -> FingerprintEnvelope:
    return FingerprintEnvelope(
        captured_at_utc=canonical_timestamp(),
        sections=(
            _client_section(inputs),
            _runtime_section(inputs),
            _service_section(inputs),
            _environment_section(inputs),
            _fixture_section(inputs),
            _execution_section(inputs),
        ),
    )


def _client_section(inputs: FingerprintCaptureInputs) -> FingerprintSection:
    if inputs.client_directory is None and inputs.client_executable is None:
        if sources := _sources(inputs, SectionName.CLIENT):
            return _source_only(SectionName.CLIENT, sources)
        return _not_applicable(SectionName.CLIENT, "no client installation was in scope")
    durable: dict[str, Any] = {}
    findings: list[str] = []
    if inputs.client_directory is not None:
        inventory = inventory_tree(inputs.client_directory)
        durable.update(
            {
                "file_count": len(inventory.files),
                "total_bytes": inventory.total_bytes,
                "tree_sha256": inventory.tree_sha256,
            }
        )
    if inputs.client_executable is not None:
        executable = inspect_pe_bytes(
            inputs.client_executable.read_bytes(), path=inputs.client_executable.name
        )
        durable.update(
            {
                "executable.sha256": executable.sha256,
                "executable.length": executable.length,
                "executable.machine": executable.machine,
                "executable.pointer_size": executable.pointer_size,
                "executable.entry_point_rva": executable.entry_point_rva,
                "executable.sections": [
                    {
                        "name": section.name,
                        "virtual_address": section.virtual_address,
                        "virtual_size": section.virtual_size,
                        "raw_size": section.raw_size,
                        "sha256": section.sha256,
                    }
                    for section in executable.sections
                ],
            }
        )
        if inputs.client_directory is not None:
            try:
                inputs.client_executable.resolve().relative_to(inputs.client_directory.resolve())
            except ValueError:
                findings.append("client executable is outside the inventoried client directory")
    durable.update(_identity_file_values(inputs.additional_identity_files, "client"))
    return FingerprintSection(
        name=SectionName.CLIENT,
        applicability=Applicability.APPLICABLE,
        durable=tuple(sorted(durable.items())),
        source_artifact_ids=_sources(inputs, SectionName.CLIENT),
        findings=tuple(sorted(findings)),
    )


def _runtime_section(inputs: FingerprintCaptureInputs) -> FingerprintSection:
    if inputs.runtime_executable is None and inputs.process_id is None:
        if sources := _sources(inputs, SectionName.RUNTIME):
            return _source_only(SectionName.RUNTIME, sources)
        return _not_applicable(SectionName.RUNTIME, "no live or produced runtime was in scope")
    durable: dict[str, Any] = {}
    volatile: dict[str, Any] = {}
    findings: list[str] = []
    if inputs.runtime_executable is not None:
        size, digest = hash_file(inputs.runtime_executable)
        durable["executable.sha256"] = digest
        durable["executable.size_bytes"] = size
    if inputs.process_id is not None:
        if inputs.process_id <= 0:
            raise ValueError("process_id must be positive")
        volatile["process_id"] = inputs.process_id
        findings.append("process identity is observational until a runtime executable is supplied")
        if inputs.runtime_executable is None:
            durable["process_identity_mode"] = "pid_only_unverified"
    durable.update(_identity_file_values(inputs.additional_identity_files, "runtime"))
    return FingerprintSection(
        name=SectionName.RUNTIME,
        applicability=Applicability.APPLICABLE,
        durable=tuple(sorted(durable.items())),
        volatile=tuple(sorted(volatile.items())),
        source_artifact_ids=_sources(inputs, SectionName.RUNTIME),
        findings=tuple(sorted(findings)),
    )


def _service_section(inputs: FingerprintCaptureInputs) -> FingerprintSection:
    if inputs.service_profile is None:
        if sources := _sources(inputs, SectionName.SERVICE):
            return _source_only(SectionName.SERVICE, sources)
        return _not_applicable(SectionName.SERVICE, "no live service was in scope")
    durable = {"profile": inputs.service_profile}
    if inputs.service_endpoint is not None:
        durable["endpoint"] = _sanitized_endpoint(inputs.service_endpoint)
    durable.update(_identity_file_values(inputs.additional_identity_files, "service"))
    return FingerprintSection(
        name=SectionName.SERVICE,
        applicability=Applicability.APPLICABLE,
        durable=tuple(sorted(durable.items())),
        source_artifact_ids=_sources(inputs, SectionName.SERVICE),
    )


def _environment_section(inputs: FingerprintCaptureInputs) -> FingerprintSection:
    revision = _git_revision(inputs.repository_directory)
    durable = {
        "environment_id": inputs.environment_id or "local-unspecified",
        "lab_revision": revision,
        "os.system": platform.system(),
        "os.release": platform.release(),
        "os.version": platform.version(),
        "machine": platform.machine(),
        "python.implementation": platform.python_implementation(),
        "python.version": platform.python_version(),
    }
    volatile = {
        "process_id": os.getpid(),
        "python.executable": sys.executable,
    }
    durable.update(_identity_file_values(inputs.additional_identity_files, "environment"))
    return FingerprintSection(
        name=SectionName.ENVIRONMENT,
        applicability=Applicability.APPLICABLE,
        durable=tuple(sorted(durable.items())),
        volatile=tuple(sorted(volatile.items())),
        source_artifact_ids=_sources(inputs, SectionName.ENVIRONMENT),
    )


def _fixture_section(inputs: FingerprintCaptureInputs) -> FingerprintSection:
    if inputs.fixture_path is None:
        if sources := _sources(inputs, SectionName.FIXTURE):
            return _source_only(SectionName.FIXTURE, sources)
        return _not_applicable(SectionName.FIXTURE, "no character fixture was in scope")
    fixture = load_strict_json(inputs.fixture_path)
    durable = {
        "fixture.sha256": canonical_json_sha256(fixture),
        "fixture.byte_sha256": hashlib.sha256(inputs.fixture_path.read_bytes()).hexdigest(),
    }
    durable.update(_identity_file_values(inputs.additional_identity_files, "fixture"))
    return FingerprintSection(
        name=SectionName.FIXTURE,
        applicability=Applicability.APPLICABLE,
        durable=tuple(sorted(durable.items())),
        source_artifact_ids=_sources(inputs, SectionName.FIXTURE),
    )


def _execution_section(inputs: FingerprintCaptureInputs) -> FingerprintSection:
    values = {
        name: value
        for name, value in (
            ("ruleset_id", inputs.ruleset_id),
            ("policy_id", inputs.policy_id),
            ("scenario_id", inputs.scenario_id),
            ("experiment_id", inputs.experiment_id),
        )
        if value is not None
    }
    values.update(_identity_file_values(inputs.additional_identity_files, "execution"))
    if not values:
        if sources := _sources(inputs, SectionName.EXECUTION):
            return _source_only(SectionName.EXECUTION, sources)
        return _not_applicable(SectionName.EXECUTION, "no lab execution was in scope")
    return FingerprintSection(
        name=SectionName.EXECUTION,
        applicability=Applicability.APPLICABLE,
        durable=tuple(sorted(values.items())),
        source_artifact_ids=_sources(inputs, SectionName.EXECUTION),
    )


def _not_applicable(name: SectionName, reason: str) -> FingerprintSection:
    return FingerprintSection(
        name=name,
        applicability=Applicability.NOT_APPLICABLE,
        reason=reason,
    )


def _source_only(name: SectionName, sources: tuple[str, ...]) -> FingerprintSection:
    return FingerprintSection(
        name=name,
        applicability=Applicability.APPLICABLE,
        durable=(("identity_mode", "source_artifacts_only"),),
        source_artifact_ids=sources,
        findings=("section identity depends on referenced evidence without local recapture",),
    )


def _sources(inputs: FingerprintCaptureInputs, name: SectionName) -> tuple[str, ...]:
    return tuple(
        sorted(
            artifact_id for section, artifact_id in inputs.source_artifact_ids if section is name
        )
    )


def _identity_file_values(values: Iterable[tuple[str, Path]], prefix: str) -> dict[str, object]:
    result: dict[str, object] = {}
    marker = prefix + "."
    for label, path in values:
        if not label.startswith(marker):
            continue
        size, digest = hash_file(path)
        result[f"identity_file.{label[len(marker) :]}.sha256"] = digest
        result[f"identity_file.{label[len(marker) :]}.size_bytes"] = size
    return result


def _git_revision(repository: Path | None) -> str:
    directory = Path.cwd() if repository is None else repository
    try:
        completed = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=directory,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _sanitized_endpoint(value: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("service endpoint must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("service endpoint must not contain query or fragment data")
    if parsed.scheme and parsed.hostname:
        port = "" if parsed.port is None else f":{parsed.port}"
        return urlunsplit((parsed.scheme, f"{parsed.hostname}{port}", parsed.path, "", ""))
    if any(marker in value for marker in ("@", "?", "#")):
        raise ValueError("service endpoint contains credential or session-like data")
    return value


__all__ = ["FingerprintCaptureInputs", "capture_fingerprint"]
