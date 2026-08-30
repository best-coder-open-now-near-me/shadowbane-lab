import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path

from shadowbane_lab.cli import main
from shadowbane_lab.pve import (
    PvECombatCalibrationError,
    compile_pve_combat_calibration,
    load_pve_combat_calibration,
    save_pve_combat_calibration,
    save_pve_trace_evidence,
)


def _step(
    at_ms: int,
    *,
    intent: str | None = None,
    mana: float = 220.0,
    player_health: float = 500.0,
    target_health: float = 180.0,
    target_present: bool = True,
    events: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "decision_id": at_ms // 100,
        "at_ms": at_ms,
        "phase": "engaged",
        "kills": 0,
        "intent": intent,
        "target": {
            "present": target_present,
            "token": "mob-a" if target_present else None,
            "current_health": target_health if target_present else None,
            "maximum_health": 180.0 if target_present else None,
            "lt": 1005.0 if target_present else None,
            "lg": 2000.0 if target_present else None,
            "altitude": 10.0 if target_present else None,
            "planar_distance": 5.0 if target_present else None,
            "altitude_delta": 0.0 if target_present else None,
            "spatial_distance": 5.0 if target_present else None,
        },
        "player": {
            "current_health": player_health,
            "maximum_health": 500.0,
            "current_mana": mana,
            "maximum_mana": 220.0,
            "current_stamina": 100.0,
            "maximum_stamina": 100.0,
            "lt": 1000.0,
            "lg": 2000.0,
            "altitude": 10.0,
        },
        "combat_events": [] if events is None else events,
        "input_accepted": None,
        "input_reason": None,
    }


def _event(
    sequence: int,
    kind: str,
    *,
    amount: float | None = None,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "timestamp": "1:00:00",
        "kind": kind,
        "message": kind,
        "target_name": "Camp Mob",
        "amount": amount,
    }


def _evidence() -> dict[str, object]:
    trace = [
        _step(0, intent="shadowbane.assassin.shadow_touch"),
        _step(
            200,
            mana=165.0,
            player_health=494.0,
            target_health=170.0,
            events=[
                _event(0, "player_hit_target", amount=10.0),
                _event(1, "target_hit_player", amount=6.0),
            ],
        ),
        _step(
            1_200,
            mana=165.0,
            player_health=488.0,
            target_health=158.0,
            events=[
                _event(2, "player_hit_target", amount=12.0),
                _event(3, "target_missed_player"),
            ],
        ),
        _step(
            1_400,
            mana=165.0,
            target_present=False,
            events=[
                _event(4, "target_killed"),
                _event(5, "experience_gained", amount=744.0),
            ],
        ),
    ]
    return {
        "trace_schema_version": 1,
        "ok": True,
        "final_phase": "complete",
        "terminal_reason": "kill_limit_reached",
        "policy": "proc-assassin",
        "kills": 1,
        "steps": len(trace),
        "dispatched": [],
        "native_observation": {
            "process_id": 4320,
            "executable_sha256": "ab" * 32,
        },
        "trace": trace,
    }


class PvECombatCalibrationTests(unittest.TestCase):
    def test_compiles_observed_combat_and_resource_samples(self) -> None:
        calibration = compile_pve_combat_calibration((_evidence(),))

        self.assertEqual(1, calibration.confirmed_kills)
        self.assertEqual(
            (2, 0, 1, 1),
            (
                calibration.player_hits,
                calibration.player_misses,
                calibration.target_hits,
                calibration.target_misses,
            ),
        )
        self.assertEqual(1.0, calibration.player_hit_rate)
        self.assertEqual(0.5, calibration.target_hit_rate)
        self.assertEqual(
            (10.0, 12.0),
            (
                calibration.player_damage.minimum,
                calibration.player_damage.maximum,
            ),
        )
        self.assertEqual(1_000.0, calibration.player_attack_interval_ms.median)
        self.assertEqual(6.0, calibration.target_damage.median)
        self.assertEqual(1_000.0, calibration.target_attack_interval_ms.median)
        self.assertEqual(180.0, calibration.target_maximum_health.median)
        self.assertEqual(744.0, calibration.experience_reward.median)
        self.assertEqual(500.0, calibration.starting_player_health.median)
        self.assertEqual(220.0, calibration.starting_player_mana.median)
        self.assertEqual(100.0, calibration.starting_player_stamina.median)
        self.assertEqual(5.0, calibration.engagement_planar_distance.median)
        self.assertEqual(55.0, calibration.shadow_touch_mana_delta.median)
        self.assertEqual(
            (10.0, 12.0),
            (
                calibration.native_target_health_decrease.minimum,
                calibration.native_target_health_decrease.maximum,
            ),
        )
        self.assertEqual(
            1_000.0,
            calibration.native_target_health_decrease_interval_ms.median,
        )
        self.assertEqual(6.0, calibration.native_player_health_decrease.median)
        self.assertEqual(
            1_000.0,
            calibration.native_player_health_decrease_interval_ms.median,
        )

    def test_round_trips_a_compiled_calibration(self) -> None:
        calibration = compile_pve_combat_calibration((_evidence(),))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "calibration.json"

            save_pve_combat_calibration(path, calibration)

            self.assertEqual(calibration, load_pve_combat_calibration(path))

    def test_rejects_duplicate_evidence_that_would_double_count_samples(self) -> None:
        evidence = _evidence()

        with self.assertRaisesRegex(PvECombatCalibrationError, "duplicate"):
            compile_pve_combat_calibration((evidence, deepcopy(evidence)))

    def test_rejects_duplicate_native_combat_event_sequences(self) -> None:
        evidence = _evidence()
        evidence["trace"][2]["combat_events"][0]["sequence"] = 0

        with self.assertRaisesRegex(PvECombatCalibrationError, "repeats"):
            compile_pve_combat_calibration((evidence,))

    def test_cli_compiles_trace_files_into_a_calibration_artifact(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "fight.json"
            calibration_path = Path(directory) / "calibration.json"
            save_pve_trace_evidence(evidence_path, _evidence())

            with redirect_stdout(output):
                result = main(
                    (
                        "client",
                        "calibrate-pve",
                        "--evidence",
                        str(evidence_path),
                        "--output",
                        str(calibration_path),
                        "--json",
                    )
                )

            saved = load_pve_combat_calibration(calibration_path)

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(saved.profile_id, payload["profile_id"])
        self.assertEqual(str(calibration_path), payload["output_path"])


if __name__ == "__main__":
    unittest.main()
