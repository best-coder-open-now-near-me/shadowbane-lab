import json
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.pve import (
    PvETraceEvidenceError,
    load_pve_trace_evidence,
    save_pve_trace_evidence,
    validate_pve_trace_evidence,
)


def _payload() -> dict[str, object]:
    return {
        "trace_schema_version": 1,
        "ok": True,
        "final_phase": "complete",
        "terminal_reason": "kill_limit_reached",
        "policy": "proc-assassin",
        "kills": 1,
        "steps": 1,
        "dispatched": [],
        "native_observation": {
            "process_id": 4320,
            "executable_sha256": "ab" * 32,
            "target_health_profile_id": "health",
            "player_vitals_profile_id": "vitals",
            "player_position_profile_id": "position",
            "target_position_profile_id": "target-position",
        },
        "trace": [
            {
                "decision_id": 0,
                "at_ms": 100,
                "phase": "engaged",
                "kills": 0,
                "intent": None,
                "target": {},
                "player": {},
                "combat_events": [],
                "input_accepted": None,
                "input_reason": None,
            }
        ],
    }


class PvETraceEvidenceTests(unittest.TestCase):
    def test_atomically_round_trips_a_versioned_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "pve-evidence.json"

            save_pve_trace_evidence(path, _payload())

            self.assertEqual(_payload(), load_pve_trace_evidence(path))
            self.assertEqual((), tuple(path.parent.glob(".*.tmp")))

    def test_rejects_step_count_drift(self) -> None:
        payload = _payload()
        payload["steps"] = 2

        with self.assertRaisesRegex(PvETraceEvidenceError, "trace length"):
            validate_pve_trace_evidence(payload)

    def test_rejects_non_finite_json(self) -> None:
        payload = _payload()
        payload["trace"][0]["target"] = {"current_health": float("nan")}

        with self.assertRaisesRegex(PvETraceEvidenceError, "finite JSON"):
            validate_pve_trace_evidence(payload)

    def test_validates_optional_farm_limits(self) -> None:
        payload = _payload()
        payload["farm_limits"] = {
            "maximum_kills": 3,
            "maximum_session_seconds": 600.0,
            "maximum_encounter_seconds": 120.0,
            "recovery_timeout_seconds": 30.0,
            "recovery_health_fraction": 0.75,
            "recovery_mana_fraction": 0.15,
            "recovery_stamina_fraction": 0.25,
        }

        self.assertIs(payload, validate_pve_trace_evidence(payload))
        payload["farm_limits"]["recovery_health_fraction"] = 1.1
        with self.assertRaisesRegex(PvETraceEvidenceError, "must be in"):
            validate_pve_trace_evidence(payload)

    def test_loader_rejects_an_unknown_schema(self) -> None:
        payload = _payload()
        payload["trace_schema_version"] = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(PvETraceEvidenceError, "schema"):
                load_pve_trace_evidence(path)


if __name__ == "__main__":
    unittest.main()
