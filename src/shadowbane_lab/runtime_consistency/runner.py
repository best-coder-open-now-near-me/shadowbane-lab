"""Execute a versioned scenario matrix against one verified produced deployment."""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .codec import load_scenario_result
from .deployment import ProducedDeployment, ProducedRuntimeSlot
from .model import (
    RuntimeCapture,
    RuntimeObservation,
    RuntimeScenario,
    RuntimeSuite,
    SlotScope,
)

_RESULT_ENVIRONMENT_VARIABLE = "SHADOWBANE_RUNTIME_RESULT_PATH"


def run_runtime_suite(
    deployment: ProducedDeployment,
    suite: RuntimeSuite,
    *,
    repetitions: int | None = None,
    working_directory: str | Path | None = None,
    captured_at: datetime | None = None,
) -> RuntimeCapture:
    """Run every declared scenario without stopping at the first anomaly."""

    if not isinstance(deployment, ProducedDeployment):
        raise ValueError("deployment must be a ProducedDeployment")
    if not isinstance(suite, RuntimeSuite):
        raise ValueError("suite must be a RuntimeSuite")
    count = suite.minimum_repetitions if repetitions is None else repetitions
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10_000:
        raise ValueError("repetitions must be in [1, 10000]")
    root = (
        Path.cwd().resolve(strict=False)
        if working_directory is None
        else Path(working_directory).resolve(strict=False)
    )
    if not root.is_dir():
        raise ValueError(f"runtime scenario working directory does not exist: {root}")

    observations: list[RuntimeObservation] = []
    with tempfile.TemporaryDirectory(prefix="shadowbane-runtime-consistency-") as temporary:
        temporary_root = Path(temporary)
        for scenario in suite.scenarios:
            slots = (
                deployment.slots[:1] if scenario.slot_scope is SlotScope.FIRST else deployment.slots
            )
            for slot in slots:
                for repetition in range(count):
                    observations.append(
                        _run_observation(
                            deployment,
                            suite,
                            scenario,
                            slot,
                            repetition,
                            root,
                            temporary_root,
                        )
                    )

    timestamp = datetime.now(UTC) if captured_at is None else captured_at
    if timestamp.tzinfo is None:
        raise ValueError("captured_at must include a timezone")
    timestamp_text = _timestamp(timestamp)
    return RuntimeCapture(
        capture_id=(
            f"capture-{timestamp.astimezone(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-"
            f"{uuid.uuid4().hex[:8]}"
        ),
        captured_at_utc=timestamp_text,
        suite_id=suite.suite_id,
        suite_revision=suite.suite_revision,
        suite_fingerprint=suite.fingerprint,
        environment_id=suite.environment_id,
        requested_repetitions=count,
        deployment=deployment.identity,
        host=tuple(
            sorted(
                {
                    "machine": platform.machine() or "unknown",
                    "os_release": platform.release() or "unknown",
                    "os_system": platform.system() or "unknown",
                    "os_version": platform.version() or "unknown",
                    "python_implementation": platform.python_implementation(),
                    "python_version": platform.python_version(),
                }.items()
            )
        ),
        observations=tuple(observations),
    )


def _run_observation(
    deployment: ProducedDeployment,
    suite: RuntimeSuite,
    scenario: RuntimeScenario,
    slot: ProducedRuntimeSlot,
    repetition: int,
    working_directory: Path,
    temporary_root: Path,
) -> RuntimeObservation:
    result_path = temporary_root / (
        f"{scenario.scenario_id}-{slot.client_id}-{repetition}-{uuid.uuid4().hex}.json"
    )
    environment = os.environ.copy()
    environment.update(
        {
            "SHADOWBANE_RUNTIME_DEPLOYMENT_EVIDENCE": str(deployment.evidence_path),
            "SHADOWBANE_RUNTIME_DEPLOYMENT_DIRECTORY": str(deployment.deployment_directory),
            "SHADOWBANE_RUNTIME_BUILD_FINGERPRINT": (deployment.identity.build_fingerprint),
            "SHADOWBANE_RUNTIME_CLIENT_ID": slot.client_id,
            "SHADOWBANE_RUNTIME_CLIENT_DIRECTORY": str(slot.runtime_directory),
            "SHADOWBANE_RUNTIME_ENVIRONMENT_ID": suite.environment_id,
            "SHADOWBANE_RUNTIME_SCENARIO_ID": scenario.scenario_id,
            "SHADOWBANE_RUNTIME_REPETITION": str(repetition),
            _RESULT_ENVIRONMENT_VARIABLE: str(result_path),
        }
    )
    started = time.perf_counter_ns()
    exit_code: int | None = None
    terminal_reason: str
    result = None
    with tempfile.TemporaryFile() as output:
        try:
            completed = subprocess.run(
                scenario.command,
                cwd=working_directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=scenario.timeout_seconds,
                check=False,
                shell=False,
            )
            exit_code = completed.returncode
            terminal_reason = f"command_exit_{exit_code}"
        except subprocess.TimeoutExpired:
            terminal_reason = "command_timeout"
        except OSError as exc:
            terminal_reason = f"command_start_failed_{type(exc).__name__}"
    duration_ms = max(0.0, (time.perf_counter_ns() - started) / 1_000_000.0)

    try:
        result = load_scenario_result(result_path)
        if result.scenario_id != scenario.scenario_id:
            terminal_reason = "result_scenario_mismatch"
            result = None
    except RuntimeError as exc:
        if exit_code == 0:
            terminal_reason = f"result_invalid_{type(exc).__name__}"
    finally:
        try:
            result_path.unlink(missing_ok=True)
        except OSError:
            pass

    if result is None:
        return RuntimeObservation(
            scenario_id=scenario.scenario_id,
            client_id=slot.client_id,
            repetition=repetition,
            passed=False,
            terminal_reason=terminal_reason,
            command_exit_code=exit_code,
            semantic=None,
            metrics=(("pipeline.wall_duration_ms", duration_ms),),
            counters=(),
        )

    result_metrics = dict(result.metrics)
    if "pipeline.wall_duration_ms" in result_metrics:
        return RuntimeObservation(
            scenario_id=scenario.scenario_id,
            client_id=slot.client_id,
            repetition=repetition,
            passed=False,
            terminal_reason="reserved_pipeline_metric_reported",
            command_exit_code=exit_code,
            semantic=result.semantic,
            metrics=(("pipeline.wall_duration_ms", duration_ms),),
            counters=result.counters,
        )
    result_metrics["pipeline.wall_duration_ms"] = duration_ms
    passed = exit_code == 0 and result.passed
    if exit_code == 0:
        terminal_reason = result.terminal_reason
    return RuntimeObservation(
        scenario_id=scenario.scenario_id,
        client_id=slot.client_id,
        repetition=repetition,
        passed=passed,
        terminal_reason=terminal_reason,
        command_exit_code=exit_code,
        semantic=result.semantic,
        metrics=tuple(sorted(result_metrics.items())),
        counters=result.counters,
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = ["run_runtime_suite"]
