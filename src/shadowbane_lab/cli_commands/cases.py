"""Research-case and bounded-experiment commands."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from shadowbane_lab.cases import (
    CaseError,
    CaseState,
    DryRunExecutor,
    ExperimentReference,
    Hypothesis,
    RecordedExecutor,
    ResearchCase,
    execute_plan,
    expand_experiment,
    load_case,
    load_experiment,
    review_case,
    save_case,
)
from shadowbane_lab.evidence import (
    ArtifactStore,
    ManifestTerminalState,
    VerificationStatus,
    load_manifest,
    verify_manifest,
)
from shadowbane_lab.fingerprints import SectionName, load_fingerprint
from shadowbane_lab.integrity import canonical_timestamp, create_only_json, load_strict_json

from .common import _error


def handle_case(arguments: Namespace) -> int:
    as_json = bool(getattr(arguments, "json", False))
    try:
        if arguments.case_command == "create":
            hypotheses = tuple(
                sorted(
                    (_hypothesis(value) for value in arguments.hypothesis),
                    key=lambda item: item.hypothesis_id,
                )
            )
            case = ResearchCase(
                case_id=arguments.case_id,
                revision=1,
                title=arguments.title,
                owner=arguments.owner,
                created_at_utc=canonical_timestamp(),
                target_profile=arguments.target_profile,
                coverage_domains=tuple(sorted(set(arguments.domain))),
                question=arguments.question,
                hypotheses=hypotheses,
                state=CaseState.DRAFT,
                required_fingerprint_sections=tuple(
                    sorted(
                        {SectionName(value) for value in arguments.fingerprint_section},
                        key=lambda item: item.value,
                    )
                ),
                required_capture_channels=tuple(sorted(set(arguments.capture_channel))),
                experiments=tuple(
                    sorted(
                        (_experiment_reference(value) for value in arguments.experiment),
                        key=lambda item: (item.experiment_id, item.revision),
                    )
                ),
            )
            save_case(arguments.output, case)
            return _print(
                {
                    "ok": True,
                    "case_id": case.case_id,
                    "revision": case.revision,
                    "output": str(arguments.output),
                },
                as_json=as_json,
            )
        if arguments.case_command == "validate":
            case = load_case(arguments.case)
            return _print(
                {
                    "ok": True,
                    "case_id": case.case_id,
                    "revision": case.revision,
                    "state": case.state.value,
                },
                as_json=as_json,
            )
        if arguments.case_command == "run":
            return _run(arguments, as_json=as_json)
        if arguments.case_command == "verify":
            return _verify_case(arguments, as_json=as_json)
        if arguments.case_command == "review":
            case = review_case(
                load_case(arguments.case),
                reviewer=arguments.reviewer,
                conclusion=arguments.conclusion,
                limitations=tuple(arguments.limitation or ()),
                invalidation_conditions=tuple(arguments.invalidation_condition),
                close=arguments.close,
            )
            save_case(arguments.output, case)
            return _print(
                {
                    "ok": True,
                    "case_id": case.case_id,
                    "revision": case.revision,
                    "state": case.state.value,
                    "output": str(arguments.output),
                },
                as_json=as_json,
            )
    except (CaseError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return _error(str(exc), as_json=as_json)
    return _error("unknown case command", as_json=as_json)


def handle_experiment(arguments: Namespace) -> int:
    as_json = bool(getattr(arguments, "json", False))
    try:
        if arguments.experiment_command == "validate":
            definition = load_experiment(arguments.experiment)
            return _print(
                {
                    "ok": True,
                    "experiment_id": definition.experiment_id,
                    "revision": definition.revision,
                    "definition_id": definition.definition_id,
                },
                as_json=as_json,
            )
        if arguments.experiment_command == "expand":
            definition = load_experiment(arguments.experiment)
            runs = expand_experiment(definition, execution_nonce=arguments.execution_nonce)
            payload = {
                "schema_version": 1,
                "definition_id": definition.definition_id,
                "execution_nonce": arguments.execution_nonce,
                "runs": [run.as_dict() for run in runs],
            }
            if arguments.output is not None:
                create_only_json(arguments.output, payload, make_parents=True)
            return _print(
                {
                    "ok": True,
                    "definition_id": definition.definition_id,
                    "run_count": len(runs),
                    "runs": payload["runs"],
                    "output": None if arguments.output is None else str(arguments.output),
                },
                as_json=as_json,
            )
        if arguments.experiment_command == "run":
            return _run(arguments, as_json=as_json)
    except (CaseError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return _error(str(exc), as_json=as_json)
    return _error("unknown experiment command", as_json=as_json)


def _run(arguments: Namespace, *, as_json: bool) -> int:
    case = load_case(arguments.case)
    definition = load_experiment(arguments.experiment)
    fingerprint = load_fingerprint(arguments.fingerprint)
    store = ArtifactStore(arguments.store)
    executor = (
        DryRunExecutor() if arguments.recorded is None else _recorded_executor(arguments.recorded)
    )
    results = tuple(
        execute_plan(
            case=case,
            definition=definition,
            fingerprint=fingerprint,
            store=store,
            manifest_directory=str(arguments.manifest_directory),
            executor=executor,
            execution_nonce=arguments.execution_nonce,
        )
    )
    complete = sum(
        item.manifest.terminal_state is ManifestTerminalState.COMPLETE for item in results
    )
    payload = {
        "ok": complete == len(results),
        "run_count": len(results),
        "complete_count": complete,
        "manifests": [item.manifest.manifest_id for item in results],
    }
    _print(payload, as_json=as_json)
    return 0 if payload["ok"] else 1


def _verify_case(arguments: Namespace, *, as_json: bool) -> int:
    case = load_case(arguments.case)
    definitions = [load_experiment(path) for path in arguments.experiment or ()]
    available = {(item.experiment_id, item.revision) for item in definitions}
    expected = {(item.experiment_id, item.revision) for item in case.experiments}
    issues = (
        []
        if expected.issubset(available)
        else ["one or more referenced experiments were not supplied"]
    )
    verified: list[dict[str, object]] = []
    if arguments.manifest:
        if arguments.store is None:
            raise ValueError("--store is required when manifests are supplied")
        store = ArtifactStore(arguments.store)
        for path in arguments.manifest:
            manifest = load_manifest(path)
            receipt = verify_manifest(store, manifest)
            if manifest.case_id != case.case_id:
                issues.append(f"manifest has wrong case ID: {path}")
            if receipt.status is not VerificationStatus.PASS:
                issues.append(f"manifest failed artifact verification: {path}")
            verified.append(
                {
                    "path": str(path),
                    "manifest_id": manifest.manifest_id,
                    "status": receipt.status.value,
                }
            )
    payload = {
        "ok": not issues,
        "case_id": case.case_id,
        "issues": sorted(set(issues)),
        "verified_manifests": verified,
    }
    _print(payload, as_json=as_json)
    return 0 if not issues else 1


def _recorded_executor(path: Path) -> RecordedExecutor:
    value = load_strict_json(path)
    if not isinstance(value, dict) or set(value) != {
        "observations_by_sequence",
        "completed_channels",
    }:
        raise ValueError("recorded execution fields are not exact")
    observations = value["observations_by_sequence"]
    channels = value["completed_channels"]
    if (
        not isinstance(observations, dict)
        or not isinstance(channels, list)
        or not all(isinstance(item, str) for item in channels)
    ):
        raise ValueError("recorded execution has invalid field types")
    parsed: dict[int, dict[str, object]] = {}
    for key, item in observations.items():
        if not isinstance(key, str) or not key.isdigit() or not isinstance(item, dict):
            raise ValueError("recorded observations require numeric sequence object keys")
        parsed[int(key)] = item
    return RecordedExecutor(parsed, completed_channels=channels)


def _hypothesis(value: str) -> Hypothesis:
    identifier, separator, statement = value.partition("=")
    if not separator:
        raise ValueError("hypothesis must use ID=STATEMENT")
    return Hypothesis(identifier, statement, (statement,))


def _experiment_reference(value: str) -> ExperimentReference:
    identifier, separator, revision = value.partition("@")
    if not separator:
        raise ValueError("experiment reference must use ID@REVISION")
    return ExperimentReference(identifier, int(revision))


def _print(payload: dict[str, object], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, allow_nan=False, sort_keys=True))
    else:
        for name, value in payload.items():
            if name != "ok":
                print(f"{name}: {value}")
    return 0


__all__ = ["handle_case", "handle_experiment"]
