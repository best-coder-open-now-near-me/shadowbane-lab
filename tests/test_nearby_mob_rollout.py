import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace

from shadowbane_lab.pve import PvEIntent, PvEPhase
from shadowbane_lab.rollouts import (
    NearbyMobSimulationConfig,
    frost_walker_observed_config,
    run_nearby_mob_simulation,
)
from shadowbane_lab.rollouts.__main__ import main


class NearbyMobRolloutTests(unittest.TestCase):
    def test_frost_walker_profile_drives_production_controller_to_one_kill(self) -> None:
        config = frost_walker_observed_config(seed=23)

        result = run_nearby_mob_simulation(config)

        self.assertEqual(PvEPhase.COMPLETE, result.final_phase)
        self.assertEqual("kill_limit_reached", result.terminal_reason)
        self.assertEqual(1, result.kills)
        self.assertEqual(0.0, result.target_final_health)
        self.assertEqual(config.player_current_health, result.player_final_health)
        self.assertEqual(744.0, result.experience_observed)
        self.assertEqual(0, result.rejected_actions)
        self.assertEqual(10.0, sum(result.effective_damage))
        self.assertTrue(all(item in (4.0, 5.0) for item in result.attack_rolls))
        intents = tuple(item.intent for item in result.controller_trace if item.intent is not None)
        self.assertEqual(
            (PvEIntent.ACQUIRE_NEXT_MOB, PvEIntent.ATTACK_SELECTED_TARGET),
            intents,
        )

    def test_same_seed_replays_the_entire_controller_and_combat_trace(self) -> None:
        config = frost_walker_observed_config(seed=72)

        self.assertEqual(
            run_nearby_mob_simulation(config),
            run_nearby_mob_simulation(config),
        )

    def test_player_health_guard_stops_before_simulated_input_or_damage(self) -> None:
        config = replace(
            frost_walker_observed_config(),
            player_current_health=500.0,
        )

        result = run_nearby_mob_simulation(config)

        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertEqual("player_health_safety_threshold", result.terminal_reason)
        self.assertEqual((), result.attack_rolls)
        self.assertEqual(0, result.ticks)
        self.assertEqual(10.0, result.target_final_health)

    def test_attack_interval_must_align_to_the_reference_tick(self) -> None:
        with self.assertRaisesRegex(ValueError, "align"):
            replace(frost_walker_observed_config(), attack_interval_ms=999)

    def test_cli_emits_machine_readable_frost_walker_trace(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                (
                    "--scenario",
                    "frost-walker",
                    "--seed",
                    "23",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual("wonderbane.frost-walker.2026-08-25", payload["profile_id"])
        self.assertEqual("kill_limit_reached", payload["terminal_reason"])
        self.assertEqual(1, payload["kills"])

    def test_config_type_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "NearbyMobSimulationConfig"):
            run_nearby_mob_simulation(object())  # type: ignore[arg-type]

        self.assertIsInstance(frost_walker_observed_config(), NearbyMobSimulationConfig)


if __name__ == "__main__":
    unittest.main()
