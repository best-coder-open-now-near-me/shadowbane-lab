import io
import json
import unittest
from contextlib import redirect_stdout

from shadowbane_lab.rollouts import (
    CombatantConfig,
    DuelConfig,
    TerminationReason,
    load_assassin_warlock_duel_ruleset,
    matched_progression_duels,
    progression_build,
    progression_duel_matrix,
    run_duel,
)
from shadowbane_lab.rollouts.__main__ import main
from shadowbane_lab.rulesets import CharacterBuild, CompilationStatus

MOVE = "shadowbane.move"
BASIC_ATTACK = "shadowbane.basic_attack"
SHADOW_BOLT = "shadowbane.assassin.shadow_bolt"
SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"
FADE = "shadowbane.assassin.fade"
BACKSTAB = "shadowbane.assassin.backstab"
INVISIBILITY = "shadowbane.assassin.invisibility"
PASSWALL = "shadowbane.assassin.passwall"
MIND_STRIKE = "shadowbane.warlock.mind_strike"
MIND_SNARE = "shadowbane.warlock.mind_snare"
PSYCHIC_HEALING = "shadowbane.warlock.psychic_healing"
LEVITATION = "shadowbane.warlock.levitation"


class DuelRolloutTests(unittest.TestCase):
    def test_duel_extension_loads_without_duplicate_base_actions(self) -> None:
        ruleset = load_assassin_warlock_duel_ruleset()

        self.assertEqual("shadowbane.assassin-warlock-duel.v1", ruleset.ruleset_id)
        self.assertEqual(12, len(ruleset.records))
        self.assertEqual(11, len(ruleset.catalog))
        self.assertEqual(
            {
                CompilationStatus.COMPILED: 0,
                CompilationStatus.COMPILED_WITH_OVERRIDE: 11,
                CompilationStatus.UNRESOLVED: 1,
            },
            ruleset.status_counts(),
        )
        for action_key in (FADE, BACKSTAB, INVISIBILITY, MIND_SNARE):
            self.assertIsNotNone(ruleset.record(action_key).action)

    def test_progression_build_clamps_twenty_rank_stealth_powers(self) -> None:
        build = progression_build("assassin", 75, 40)
        ranks = dict(build.power_ranks)

        self.assertEqual(40, ranks[SHADOW_BOLT])
        self.assertEqual(40, ranks[BACKSTAB])
        self.assertEqual(20, ranks[FADE])
        self.assertEqual(20, ranks[INVISIBILITY])

    def test_level_and_power_prerequisites_change_available_kits(self) -> None:
        results = matched_progression_duels(
            levels=(10, 15, 18, 19, 22, 26, 28, 75),
            power_ranks=(20,),
            max_ticks=1,
        )
        by_level = {level: result for level, _, result in results}

        assassin_10 = set(by_level[10].combatants[0].available_actions)
        assassin_15 = set(by_level[15].combatants[0].available_actions)
        assassin_19 = set(by_level[19].combatants[0].available_actions)
        assassin_28 = set(by_level[28].combatants[0].available_actions)
        warlock_10 = set(by_level[10].combatants[1].available_actions)
        warlock_18 = set(by_level[18].combatants[1].available_actions)
        warlock_22 = set(by_level[22].combatants[1].available_actions)
        warlock_26 = set(by_level[26].combatants[1].available_actions)

        self.assertTrue({MOVE, BASIC_ATTACK, SHADOW_BOLT, FADE, BACKSTAB} <= assassin_10)
        self.assertNotIn(SHADOW_TOUCH, assassin_10)
        self.assertIn(SHADOW_TOUCH, assassin_15)
        self.assertIn(INVISIBILITY, assassin_19)
        self.assertNotIn(PASSWALL, assassin_28)
        self.assertIn(MIND_STRIKE, warlock_10)
        self.assertNotIn(MIND_SNARE, warlock_10)
        self.assertIn(MIND_SNARE, warlock_18)
        self.assertIn(LEVITATION, warlock_22)
        self.assertIn(PSYCHIC_HEALING, warlock_26)

    def test_invisibility_requires_fade_rank_eighteen(self) -> None:
        low = matched_progression_duels(levels=(19,), power_ranks=(10,), max_ticks=1)[0][2]
        high = matched_progression_duels(levels=(19,), power_ranks=(20,), max_ticks=1)[0][2]

        self.assertNotIn(INVISIBILITY, low.combatants[0].available_actions)
        self.assertIn(INVISIBILITY, high.combatants[0].available_actions)

    def test_duel_is_reproducible_and_reaches_a_terminal_outcome(self) -> None:
        config = DuelConfig(
            left=CombatantConfig(
                "assassin", "red", progression_build("assassin", 26, 40), health=200.0
            ),
            right=CombatantConfig(
                "warlock", "blue", progression_build("warlock", 26, 40), health=200.0
            ),
            max_ticks=1_200,
            seed=72,
        )

        first = run_duel(config)
        second = run_duel(config)

        self.assertEqual(first, second)
        self.assertEqual(TerminationReason.LAST_TEAM_STANDING, first.reason)
        self.assertIsNotNone(first.winner_entity_id)
        self.assertTrue(any(item.damage_dealt > 0 for item in first.combatants))
        self.assertTrue(all(item.rejected_actions == 0 for item in first.combatants))
        self.assertEqual(first.trace_digest, second.trace_digest)

    def test_rank_brackets_change_compiled_power_usage_or_outcome(self) -> None:
        results = matched_progression_duels(levels=(26,), power_ranks=(0, 40), max_ticks=1_200)

        low = results[0][2]
        high = results[1][2]

        self.assertNotEqual(low.as_dict(), high.as_dict())

    def test_time_limit_is_reported_as_truncation_without_a_winner(self) -> None:
        config = DuelConfig(
            left=CombatantConfig("assassin", "red", progression_build("assassin", 10, 0)),
            right=CombatantConfig("warlock", "blue", progression_build("warlock", 10, 0)),
            max_ticks=1,
        )

        result = run_duel(config)

        self.assertEqual(TerminationReason.TIME_LIMIT, result.reason)
        self.assertIsNone(result.winner_entity_id)
        self.assertEqual(1, result.ticks)

    def test_explicit_power_subset_excludes_unselected_power(self) -> None:
        assassin = progression_build("assassin", 26, 40)
        assassin = CharacterBuild(
            profession=assassin.profession,
            level=assassin.level,
            skill_ranks=assassin.skill_ranks,
            power_ranks=assassin.power_ranks,
            enabled_power_keys=(SHADOW_BOLT,),
        )
        config = DuelConfig(
            left=CombatantConfig("assassin", "red", assassin, health=200.0),
            right=CombatantConfig(
                "warlock",
                "blue",
                progression_build("warlock", 26, 40),
                health=200.0,
            ),
        )

        result = run_duel(config)

        self.assertNotIn(SHADOW_TOUCH, result.combatants[0].available_actions)
        self.assertNotIn(BACKSTAB, result.combatants[0].available_actions)

    def test_common_movement_closes_range_without_rejections(self) -> None:
        assassin = progression_build("assassin", 26, 40)
        warlock = progression_build("warlock", 26, 40)
        assassin = CharacterBuild(
            profession=assassin.profession,
            level=assassin.level,
            skill_ranks=assassin.skill_ranks,
            power_ranks=assassin.power_ranks,
            enabled_power_keys=(),
        )
        warlock = CharacterBuild(
            profession=warlock.profession,
            level=warlock.level,
            skill_ranks=warlock.skill_ranks,
            power_ranks=warlock.power_ranks,
            enabled_power_keys=(),
        )
        result = run_duel(
            DuelConfig(
                left=CombatantConfig("assassin", "red", assassin, health=200.0),
                right=CombatantConfig("warlock", "blue", warlock, health=200.0),
                starting_distance=50.0,
                max_ticks=400,
            )
        )

        for combatant in result.combatants:
            actions = {item.action_key for item in combatant.actions}
            self.assertIn(MOVE, actions)
            self.assertIn(BASIC_ATTACK, actions)
            self.assertEqual(0, combatant.rejected_actions)

    def test_matrix_aggregates_distances_and_seed_invariance(self) -> None:
        cells = progression_duel_matrix(
            levels=(10,),
            power_ranks=(0,),
            starting_distances=(15.0, 60.0),
            seeds=(1, 2),
            max_ticks=1_200,
        )

        self.assertEqual(2, len(cells))
        for cell in cells:
            self.assertEqual(2, cell.matches)
            self.assertEqual(cell.matches, cell.assassin_wins + cell.warlock_wins + cell.draws)
            self.assertEqual(1, cell.unique_trace_count)

    def test_cli_emits_machine_readable_results(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(("--levels", "10", "--ranks", "0", "--json"))

        payload = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(payload))
        self.assertEqual(10, payload[0]["level"])
        self.assertIn(payload[0]["winner_entity_id"], ("assassin", "warlock", None))
        self.assertIn("available_actions", payload[0]["combatants"][0])

    def test_matrix_cli_emits_aggregate_cells(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                (
                    "--matrix",
                    "--levels",
                    "10",
                    "--ranks",
                    "0",
                    "--distances",
                    "15",
                    "--seeds",
                    "1,2",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(payload))
        self.assertEqual(2, payload[0]["matches"])
        self.assertEqual(1, payload[0]["unique_trace_count"])


if __name__ == "__main__":
    unittest.main()
