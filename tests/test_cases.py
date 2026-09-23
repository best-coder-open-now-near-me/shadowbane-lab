from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from jsonschema import Draft202012Validator

from shadowbane_lab.cases import (
    CapturePolicy,
    CaseError,
    CaseState,
    ExperimentDefinition,
    ExperimentReference,
    ExperimentStep,
    ExperimentVariable,
    Hypothesis,
    OracleRule,
    OracleSeverity,
    RecordedExecutor,
    RepetitionPolicy,
    ResearchCase,
    SafetyPolicy,
    StepKind,
    VariableOrder,
    execute_plan,
    expand_experiment,
    load_case,
    load_experiment,
    save_case,
    save_experiment,
    validate_expanded_run,
)
from shadowbane_lab.cli import main
from shadowbane_lab.evidence import (
    ArtifactStore,
    ManifestTerminalState,
    VerificationStatus,
    verify_manifest,
)
from shadowbane_lab.fingerprints import (
    Applicability,
    FingerprintEnvelope,
    FingerprintSection,
    SectionName,
)


class ResearchCaseTests(unittest.TestCase):
    def _definition(self) -> ExperimentDefinition:
        return ExperimentDefinition(
            experiment_id="combat-boundary",
            revision=1,
            question_type="boundary",
            hypothesis_ids=("high", "low"),
            preconditions=(("fixture_ready", True),),
            variables=(ExperimentVariable("rank", (1, 2, 3)),),
            steps=(
                ExperimentStep(1, StepKind.RECORD_ANNOTATION, (("text", "capture"),)),
                ExperimentStep(2, StepKind.STOP, (("reason", "complete"),)),
            ),
            capture=CapturePolicy(("semantic_trace",), ("screenshot",), 100, 100),
            repetition=RepetitionPolicy(2, (11, 22), VariableOrder.CANONICAL, 0),
            oracle=(OracleRule("result", "eq", 10, 0.0, OracleSeverity.FAILURE),),
            safety=SafetyPolicy(60.0, 0, 0.0, 0.0, ("emergency_stop",)),
            outputs=("semantic_trace",),
        )

    def _case(self) -> ResearchCase:
        return ResearchCase(
            case_id="case-combat-boundary",
            revision=1,
            title="Combat boundary",
            owner="lab",
            created_at_utc="2026-08-31T12:00:00.000Z",
            target_profile="wonderbane",
            coverage_domains=("combat",),
            question="Which boundary value is used?",
            hypotheses=(
                Hypothesis("high", "The high value is used", ("result is 10",)),
                Hypothesis("low", "The low value is used", ("result is 9",)),
            ),
            state=CaseState.READY,
            required_capture_channels=("semantic_trace",),
            experiments=(ExperimentReference("combat-boundary", 1),),
        )

    def _fingerprint(self) -> FingerprintEnvelope:
        return FingerprintEnvelope(
            "2026-08-31T12:00:00.000Z",
            tuple(
                FingerprintSection(
                    name=name,
                    applicability=Applicability.NOT_APPLICABLE,
                    reason="recorded test fixture",
                )
                for name in SectionName
            ),
        )

    def test_contracts_round_trip_and_validate_against_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case_path = root / "case.json"
            experiment_path = root / "experiment.json"
            save_case(case_path, self._case())
            save_experiment(experiment_path, self._definition())
            self.assertEqual(self._case(), load_case(case_path))
            self.assertEqual(self._definition(), load_experiment(experiment_path))
            repository = Path(__file__).parents[1]
            for contract, name in (
                (self._case().as_dict(), "research-case-v1.schema.json"),
                (self._definition().as_dict(), "experiment-definition-v1.schema.json"),
            ):
                schema = json.loads((repository / "schemas" / name).read_text(encoding="utf-8"))
                Draft202012Validator(schema).validate(contract)

    def test_expansion_is_deterministic_and_complete(self) -> None:
        definition = self._definition()
        first = expand_experiment(definition, execution_nonce="review-1")
        second = expand_experiment(definition, execution_nonce="review-1")
        first_runs = tuple(first)
        self.assertEqual(first_runs, tuple(second))
        self.assertEqual(6, len(first))
        self.assertEqual(("rank", 1), first_runs[0].variables[0])
        self.assertEqual(11, first_runs[0].seed)
        self.assertEqual(definition.definition_id, first_runs[0].definition_id)
        self.assertNotEqual(
            first.plan_id,
            expand_experiment(definition, execution_nonce="review-2").plan_id,
        )

    def test_definition_identity_is_detached_from_mutable_inputs(self) -> None:
        precondition = {"client": {"ready": True}}
        variable = {"route": ["approach", "cross"]}
        binding = {"targets": ["turtle-camp"]}
        seeds = [11, 22]
        definition = replace(
            self._definition(),
            preconditions=(("fixture_ready", precondition),),
            variables=(ExperimentVariable("config", (variable,)),),
            repetition=RepetitionPolicy(2, seeds),
            steps=(
                ExperimentStep(
                    1,
                    StepKind.SEMANTIC_DECISION,
                    (("action_key", "travel"), ("binding", binding)),
                ),
                ExperimentStep(2, StepKind.STOP, (("reason", "complete"),)),
            ),
        )
        definition_id = definition.definition_id

        precondition["client"]["ready"] = False
        variable["route"].append("leave")
        binding["targets"].append("maelstrom")
        seeds[0] = 99

        self.assertEqual(definition_id, definition.definition_id)
        self.assertEqual((11, 22), definition.repetition.seeds)
        self.assertEqual(
            {"fixture_ready": {"client": {"ready": True}}},
            definition.as_dict()["preconditions"],
        )
        self.assertEqual(
            [{"route": ["approach", "cross"]}],
            definition.variables[0].as_dict()["values"],
        )
        with self.assertRaises(TypeError):
            definition.variables[0].values[0]["route"] = ()

    def test_forged_expanded_runs_are_rejected_before_execution(self) -> None:
        plan = expand_experiment(self._definition(), execution_nonce="identity-check")
        run = next(iter(plan))

        with self.assertRaisesRegex(CaseError, "experiment plan"):
            validate_expanded_run(
                plan,
                replace(run, plan_id="plan-00000000000000000000000000000000"),
            )
        with self.assertRaisesRegex(CaseError, "experiment plan"):
            validate_expanded_run(
                plan,
                replace(run, definition_id="sha256:" + "0" * 64),
            )
        with self.assertRaisesRegex(CaseError, "illegal value"):
            validate_expanded_run(plan, replace(run, variables=(("rank", 99),)))
        with self.assertRaisesRegex(CaseError, "not canonical"):
            validate_expanded_run(
                plan,
                replace(run, run_id="run-00000000000000000000000000000000"),
            )

    def test_million_run_plan_is_bounded_but_lazily_iterated(self) -> None:
        definition = replace(
            self._definition(),
            variables=(
                ExperimentVariable("a", tuple(range(1000))),
                ExperimentVariable("b", tuple(range(1000))),
            ),
            repetition=RepetitionPolicy(1, (11,)),
        )

        plan = expand_experiment(definition, execution_nonce="lazy-million")
        first = next(iter(plan))

        self.assertEqual(1_000_000, len(plan))
        self.assertEqual(("a", 0), first.variables[0])
        self.assertEqual(("b", 0), first.variables[1])

    def test_stop_condition_seals_decision_and_halts_remaining_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ArtifactStore.initialize(root / "store", store_id="case-stop-test")
            executor = RecordedExecutor(
                {1: {"emergency_stop": True, "result": 10}},
                completed_channels=("semantic_trace",),
            )

            results = tuple(
                execute_plan(
                    case=self._case(),
                    definition=self._definition(),
                    fingerprint=self._fingerprint(),
                    store=store,
                    manifest_directory=str(root / "manifests"),
                    executor=executor,
                    execution_nonce="stop-condition-1",
                )
            )

        self.assertEqual(1, len(results))
        result = results[0]
        self.assertIs(result.manifest.terminal_state, ManifestTerminalState.FAILED)
        self.assertEqual(["emergency_stop"], result.record["triggered_stop_conditions"])
        self.assertEqual(
            "stop condition triggered: emergency_stop",
            result.record["execution_error"],
        )
        self.assertEqual(1, len(result.record["stop_condition_evaluations"]))

    def test_step_algebra_rejects_undeclared_execution_authority(self) -> None:
        with self.assertRaises(ValueError):
            ExperimentStep(
                1,
                StepKind.SEMANTIC_DECISION,
                (
                    ("action_key", "attack"),
                    ("binding", {}),
                    ("screen_coordinates", [100, 100]),
                ),
            )

    def test_recorded_run_seals_complete_verifiable_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ArtifactStore.initialize(root / "store", store_id="case-test")
            executor = RecordedExecutor(
                {1: {"result": 10}, 2: {}},
                completed_channels=("semantic_trace",),
            )
            results = tuple(
                execute_plan(
                    case=self._case(),
                    definition=self._definition(),
                    fingerprint=self._fingerprint(),
                    store=store,
                    manifest_directory=str(root / "manifests"),
                    executor=executor,
                    execution_nonce="recorded-1",
                )
            )
            self.assertEqual(6, len(results))
            self.assertTrue(
                all(
                    item.manifest.terminal_state is ManifestTerminalState.COMPLETE
                    for item in results
                )
            )
            self.assertTrue(
                all(
                    verify_manifest(store, item.manifest).status is VerificationStatus.PASS
                    for item in results
                )
            )

    def test_dry_run_is_explicitly_incomplete_and_never_sends_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case_path = root / "case.json"
            definition_path = root / "definition.json"
            fingerprint_path = root / "fingerprint.json"
            store_path = root / "store"
            save_case(case_path, self._case())
            save_experiment(definition_path, self._definition())
            from shadowbane_lab.fingerprints import save_fingerprint

            save_fingerprint(fingerprint_path, self._fingerprint())
            ArtifactStore.initialize(store_path, store_id="cli-case-test")
            exit_code = main(
                [
                    "experiment",
                    "run",
                    str(case_path),
                    str(definition_path),
                    str(fingerprint_path),
                    str(store_path),
                    str(root / "manifests"),
                    "--execution-nonce",
                    "dry-run-1",
                    "--json",
                ]
            )
            self.assertEqual(1, exit_code)

    def test_loader_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "case.json"
            payload = self._case().as_dict()
            payload["shell"] = "do not run"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(CaseError):
                load_case(path)


if __name__ == "__main__":
    unittest.main()
