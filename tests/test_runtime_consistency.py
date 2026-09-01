import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from shadowbane_lab.runtime_consistency import (
    CounterPolicy,
    DeploymentIdentity,
    DeploymentSlotIdentity,
    GateStatus,
    MetricDirection,
    MetricPolicy,
    ProducedDeployment,
    ProducedRuntimeSlot,
    RuntimeCapture,
    RuntimeConsistencyError,
    RuntimeObservation,
    RuntimeScenario,
    RuntimeSuite,
    Severity,
    SlotScope,
    compare_runtime_capture,
    inspect_produced_deployment,
    load_baseline,
    load_capture,
    load_suite,
    promote_runtime_baseline,
    run_runtime_suite,
    save_artifact,
)
from shadowbane_lab.runtime_consistency.manager_health_probe import (
    build_manager_health_result,
)
from shadowbane_lab.runtime_consistency.model import canonical_sha256

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


def _suite(*, minimum_repetitions: int = 3) -> RuntimeSuite:
    scenario = RuntimeScenario(
        scenario_id="startup-health",
        command=("runtime-probe",),
        timeout_seconds=30.0,
        slot_scope=SlotScope.ALL,
        metric_policies=(
            (
                "frame_time_ms",
                MetricPolicy(
                    direction=MetricDirection.INCREASE,
                    absolute_tolerance=2.0,
                    relative_tolerance=0.1,
                ),
            ),
            (
                "pipeline.wall_duration_ms",
                MetricPolicy(
                    direction=MetricDirection.INCREASE,
                    absolute_tolerance=20.0,
                    relative_tolerance=0.2,
                ),
            ),
        ),
        counter_policies=(("event_drops", CounterPolicy(maximum_value=0)),),
    )
    return RuntimeSuite(
        suite_id="wonderbane-runtime-smoke",
        suite_revision="2026-08-31.1",
        environment_id="wonderbane-vm-1920x955",
        minimum_repetitions=minimum_repetitions,
        scenarios=(scenario,),
    )


def _deployment() -> DeploymentIdentity:
    return DeploymentIdentity(
        deployment_id="deployment-1",
        deployment_kind="initial",
        baseline_tree_sha256=SHA_A,
        repository_revision="abc123",
        patch_id="patch-1",
        patch_manifest_sha256=SHA_B,
        resolution="1920x955",
        slots=(
            DeploymentSlotIdentity("client-01", SHA_C, SHA_D, SHA_E),
            DeploymentSlotIdentity("client-02", SHA_C, SHA_D, SHA_E),
        ),
    )


def _capture(
    suite: RuntimeSuite,
    *,
    capture_id: str = "capture-1",
    semantic: object = None,
    frame_time_ms: float = 16.0,
    wall_duration_ms: float = 100.0,
    event_drops: int = 0,
) -> RuntimeCapture:
    semantic_value = {"extension": "ready", "worker": "healthy"} if semantic is None else semantic
    observations = tuple(
        RuntimeObservation(
            scenario_id="startup-health",
            client_id=client_id,
            repetition=repetition,
            passed=True,
            terminal_reason="completed",
            command_exit_code=0,
            semantic=semantic_value,
            metrics=(
                ("frame_time_ms", frame_time_ms),
                ("pipeline.wall_duration_ms", wall_duration_ms),
            ),
            counters=(("event_drops", event_drops),),
        )
        for client_id in ("client-01", "client-02")
        for repetition in range(suite.minimum_repetitions)
    )
    return RuntimeCapture(
        capture_id=capture_id,
        captured_at_utc="2026-08-31T06:00:00.000Z",
        suite_id=suite.suite_id,
        suite_revision=suite.suite_revision,
        suite_fingerprint=suite.fingerprint,
        environment_id=suite.environment_id,
        requested_repetitions=suite.minimum_repetitions,
        deployment=_deployment(),
        host=(("os_system", "Windows"),),
        observations=observations,
    )


