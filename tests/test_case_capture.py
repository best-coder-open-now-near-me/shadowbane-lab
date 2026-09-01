from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from shadowbane_lab.cases import (
    CapturePolicy,
    CaptureRecord,
    CaptureRecordKind,
    CaseState,
    ExecutionControl,
    ExperimentDefinition,
    ExperimentReference,
    ExperimentStep,
    ExperimentVariable,
    Hypothesis,
    RepetitionPolicy,
    ResearchCase,
    SafetyPolicy,
    StepKind,
    StepOutcome,
    align_capture_records,
    execute_plan,
    expand_experiment,
    load_capture_records,
    producer_health,
    save_capture_records,
)
from shadowbane_lab.evidence import ArtifactStore, ManifestTerminalState, verify_manifest
from shadowbane_lab.fingerprints import (
    Applicability,
    FingerprintEnvelope,
    FingerprintSection,
    SectionName,
)


def _record(
    *,
    clock_domain_id: str,
    monotonic_ns: int,
    captured_at_utc: str,
    producer_sequence: int,
    producer_id: str = "producer",
) -> CaptureRecord:
    return CaptureRecord(
        run_id="run-capture",
        channel_id="process-metrics",
        producer_id=producer_id,
        producer_version="1",
        clock_domain_id=clock_domain_id,
        monotonic_ns=monotonic_ns,
        utc_uncertainty_ns=1_000_000,
        captured_at_utc=captured_at_utc,
        producer_sequence=producer_sequence,
        kind=CaptureRecordKind.OBSERVATION,
        payload=(("value", producer_sequence),),
    )


