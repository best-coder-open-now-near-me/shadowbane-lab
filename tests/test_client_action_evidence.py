import json
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.client_action import (
    ClientActionBoundary,
    ClientActionBoundaryRecord,
    ClientActionEvidenceError,
    ClientActionResult,
    ClientActionVerification,
    load_client_action_evidence,
    save_client_action_evidence,
)


def _result() -> ClientActionResult:
    return ClientActionResult(
        action_id="world-map-test-1",
        action_key="client.world_map.destination_click",
        verification=ClientActionVerification.NATIVE_VERIFIED,
        succeeded=True,
        terminal_reason="effect_observed",
        duration_ms=25,
        boundaries=(
            ClientActionBoundaryRecord(
                sequence=0,
                at_ms=0,
                boundary=ClientActionBoundary.STARTED,
                detail="world-map action started",
            ),
            ClientActionBoundaryRecord(
                sequence=1,
                at_ms=25,
                boundary=ClientActionBoundary.SUCCEEDED,
                detail="destination event matched",
                evidence={"lt": 80_000.0, "lg": 60_000.0},
            ),
        ),
    )


class ClientActionEvidenceTests(unittest.TestCase):
    def test_atomically_round_trips_a_finite_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "action.json"

            save_client_action_evidence(path, _result())

            self.assertEqual(_result(), load_client_action_evidence(path))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(1, payload["schema_version"])
            self.assertEqual("native_verified", payload["verification"])

    def test_refuses_to_overwrite_prior_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "action.json"
            save_client_action_evidence(path, _result())

            with self.assertRaisesRegex(ClientActionEvidenceError, "already exists"):
                save_client_action_evidence(path, _result())

    def test_rejects_unknown_or_missing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "action.json"
            path.write_text('{"schema_version":1}', encoding="utf-8")

            with self.assertRaisesRegex(ClientActionEvidenceError, "fields are not exact"):
                load_client_action_evidence(path)


if __name__ == "__main__":
    unittest.main()
