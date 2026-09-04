"""Command-line release gate for produced-build runtime consistency."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .codec import load_baseline, load_capture, load_suite, save_artifact
from .compare import compare_runtime_capture, promote_runtime_baseline
from .deployment import inspect_produced_deployment
from .model import GateStatus, RuntimeConsistencyError
from .runner import run_runtime_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shadowbane-runtime-consistency",
        description=(
            "Capture, promote, and gate runtime behavior for verified patcher-produced builds."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-suite", help="validate one versioned suite")
    validate.add_argument("suite", type=Path)

    inspect = commands.add_parser(
        "inspect-deployment",
        help="reverify deployment and package evidence without executing it",
    )
    inspect.add_argument("deployment_evidence", type=Path)

    capture = commands.add_parser(
        "capture",
        help="run a complete scenario matrix and publish one capture",
    )
    _capture_arguments(capture)

    promote = commands.add_parser(
        "promote",
        help="promote complete passing captures into a known-good baseline",
    )
    promote.add_argument("--baseline-id", required=True)
    promote.add_argument("--suite", required=True, type=Path)
    promote.add_argument("--output", required=True, type=Path)
    promote.add_argument("captures", nargs="+", type=Path)

    compare = commands.add_parser(
        "compare",
        help="compare a capture to an accepted runtime baseline",
    )
    compare.add_argument("baseline", type=Path)
    compare.add_argument("capture", type=Path)
    compare.add_argument("output", type=Path)

    gate = commands.add_parser(
        "gate",
        help="capture and compare one produced build as a single release gate",
    )
    _capture_arguments(gate)
    gate.add_argument("--baseline", required=True, type=Path)
    gate.add_argument("--report-output", required=True, type=Path)
    return parser


def _capture_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("deployment_evidence", type=Path)
    parser.add_argument("suite", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repetitions", type=int)
    parser.add_argument(
        "--working-directory",
        type=Path,
        help="scenario command working directory; defaults to the suite directory",
    )


def main(argv: tuple[str, ...] | list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "validate-suite":
            return _validate_suite(arguments.suite)
        if arguments.command == "inspect-deployment":
            return _inspect_deployment(arguments.deployment_evidence)
        if arguments.command == "capture":
            capture = _capture(arguments)
            _print(
                {
                    "ok": True,
                    "capture_id": capture.capture_id,
                    "output": str(arguments.output.resolve(strict=False)),
                    "build_fingerprint": capture.deployment.build_fingerprint,
                    "observation_count": len(capture.observations),
                    "passing_observations": sum(
                        observation.passed for observation in capture.observations
                    ),
                }
            )
            return 0
        if arguments.command == "promote":
            return _promote(arguments)
        if arguments.command == "compare":
            return _compare(arguments.baseline, arguments.capture, arguments.output)
        if arguments.command == "gate":
            return _gate(arguments)
        raise AssertionError(f"unhandled command {arguments.command}")
    except (OSError, RuntimeConsistencyError, ValueError) as exc:
        _print({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 2


def _validate_suite(path: Path) -> int:
    suite = load_suite(path)
    _print(
        {
            "ok": True,
            "suite_id": suite.suite_id,
            "suite_revision": suite.suite_revision,
            "environment_id": suite.environment_id,
            "minimum_repetitions": suite.minimum_repetitions,
            "scenario_count": len(suite.scenarios),
            "suite_fingerprint": suite.fingerprint,
        }
    )
    return 0


def _inspect_deployment(path: Path) -> int:
    deployment = inspect_produced_deployment(path)
    _print(
        {
            "ok": True,
            "evidence_path": str(deployment.evidence_path),
            "deployment_directory": str(deployment.deployment_directory),
            "build_fingerprint": deployment.identity.build_fingerprint,
            "identity": deployment.identity.as_dict(),
        }
    )
    return 0


def _capture(arguments: argparse.Namespace):
    output = arguments.output.resolve(strict=False)
    if output.exists():
        raise RuntimeConsistencyError(f"capture output already exists: {output}")
    suite_path = arguments.suite.resolve(strict=False)
    suite = load_suite(suite_path)
    deployment = inspect_produced_deployment(arguments.deployment_evidence)
    working_directory = (
        suite_path.parent if arguments.working_directory is None else arguments.working_directory
    )
    capture = run_runtime_suite(
        deployment,
        suite,
        repetitions=arguments.repetitions,
        working_directory=working_directory,
    )
    save_artifact(output, capture)
    return capture


def _promote(arguments: argparse.Namespace) -> int:
    output = arguments.output.resolve(strict=False)
    if output.exists():
        raise RuntimeConsistencyError(f"baseline output already exists: {output}")
    suite = load_suite(arguments.suite)
    captures = tuple(load_capture(path) for path in arguments.captures)
    baseline = promote_runtime_baseline(arguments.baseline_id, suite, captures)
    save_artifact(output, baseline)
    _print(
        {
            "ok": True,
            "baseline_id": baseline.baseline_id,
            "output": str(output),
            "source_capture_count": len(baseline.source_capture_ids),
            "accepted_build_count": len(baseline.accepted_build_fingerprints),
            "scenario_count": len(baseline.scenarios),
        }
    )
    return 0


def _compare(baseline_path: Path, capture_path: Path, output_path: Path) -> int:
    output = output_path.resolve(strict=False)
    if output.exists():
        raise RuntimeConsistencyError(f"report output already exists: {output}")
    baseline = load_baseline(baseline_path)
    capture = load_capture(capture_path)
    report = compare_runtime_capture(baseline, capture)
    save_artifact(output, report)
    _print(
        {
            "ok": report.status is not GateStatus.FAIL,
            "status": report.status.value,
            "baseline_id": report.baseline_id,
            "capture_id": report.capture_id,
            "output": str(output),
            "anomaly_count": len(report.anomalies),
            "failure_count": sum(
                anomaly.severity.value == "failure" for anomaly in report.anomalies
            ),
        }
    )
    return 1 if report.status is GateStatus.FAIL else 0


def _gate(arguments: argparse.Namespace) -> int:
    report_output = arguments.report_output.resolve(strict=False)
    if report_output.exists():
        raise RuntimeConsistencyError(f"report output already exists: {report_output}")
    capture = _capture(arguments)
    baseline = load_baseline(arguments.baseline)
    report = compare_runtime_capture(baseline, capture)
    save_artifact(report_output, report)
    _print(
        {
            "ok": report.status is not GateStatus.FAIL,
            "status": report.status.value,
            "baseline_id": report.baseline_id,
            "capture_id": capture.capture_id,
            "capture_output": str(arguments.output.resolve(strict=False)),
            "report_output": str(report_output),
            "build_fingerprint": capture.deployment.build_fingerprint,
            "anomaly_count": len(report.anomalies),
        }
    )
    return 1 if report.status is GateStatus.FAIL else 0


def _print(payload: object, *, stream=None) -> None:
    output = sys.stdout if stream is None else stream
    print(json.dumps(payload, allow_nan=False, sort_keys=True), file=output)


if __name__ == "__main__":
    raise SystemExit(main())
