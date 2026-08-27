import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

from shadowbane_lab.progression import StatLine
from shadowbane_lab.pve import (
    ObservedSampleSummary,
    PvECombatCalibration,
    save_pve_combat_calibration,
)
from shadowbane_lab.rollouts import (
    CampMobConfig,
    SmartCampConfig,
    SmartCampTerminationReason,
    apply_pve_combat_calibration,
    irekei_proc_assassin_smart_camp_config,
    run_smart_camp,
    run_smart_camp_batch,
)
from shadowbane_lab.rollouts.__main__ import main


def _summary(*values: float) -> ObservedSampleSummary:
    result = ObservedSampleSummary.from_samples(values)
    assert result is not None
    return result


def _calibration() -> PvECombatCalibration:
    return PvECombatCalibration(
        profile_id="wonderbane.live-pve.test",
        source_trace_sha256s=("11" * 32,),
        executable_sha256s=("22" * 32,),
        policies=("proc-assassin",),
        confirmed_kills=2,
        player_hits=3,
        player_misses=1,
        target_hits=2,
        target_misses=1,
        target_maximum_health=_summary(240.0),
        player_damage=_summary(10.0, 12.0),
        target_damage=_summary(6.0, 9.0),
        player_attack_interval_ms=_summary(1_000.0),
        target_attack_interval_ms=_summary(1_800.0),
        experience_reward=_summary(744.0),
        starting_player_health=_summary(900.0),
        starting_player_mana=_summary(180.0),
        starting_player_stamina=_summary(300.0),
        engagement_planar_distance=_summary(4.0),
        shadow_touch_mana_delta=_summary(55.0),
        native_target_health_decrease=_summary(10.0, 12.0),
        native_target_health_decrease_interval_ms=_summary(1_000.0),
        native_player_health_decrease=_summary(6.0, 9.0),
        native_player_health_decrease_interval_ms=_summary(1_800.0),
        limitations=("test limitation",),
    )


class SmartCampRolloutTests(unittest.TestCase):
    def test_live_calibration_replaces_supported_generic_camp_assumptions(self) -> None:
        config = apply_pve_combat_calibration(
            irekei_proc_assassin_smart_camp_config(seed=4),
            _calibration(),
        )

        self.assertTrue(all(mob.health == 240.0 for mob in config.mobs))
        self.assertTrue(all(mob.distance == 4.0 for mob in config.mobs))
        self.assertTrue(all(mob.attack_damage_minimum == 6 for mob in config.mobs))
        self.assertTrue(all(mob.attack_damage_maximum == 9 for mob in config.mobs))
        self.assertTrue(all(mob.attack_interval_ms == 1_800 for mob in config.mobs))
        self.assertEqual((900.0, 180.0, 300.0), (
            config.player_health,
            config.player_mana,
            config.player_stamina,
        ))
        self.assertIn("wonderbane.live-pve.test", config.evidence)
        self.assertFalse(any("assumed 180 health" in item for item in config.assumptions))

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

    def test_cli_applies_a_live_pve_calibration_to_smart_camp(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            calibration_path = Path(directory) / "calibration.json"
            save_pve_combat_calibration(calibration_path, _calibration())

            with redirect_stdout(output):
                exit_code = main(
                    (
                        "--scenario",
                        "smart-camp",
                        "--episodes",
                        "1",
                        "--seed",
                        "4",
                        "--pve-calibration",
                        str(calibration_path),
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertIn("wonderbane.live-pve.test", payload["profile_id"])
        self.assertIn("wonderbane.live-pve.test", payload["evidence"])

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