class CaptureAlignmentTests(unittest.TestCase):
    def test_capture_round_trip_preserves_clock_identity(self) -> None:
        records = (
            _record(
                clock_domain_id="host-boot-a",
                monotonic_ns=100,
                captured_at_utc="2026-08-31T12:00:00.000Z",
                producer_sequence=1,
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "capture.json"
            save_capture_records(path, records)
            self.assertEqual(records, load_capture_records(path))

    def test_cross_domain_alignment_never_claims_a_total_order(self) -> None:
        records = (
            _record(
                clock_domain_id="host-boot-a",
                monotonic_ns=100,
                captured_at_utc="2026-08-31T12:00:00.000Z",
                producer_sequence=1,
                producer_id="a",
            ),
            _record(
                clock_domain_id="host-boot-b",
                monotonic_ns=9_000_000,
                captured_at_utc="2026-08-31T12:00:00.000Z",
                producer_sequence=1,
                producer_id="b",
            ),
        )
        trace = align_capture_records(records)
        aligned = tuple(dict(item) for item in trace.records)
        self.assertTrue(all(item["global_order"] == "not_asserted" for item in aligned))
        self.assertTrue(all(item["clock_domain_offset_ns"] == 0 for item in aligned))
        self.assertIn("cross-clock-order-not-total", trace.findings)

    def test_producer_restarts_are_accounted_per_clock_domain(self) -> None:
        records = (
            _record(
                clock_domain_id="host-boot-a",
                monotonic_ns=100,
                captured_at_utc="2026-08-31T12:00:00.000Z",
                producer_sequence=1,
            ),
            _record(
                clock_domain_id="host-boot-b",
                monotonic_ns=10,
                captured_at_utc="2026-08-31T12:01:00.000Z",
                producer_sequence=1,
            ),
        )
        health = producer_health(records)
        self.assertEqual(2, len(health))
        self.assertTrue(all(item.sequence_gaps == 0 for item in health))


class _RecordingExecutor:
    executor_id = "test.recording"
    executor_version = "1"

    def __init__(self, *, fail: bool = False) -> None:
        self.sequences: list[int] = []
        self.fail = fail

    def execute(
        self,
        step: ExperimentStep,
        *,
        run: Any,
        context: Any,
        control: ExecutionControl,
    ) -> StepOutcome:
        del run, context
        control.check()
        self.sequences.append(step.sequence)
        if self.fail:
            raise RuntimeError("fixture failure")
        return StepOutcome(
            passed=True,
            completed_channels=("semantic-trace",),
            stop=step.kind is StepKind.STOP,
        )


class HardenedRunnerTests(unittest.TestCase):
    def _definition(self) -> ExperimentDefinition:
        return ExperimentDefinition(
            experiment_id="bounded-repeat",
            revision=1,
            question_type="control-flow",
            hypothesis_ids=("a", "b"),
            preconditions=(),
            variables=(),
            steps=(
                ExperimentStep(1, StepKind.RECORD_ANNOTATION, (("text", "a"),)),
                ExperimentStep(2, StepKind.RECORD_ANNOTATION, (("text", "b"),)),
                ExperimentStep(3, StepKind.RECORD_ANNOTATION, (("text", "outside"),)),
                ExperimentStep(
                    4,
                    StepKind.REPEAT,
                    (
                        ("count", 2),
                        ("end_sequence", 2),
                        ("start_sequence", 1),
                    ),
                ),
                ExperimentStep(5, StepKind.STOP, (("reason", "done"),)),
            ),
            capture=CapturePolicy(("semantic-trace",)),
            repetition=RepetitionPolicy(1, (1,)),
            oracle=(),
            safety=SafetyPolicy(60.0, 0, 0.0, 0.0, ("cancel",)),
            outputs=("semantic-trace",),
        )

    def _case(self) -> ResearchCase:
        return ResearchCase(
            case_id="case-bounded-repeat",
            revision=1,
            title="Bounded repeat",
            owner="tests",
            created_at_utc="2026-08-31T12:00:00.000Z",
            target_profile="fixture",
            coverage_domains=("runner",),
            question="Is the repeat range exact?",
            hypotheses=(
                Hypothesis("a", "It is exact", ("outside step runs once",)),
                Hypothesis("b", "It leaks", ("outside step repeats",)),
            ),
            state=CaseState.READY,
            required_capture_channels=("semantic-trace",),
            experiments=(ExperimentReference("bounded-repeat", 1),),
        )

    def _fingerprint(self) -> FingerprintEnvelope:
        return FingerprintEnvelope(
            "2026-08-31T12:00:00.000Z",
            tuple(
                FingerprintSection(
                    name=name,
                    applicability=Applicability.NOT_APPLICABLE,
                    reason="test fixture",
                )
                for name in SectionName
            ),
        )

    def _execute(
        self,
        executor: _RecordingExecutor,
        *,
        cancelled: bool = False,
    ):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        store = ArtifactStore.initialize(root / "store", store_id="runner-hardening")
        result = execute_plan(
            case=self._case(),
            definition=self._definition(),
            fingerprint=self._fingerprint(),
            store=store,
            manifest_directory=str(root / "manifests"),
            executor=executor,
            execution_nonce="fixture",
            cancellation_requested=(lambda: cancelled),
        )[0]
        return result, store

    def test_repeat_executes_only_the_declared_range(self) -> None:
        executor = _RecordingExecutor()
        result, _ = self._execute(executor)
        self.assertEqual([1, 2, 3, 1, 2, 1, 2, 5], executor.sequences)
        self.assertIs(result.manifest.terminal_state, ManifestTerminalState.COMPLETE)

    def test_executor_failure_still_seals_verifiable_failed_evidence(self) -> None:
        result, store = self._execute(_RecordingExecutor(fail=True))
        self.assertIs(result.manifest.terminal_state, ManifestTerminalState.FAILED)
        self.assertIn("RuntimeError: fixture failure", result.record["execution_error"])
        self.assertEqual("pass", verify_manifest(store, result.manifest).status.value)

    def test_cancellation_still_seals_verifiable_failed_evidence(self) -> None:
        result, store = self._execute(_RecordingExecutor(), cancelled=True)
        self.assertIs(result.manifest.terminal_state, ManifestTerminalState.FAILED)
        self.assertIn("cancelled", result.record["execution_error"])
        self.assertEqual("pass", verify_manifest(store, result.manifest).status.value)

    def test_expansion_rejects_oversized_product_before_materialization(self) -> None:
        definition = replace(
            self._definition(),
            variables=(
                ExperimentVariable("a", tuple(range(1001))),
                ExperimentVariable("b", tuple(range(1001))),
            ),
        )
        with self.assertRaisesRegex(ValueError, "one million"):
            expand_experiment(definition, execution_nonce="too-large")


if __name__ == "__main__":
    unittest.main()
