from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from shadowbane_lab.cli import main
from shadowbane_lab.fingerprints import (
    Applicability,
    FingerprintCaptureInputs,
    FingerprintEnvelope,
    FingerprintError,
    FingerprintSection,
    ImpactState,
    SectionName,
    capture_fingerprint,
    compare_fingerprints,
    load_fingerprint,
    save_fingerprint,
)


class FingerprintTests(unittest.TestCase):
    def _capture(self, root: Path, *, fixture_value: int = 1) -> FingerprintEnvelope:
        fixture = root / f"fixture-{fixture_value}.json"
        fixture.write_text(json.dumps({"value": fixture_value}), encoding="utf-8")
        identity = root / "rules.json"
        identity.write_text("{}\n", encoding="utf-8")
        with patch("shadowbane_lab.fingerprints.capture.canonical_timestamp") as timestamp:
            timestamp.return_value = "2026-08-31T12:00:00.000Z"
            return capture_fingerprint(
                FingerprintCaptureInputs(
                    service_profile="wonderbane-observed",
                    service_endpoint="https://example.invalid/game",
                    environment_id="test-environment",
                    fixture_path=fixture,
                    ruleset_id="ruleset-v1",
                    policy_id="policy-v1",
                    scenario_id="scenario-v1",
                    additional_identity_files=(("execution.rules", identity),),
                    repository_directory=root,
                )
            )

    def test_complete_envelope_contains_all_sections_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            envelope = self._capture(root)
            self.assertEqual(tuple(SectionName), tuple(item.name for item in envelope.sections))
            path = root / "fingerprint.json"
            save_fingerprint(path, envelope)
            self.assertEqual(envelope, load_fingerprint(path))
            schema = json.loads(
                (
                    Path(__file__).parents[1] / "schemas" / "fingerprint-envelope-v1.schema.json"
                ).read_text(encoding="utf-8")
            )
            Draft202012Validator(schema).validate(envelope.as_dict())

    def test_fingerprint_excludes_time_and_volatile_process_identity(self) -> None:
        sections = tuple(
            FingerprintSection(
                name=name,
                applicability=Applicability.APPLICABLE
                if name is SectionName.ENVIRONMENT
                else Applicability.NOT_APPLICABLE,
                durable=(("environment_id", "test"),) if name is SectionName.ENVIRONMENT else (),
                volatile=(("process_id", 1),) if name is SectionName.ENVIRONMENT else (),
                reason=None if name is SectionName.ENVIRONMENT else "not in scope",
            )
            for name in SectionName
        )
        first = FingerprintEnvelope("2026-08-31T12:00:00.000Z", sections)
        replacement = tuple(
            FingerprintSection(
                name=item.name,
                applicability=item.applicability,
                durable=item.durable,
                volatile=(("process_id", 99),) if item.name is SectionName.ENVIRONMENT else (),
                reason=item.reason,
            )
            for item in sections
        )
        second = FingerprintEnvelope("2026-08-31T12:01:00.000Z", replacement)
        self.assertEqual(first.fingerprint_id, second.fingerprint_id)
        self.assertNotEqual(first.capture_id, second.capture_id)

    def test_fixture_change_requires_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = self._capture(root, fixture_value=1)
            candidate = self._capture(root, fixture_value=2)
            report = compare_fingerprints(reference, candidate)
            self.assertEqual(ImpactState.REVIEW_REQUIRED, report.state)
            fixture = next(
                item for item in report.differences if item.section is SectionName.FIXTURE
            )
            self.assertIn("fixture.sha256", fixture.changed_keys)

    def test_service_endpoint_rejects_credentials_and_queries(self) -> None:
        for endpoint in (
            "https://user:secret@example.invalid/game",
            "https://example.invalid/game?token=secret",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                capture_fingerprint(
                    FingerprintCaptureInputs(
                        service_profile="wonderbane-observed",
                        service_endpoint=endpoint,
                    )
                )

    def test_loader_detects_tampered_durable_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            envelope = self._capture(root)
            path = root / "fingerprint.json"
            save_fingerprint(path, envelope)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["sections"][3]["durable"]["environment_id"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(FingerprintError):
                load_fingerprint(path)

    def test_cli_captures_verifies_and_diffs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture.json"
            fixture.write_text("{}\n", encoding="utf-8")
            first = root / "first.json"
            second = root / "second.json"
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    (
                        "fingerprint",
                        "capture",
                        str(first),
                        "--fixture",
                        str(fixture),
                        "--environment-id",
                        "test",
                        "--ruleset-id",
                        "rules-v1",
                        "--repository",
                        str(root),
                        "--json",
                    )
                )
            self.assertEqual(0, result)
            self.assertTrue(json.loads(output.getvalue())["fingerprint_id"].startswith("sha256:"))
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(("fingerprint", "verify", str(first), "--json"))
            self.assertEqual(0, result)
            self.assertTrue(json.loads(output.getvalue())["ok"])
            second.write_bytes(first.read_bytes())
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(("fingerprint", "diff", str(first), str(second), "--json"))
            self.assertEqual(0, result)
            self.assertEqual("unaffected", json.loads(output.getvalue())["state"])


if __name__ == "__main__":
    unittest.main()
