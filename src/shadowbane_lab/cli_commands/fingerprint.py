"""Complete execution fingerprint commands."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from shadowbane_lab.evidence.codec import save_contract
from shadowbane_lab.fingerprints import (
    FingerprintCaptureInputs,
    FingerprintError,
    ImpactState,
    SectionName,
    capture_fingerprint,
    compare_fingerprints,
    load_fingerprint,
    save_fingerprint,
)

from .common import _error


def handle(arguments: Namespace) -> int:
    as_json = bool(getattr(arguments, "json", False))
    try:
        if arguments.fingerprint_command == "capture":
            envelope = capture_fingerprint(
                FingerprintCaptureInputs(
                    client_directory=arguments.client_directory,
                    client_executable=arguments.client_executable,
                    runtime_executable=arguments.runtime_executable,
                    process_id=arguments.pid,
                    service_profile=arguments.service_profile,
                    service_endpoint=arguments.service_endpoint,
                    environment_id=arguments.environment_id,
                    fixture_path=arguments.fixture,
                    ruleset_id=arguments.ruleset_id,
                    policy_id=arguments.policy_id,
                    scenario_id=arguments.scenario_id,
                    experiment_id=arguments.experiment_id,
                    source_artifact_ids=tuple(
                        _section_artifact(value) for value in arguments.source_artifact or ()
                    ),
                    additional_identity_files=tuple(
                        _identity_file(value) for value in arguments.identity_file or ()
                    ),
                    repository_directory=arguments.repository,
                )
            )
            save_fingerprint(arguments.output, envelope)
            return _print(
                {
                    "ok": True,
                    "fingerprint_id": envelope.fingerprint_id,
                    "capture_id": envelope.capture_id,
                    "output": str(arguments.output),
                },
                as_json=as_json,
            )
        if arguments.fingerprint_command == "verify":
            envelope = load_fingerprint(arguments.fingerprint)
            return _print(
                {
                    "ok": True,
                    "fingerprint_id": envelope.fingerprint_id,
                    "capture_id": envelope.capture_id,
                    "applicable_sections": [
                        item.name.value
                        for item in envelope.sections
                        if item.applicability.value == "applicable"
                    ],
                },
                as_json=as_json,
            )
        if arguments.fingerprint_command == "diff":
            report = compare_fingerprints(
                load_fingerprint(arguments.reference),
                load_fingerprint(arguments.candidate),
            )
            if arguments.output is not None:
                save_contract(arguments.output, report)
            _print(
                {"ok": report.state is ImpactState.UNAFFECTED, **report.as_dict()},
                as_json=as_json,
            )
            return 0 if report.state is ImpactState.UNAFFECTED else 1
    except (FingerprintError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return _error(str(exc), as_json=as_json)
    return _error("unknown fingerprint command", as_json=as_json)


def _section_artifact(value: str) -> tuple[SectionName, str]:
    section, separator, artifact_id = value.partition("=")
    if not separator:
        raise ValueError("source artifact must use SECTION=sha256:<digest>")
    return SectionName(section), artifact_id


def _identity_file(value: str) -> tuple[str, Path]:
    label, separator, path = value.partition("=")
    if not separator or "." not in label:
        raise ValueError("identity file must use SECTION.LABEL=PATH")
    SectionName(label.split(".", 1)[0])
    return label, Path(path)


def _print(payload: dict[str, object], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, allow_nan=False, sort_keys=True))
    else:
        for name, value in payload.items():
            if name != "ok":
                print(f"{name}: {value}")
    return 0


__all__ = ["handle"]
