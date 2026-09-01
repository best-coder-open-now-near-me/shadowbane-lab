import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from test_runtime_consistency import _capture, _deployment, _suite

from shadowbane_lab.runtime_consistency import (
    ProducedDeployment,
    ProducedRuntimeSlot,
    RuntimeSuite,
    load_capture,
    load_report,
    promote_runtime_baseline,
    save_artifact,
)
from shadowbane_lab.runtime_consistency.__main__ import main


class RuntimeConsistencyCliTests(unittest.TestCase):
    def test_validate_suite_emits_machine_readable_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "suite.json"
            suite = _suite()
            save_artifact(path, suite)
            output = io.StringIO()

            with redirect_stdout(output):
                result = main(("validate-suite", str(path)))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["ok"])
        self.assertEqual(suite.fingerprint, payload["suite_fingerprint"])

    def test_compare_returns_gate_failure_and_persists_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = _suite()
            baseline = promote_runtime_baseline("baseline-1", suite, (_capture(suite),))
            candidate = _capture(
                suite,
                capture_id="candidate-1",
                semantic={"extension": "missing"},
            )
            baseline_path = root / "baseline.json"
            candidate_path = root / "candidate.json"
            report_path = root / "report.json"
            save_artifact(baseline_path, baseline)
            save_artifact(candidate_path, candidate)
            output = io.StringIO()

            with redirect_stdout(output):
                result = main(
                    (
                        "compare",
                        str(baseline_path),
                        str(candidate_path),
                        str(report_path),
                    )
                )

            report = load_report(report_path)

        self.assertEqual(1, result)
        self.assertEqual("fail", report.status.value)
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_gate_runs_capture_and_comparison_as_one_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "client-01"
            runtime.mkdir()
            source = (
                "import json, os; from pathlib import Path; "
                "Path(os.environ['SHADOWBANE_RUNTIME_RESULT_PATH']).write_text("
                "json.dumps({'schema_version':1,'scenario_id':'startup-health',"
                "'passed':True,'terminal_reason':'completed',"
                "'semantic':{'extension':'ready','worker':'healthy'},"
                "'metrics':{'frame_time_ms':16.0},"
                "'counters':{'event_drops':0}}),encoding='utf-8')"
            )
            original_suite = _suite()
            scenario = replace(
                original_suite.scenarios[0],
                command=(sys.executable, "-c", source),
            )
            suite = RuntimeSuite(
                suite_id=original_suite.suite_id,
                suite_revision=original_suite.suite_revision,
                environment_id=original_suite.environment_id,
                minimum_repetitions=original_suite.minimum_repetitions,
                scenarios=(scenario,),
            )
            known_good = _capture(suite)
            baseline = promote_runtime_baseline("baseline-1", suite, (known_good,))
            suite_path = root / "suite.json"
            baseline_path = root / "baseline.json"
            capture_path = root / "candidate.json"
            report_path = root / "report.json"
            save_artifact(suite_path, suite)
            save_artifact(baseline_path, baseline)
            identity = replace(_deployment(), slots=(_deployment().slots[0],))
            produced = ProducedDeployment(
                evidence_path=root / "runtime-deployment.json",
                deployment_directory=root,
                identity=identity,
                slots=(ProducedRuntimeSlot("client-01", runtime),),
            )
            output = io.StringIO()

            with (
                patch(
                    "shadowbane_lab.runtime_consistency.__main__.inspect_produced_deployment",
                    return_value=produced,
                ),
                redirect_stdout(output),
            ):
                result = main(
                    (
                        "gate",
                        str(produced.evidence_path),
                        str(suite_path),
                        str(capture_path),
                        "--baseline",
                        str(baseline_path),
                        "--report-output",
                        str(report_path),
                        "--working-directory",
                        str(root),
                    )
                )

            capture = load_capture(capture_path)
            report = load_report(report_path)

        self.assertEqual(0, result)
        self.assertEqual(3, len(capture.observations))
        self.assertEqual("pass", report.status.value)
        self.assertTrue(json.loads(output.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
