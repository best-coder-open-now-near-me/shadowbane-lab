import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace

from shadowbane_lab.progression import StatLine
from shadowbane_lab.rollouts import (
    CampMobConfig,
    SmartCampConfig,
    SmartCampTerminationReason,
    irekei_proc_assassin_smart_camp_config,
    run_smart_camp,
    run_smart_camp_batch,
)
from shadowbane_lab.rollouts.__main__ import main


class SmartCampRolloutTests(unittest.TestCase):
    def test_default_proc_assassin_retains_targets_and_clears_the_camp(self) -> None:
        result = run_smart_camp(irekei_proc_assassin_smart_camp_config(seed=4))

        self.assertEqual(SmartCampTerminationReason.CAMP_CLEARED, result.reason)
        self.assertTrue(result.player_alive)
        self.assertEqual(3, result.mobs_killed)
        self.assertEqual(("camp-mob-1", "camp-mob-2", "camp-mob-3"), result.target_sequence)
        self.assertEqual(0, result.rejected_actions)
        action_counts = dict(result.action_counts)
        self.assertEqual(3, action_counts["shadowbane.assassin.shadow_touch"])
        fist_attacks = action_counts["shadowbane.assassin.dual_fist_successful_hit"]
        self.assertEqual(
            [fist_attacks, fist_attacks],
            [item.checks for item in result.proc_outcomes],
        )
        changed = [choice.target_entity_id for choice in result.choices if choice.target_changed]
        self.assertEqual(list(result.target_sequence), changed)

    def test_same_seed_replays_identically(self) -> None:
        config = irekei_proc_assassin_smart_camp_config(seed=17)

        first = run_smart_camp(config)
        second = run_smart_camp(config)

        self.assertEqual(first, second)

    def test_batch_aggregates_seeded_outcomes_without_retaining_episodes(self) -> None:
        config = irekei_proc_assassin_smart_camp_config(seed=0)

        result = run_smart_camp_batch(config, episodes=25)

        self.assertEqual(25, result.camps_cleared)
        self.assertEqual(0, result.player_defeats)
        self.assertEqual(0, result.timeouts)
        self.assertEqual(1.0, result.clear_rate)
        self.assertGreater(result.p90_clear_time_ms, result.p50_clear_time_ms)
        self.assertEqual(0, result.rejected_actions)
        self.assertEqual((), result.episode_results)
        fist_attacks = dict(result.action_counts)[
            "shadowbane.assassin.dual_fist_successful_hit"
        ]
        self.assertEqual(
            [fist_attacks, fist_attacks],
            [item.checks for item in result.proc_outcomes],
        )

    def test_cli_emits_compact_smart_camp_batch(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                (
                    "--scenario",
                    "smart-camp",
                    "--episodes",
                    "5",
                    "--seed",
                    "0",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual(5, payload["episodes"])
        self.assertEqual(5, payload["camps_cleared"])
        self.assertNotIn("episode_results", payload)

    def test_short_tick_budget_reports_timeout_without_laundering_a_kill(self) -> None:
        config = replace(irekei_proc_assassin_smart_camp_config(seed=1), max_ticks=1)

        result = run_smart_camp(config)

        self.assertEqual(SmartCampTerminationReason.TICK_LIMIT, result.reason)
        self.assertEqual(0, result.mobs_killed)

    def test_timeout_only_batch_has_no_fabricated_clear_time(self) -> None:
        config = replace(irekei_proc_assassin_smart_camp_config(seed=1), max_ticks=1)

        result = run_smart_camp_batch(config, episodes=3)

        self.assertEqual(3, result.timeouts)
        self.assertEqual(0, result.camps_cleared)
        self.assertIsNone(result.mean_clear_time_ms)
        self.assertIsNone(result.p50_clear_time_ms)

    def test_config_rejects_duplicate_mob_ids(self) -> None:
        mob = CampMobConfig("mob", 10.0, 1.0)

        with self.assertRaisesRegex(ValueError, "unique"):
            SmartCampConfig(
                profile_id="invalid",
                stats=StatLine(1, 1, 1, 1, 1),
                mobs=(mob, mob),
            )


if __name__ == "__main__":
    unittest.main()