class RuntimeConsistencyTests(unittest.TestCase):
    def test_manager_health_probe_normalizes_volatile_status(self) -> None:
        status = {
            "ok": True,
            "slots": [
                {
                    "client_id": "client-01",
                    "state": "attached",
                    "dispatch_enabled": True,
                    "failure_detail": None,
                    "binding": {"process_id": 1001, "instance_id": "volatile"},
                    "worker": {
                        "state": "healthy",
                        "dispatch_allowed": True,
                        "active_worker_count": 1,
                        "heartbeat_age_seconds": 0.25,
                        "issues": [],
                    },
                    "extension": {
                        "state": "initialized",
                        "ready": True,
                        "abi_version": 1,
                        "extension_version": "volatile-build-version",
                    },
                    "operation": {"queued_count": 0, "active": None},
                    "candidates": [],
                    "rejected_windows": [],
                }
            ],
        }
        process_metrics = {
            "process_handle_count": 120.0,
            "process_private_bytes": 256_000_000.0,
            "process_working_set_bytes": 192_000_000.0,
        }
        event_channel = SimpleNamespace(
            header=SimpleNamespace(
                dropped_event_count=0,
                pending_count=0,
                producer_error=0,
                capability_flags=3,
            )
        )

        with patch.dict(os.environ, {"SHADOWBANE_RUNTIME_SCENARIO_ID": "manager-health"}):
            result = build_manager_health_result(
                status,
                "client-01",
                latency_ms=4.0,
                process_metrics=process_metrics,
                event_channel=event_channel,
            )

        self.assertTrue(result.passed)
        self.assertEqual("healthy", result.terminal_reason)
        self.assertNotIn("volatile", json.dumps(result.semantic))
        self.assertEqual(3, result.semantic["event_channel"]["capability_flags"])
        self.assertEqual(192_000_000.0, dict(result.metrics)["process_working_set_bytes"])
        self.assertEqual(0.25, dict(result.metrics)["worker_heartbeat_age_seconds"])
        self.assertTrue(all(value == 0 for _, value in result.counters))

    def test_manager_health_probe_fails_closed_on_degraded_worker(self) -> None:
        status = {
            "ok": True,
            "slots": [
                {
                    "client_id": "client-01",
                    "state": "attached",
                    "dispatch_enabled": False,
                    "failure_detail": None,
                    "binding": {"process_id": 1001},
                    "worker": {
                        "state": "degraded",
                        "dispatch_allowed": False,
                        "active_worker_count": 1,
                        "heartbeat_age_seconds": 4.0,
                        "issues": [{"code": "expired"}],
                    },
                    "extension": {
                        "state": "initialized",
                        "ready": True,
                        "abi_version": 1,
                    },
                    "operation": {"queued_count": 0, "active": None},
                    "candidates": [],
                    "rejected_windows": [],
                }
            ],
        }

        result = build_manager_health_result(status, "client-01", latency_ms=4.0)

        self.assertFalse(result.passed)
        self.assertEqual("manager_health_invariant_failed", result.terminal_reason)
        self.assertEqual(1, dict(result.counters)["worker_issue_count"])

    def test_promotes_stable_capture_and_accepts_consistent_candidate(self) -> None:
        suite = _suite()
        baseline = promote_runtime_baseline(
            "baseline-1",
            suite,
            (_capture(suite),),
            promoted_at=datetime(2026, 8, 31, tzinfo=UTC),
        )

        report = compare_runtime_capture(
            baseline,
            _capture(
                suite,
                capture_id="candidate-1",
                frame_time_ms=17.0,
                wall_duration_ms=110.0,
            ),
            compared_at=datetime(2026, 8, 31, 1, tzinfo=UTC),
        )

        self.assertEqual(GateStatus.PASS, report.status)
        self.assertEqual((), report.anomalies)

    def test_semantic_drift_fails_the_gate(self) -> None:
        suite = _suite()
        baseline = promote_runtime_baseline("baseline-1", suite, (_capture(suite),))

        report = compare_runtime_capture(
            baseline,
            _capture(suite, capture_id="candidate-1", semantic={"extension": "missing"}),
        )

        self.assertEqual(GateStatus.FAIL, report.status)
        self.assertIn("semantic", {item.category for item in report.anomalies})

    def test_metric_and_counter_regressions_fail_the_gate(self) -> None:
        suite = _suite()
        baseline = promote_runtime_baseline("baseline-1", suite, (_capture(suite),))

        report = compare_runtime_capture(
            baseline,
            _capture(
                suite,
                capture_id="candidate-1",
                frame_time_ms=40.0,
                wall_duration_ms=200.0,
                event_drops=1,
            ),
        )

        self.assertEqual(GateStatus.FAIL, report.status)
        categories = {item.category for item in report.anomalies}
        self.assertIn("metric", categories)
        self.assertIn("counter", categories)

    def test_warning_policy_yields_warning_gate(self) -> None:
        suite = _suite()
        scenario = suite.scenarios[0]
        policies = tuple(
            (
                name,
                replace(policy, severity=Severity.WARNING) if name == "frame_time_ms" else policy,
            )
            for name, policy in scenario.metric_policies
        )
        suite = replace(suite, scenarios=(replace(scenario, metric_policies=policies),))
        baseline = promote_runtime_baseline("baseline-1", suite, (_capture(suite),))

        report = compare_runtime_capture(
            baseline,
            _capture(suite, capture_id="candidate-1", frame_time_ms=40.0),
        )

        self.assertEqual(GateStatus.WARN, report.status)

    def test_promotion_rejects_incomplete_capture(self) -> None:
        suite = _suite()
        capture = _capture(suite)
        incomplete = replace(capture, observations=capture.observations[:-1])

        with self.assertRaisesRegex(RuntimeConsistencyError, "exact scenario matrix"):
            promote_runtime_baseline("baseline-1", suite, (incomplete,))

    def test_suite_capture_and_baseline_round_trip(self) -> None:
        suite = _suite()
        capture = _capture(suite)
        baseline = promote_runtime_baseline("baseline-1", suite, (capture,))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite_path = root / "suite.json"
            capture_path = root / "capture.json"
            baseline_path = root / "baseline.json"
            save_artifact(suite_path, suite)
            save_artifact(capture_path, capture)
            save_artifact(baseline_path, baseline)

            self.assertEqual(suite, load_suite(suite_path))
            self.assertEqual(capture, load_capture(capture_path))
            self.assertEqual(baseline, load_baseline(baseline_path))

    def test_runner_injects_context_and_loads_strict_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "client-01"
            runtime.mkdir()
            identity = replace(_deployment(), slots=(_deployment().slots[0],))
            produced = ProducedDeployment(
                evidence_path=root / "runtime-deployment.json",
                deployment_directory=root,
                identity=identity,
                slots=(ProducedRuntimeSlot("client-01", runtime),),
            )
            source = (
                "import json, os; from pathlib import Path; "
                "Path(os.environ['SHADOWBANE_RUNTIME_RESULT_PATH']).write_text("
                "json.dumps({'schema_version':1,'scenario_id':"
                "os.environ['SHADOWBANE_RUNTIME_SCENARIO_ID'],'passed':True,"
                "'terminal_reason':'completed','semantic':{'ready':True},"
                "'metrics':{'probe_ms':2.0},'counters':{'event_drops':0}}),"
                "encoding='utf-8')"
            )
            scenario = RuntimeScenario(
                scenario_id="probe",
                command=(sys.executable, "-c", source),
                timeout_seconds=10.0,
                slot_scope=SlotScope.FIRST,
                metric_policies=(
                    ("pipeline.wall_duration_ms", MetricPolicy()),
                    ("probe_ms", MetricPolicy()),
                ),
                counter_policies=(("event_drops", CounterPolicy(maximum_value=0)),),
            )
            suite = RuntimeSuite(
                suite_id="runner-test",
                suite_revision="1",
                environment_id="test",
                minimum_repetitions=1,
                scenarios=(scenario,),
            )

            capture = run_runtime_suite(
                produced,
                suite,
                working_directory=root,
                captured_at=datetime(2026, 8, 31, tzinfo=UTC),
            )

        self.assertEqual(1, len(capture.observations))
        observation = capture.observations[0]
        self.assertTrue(observation.passed)
        self.assertEqual({"ready": True}, observation.semantic)
        self.assertEqual({"event_drops": 0}, dict(observation.counters))
        self.assertIn("pipeline.wall_duration_ms", dict(observation.metrics))

    def test_deployment_inspection_reverifies_every_slot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            deployment = Path(temporary) / "deployment-1"
            runtime = deployment / "client-01"
            inputs = deployment / ".deployment-inputs"
            runtime.mkdir(parents=True)
            resolved_runtime = runtime.resolve(strict=True)
            inputs.mkdir()
            evidence_path = deployment / "runtime-deployment.json"
            manifest_path = inputs / "bootstrap-manifest.json"
            extension_path = inputs / "extension.dll"
            manifest_path.write_text("{}", encoding="utf-8")
            extension_path.write_bytes(b"extension")
            manifest = SimpleNamespace(
                patch_id="patch-1",
                extension=SimpleNamespace(file_name="extension.dll", sha256=SHA_E),
                as_dict=lambda: {"patch_id": "patch-1", "extension": SHA_E},
            )
            manifest_hash = canonical_sha256(manifest.as_dict())
            package = SimpleNamespace(
                working_tree_sha256=SHA_C,
                result_executable_sha256=SHA_D,
                extension_sha256=SHA_E,
                baseline_tree_sha256=SHA_A,
                repository_revision="abc123",
                patch_id="patch-1",
                manifest_sha256=manifest_hash,
            )
            evidence = {
                "schema_version": 2,
                "deployment_id": "deployment-1",
                "deployment_kind": "initial",
                "created_at_utc": "2026-08-31T06:00:00.000Z",
                "deployment_directory": str(deployment),
                "manager_manifest_path": str(deployment / "manager.json"),
                "baseline_directory": str(deployment / "baseline"),
                "baseline_tree_sha256": SHA_A,
                "repository_revision": "abc123",
                "patch_id": "patch-1",
                "patch_manifest_sha256": manifest_hash,
                "resolution": "1920x955",
                "inputs": {
                    "patch_manifest": ".deployment-inputs/bootstrap-manifest.json",
                    "extension_artifact": ".deployment-inputs/extension.dll",
                },
                "slot_count": 1,
                "slots": [
                    {
                        "client_id": "client-01",
                        "runtime_directory": str(runtime),
                        "package_working_tree_sha256": SHA_C,
                        "executable_sha256": SHA_D,
                        "extension_sha256": SHA_E,
                    }
                ],
            }
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            with (
                patch(
                    "shadowbane_lab.runtime_consistency.deployment.load_patch_manifest",
                    return_value=manifest,
                ),
                patch(
                    "shadowbane_lab.runtime_consistency.deployment.verify_patched_client_copy",
                    return_value=package,
                ) as verify,
                patch(
                    "shadowbane_lab.runtime_consistency.deployment._file_sha256",
                    return_value=SHA_E,
                ),
            ):
                inspected = inspect_produced_deployment(evidence_path)

        self.assertEqual("deployment-1", inspected.identity.deployment_id)
        self.assertEqual(("client-01",), tuple(item.client_id for item in inspected.slots))
        verify.assert_called_once_with(resolved_runtime)


if __name__ == "__main__":
    unittest.main()
