import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace

from shadowbane_lab.rollouts import (
    PurePvETerminationReason,
    frost_walker_observed_config,
    run_pure_pve_batch,
    run_pure_pve_encounter,
)
from shadowbane_lab.rollouts.__main__ import main


class PurePvERolloutTests(unittest.TestCase):
    def test_direct_encounter_attacks_known_mob_without_controller_acquisition(self) -> None:
        config = frost_walker_observed_config(seed=23)

        result = run_pure_pve_encounter(config)

        self.assertEqual(PurePvETerminationReason.MOB_DEFEATED, result.reason)
        self.assertTrue(result.killed)
        self.assertEqual((4.0, 5.0, 5.0), result.attack_rolls)
        self.assertEqual((4.0, 5.0, 1.0), result.effective_damage)
        self.assertEqual(2_000, result.kill_time_ms)
        self.assertEqual(0.0, result.target_final_health)
        self.assertEqual(744.0, result.experience_earned)
        self.assertEqual(0, result.rejected_actions)

    def test_batch_is_reproducible_and_distributions_account_for_every_episode(self) -> None:
        config = frost_walker_observed_config()

        first = run_pure_pve_batch(config, episodes=1_000, seed_start=0)
        second = run_pure_pve_batch(config, episodes=1_000, seed_start=0)

        self.assertEqual(first, second)
        self.assertEqual(1_000, first.kills)
        self.assertEqual(0, first.timeouts)
        self.assertEqual(1.0, first.kill_rate)
        self.assertEqual(
            1_000,
            sum(item.count for item in first.attacks_to_kill),
        )
        self.assertEqual(
            1_000,
            sum(item.count for item in first.kill_times_ms),
        )
        self.assertEqual(
            sum(item.value * item.count for item in first.attacks_to_kill),
            sum(item.count for item in first.damage_rolls),
        )
        self.assertEqual(744_000.0, first.total_experience)
        self.assertEqual((), first.episode_results)

    def test_batch_can_retain_exact_seed_results_on_request(self) -> None:
        result = run_pure_pve_batch(
            frost_walker_observed_config(),
            episodes=10,
            seed_start=50,
            retain_episode_results=True,
        )

        self.assertEqual(tuple(range(50, 60)), tuple(item.seed for item in result.episode_results))

    def test_tick_limit_is_a_simulation_outcome_without_live_safety_semantics(self) -> None:
        config = replace(frost_walker_observed_config(), max_ticks=1)

        result = run_pure_pve_encounter(config)

        self.assertEqual(PurePvETerminationReason.TICK_LIMIT, result.reason)
        self.assertFalse(result.killed)
        self.assertEqual(0.0, result.experience_earned)
        self.assertEqual(1, len(result.attack_rolls))
        self.assertIn(result.attack_rolls[0], (4.0, 5.0))
        self.assertEqual(10.0 - result.attack_rolls[0], result.target_final_health)

    def test_batch_bounds_reject_invalid_episode_counts(self) -> None:
        config = frost_walker_observed_config()

        with self.assertRaisesRegex(ValueError, "episodes"):
            run_pure_pve_batch(config, episodes=0)
        with self.assertRaisesRegex(ValueError, "seed_start"):
            run_pure_pve_batch(config, episodes=1, seed_start=-1)

    def test_cli_emits_compact_pure_batch_summary(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                (
                    "--scenario",
                    "pure-frost-walker",
                    "--episodes",
                    "100",
                    "--seed",
                    "0",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual(100, payload["episodes"])
        self.assertEqual(100, payload["kills"])
        self.assertNotIn("episode_results", payload)


if __name__ == "__main__":
    unittest.main()
