import io
import json
import unittest
from contextlib import redirect_stdout

from shadowbane_lab.rollouts import (
    CombatantConfig,
    DuelConfig,
    TerminationReason,
    matched_progression_duels,
    progression_build,
    progression_duel_matrix,
    run_duel,
)
from shadowbane_lab.rollouts.__main__ import main
from shadowbane_lab.rulesets import CharacterBuild

SHADOW_BOLT = "shadowbane.assassin.shadow_bolt"
SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"
MIND_STRIKE = "shadowbane.warlock.mind_strike"
PSYCHIC_HEALING = "shadowbane.warlock.psychic_healing"
STEAL_BREATH = "shadowbane.assassin.steal_breath"
PSYCHIC_SHIELD = "shadowbane.warlock.psychic_shield"


def build(profession: str, level: int, rank: int) -> CharacterBuild:
    if profession == "assassin":
        skill = "shadowmastery"
        powers = (SHADOW_BOLT, SHADOW_TOUCH)
    else:
        skill = "warlockry"
        powers = (MIND_STRIKE, PSYCHIC_HEALING)
    return CharacterBuild(
        profession=profession,
        level=level,
        skill_ranks=((skill, 200),),
        power_ranks=tuple((power, rank) for power in powers),
    )


class DuelRolloutTests(unittest.TestCase):
    def test_progression_build_clamps_limited_rank_powers(self) -> None:
        ranks = dict(progression_build("assassin", 75, 40).power_ranks)

        self.assertEqual(40, ranks["shadowbane.assassin.backstab"])
        self.assertEqual(20, ranks["shadowbane.assassin.fade"])
        self.assertEqual(20, ranks["shadowbane.assassin.invisibility"])

    def test_duel_is_reproducible_and_reaches_a_terminal_outcome(self) -> None:
        config = DuelConfig(
            left=CombatantConfig("assassin", "red", build("assassin", 26, 40)),
            right=CombatantConfig("warlock", "blue", build("warlock", 26, 40)),
            max_ticks=1_000,
            seed=72,
        )

        first = run_duel(config)
        second = run_duel(config)

        self.assertEqual(first, second)
        self.assertEqual(TerminationReason.LAST_TEAM_STANDING, first.reason)
        self.assertIsNotNone(first.winner_entity_id)
        self.assertTrue(any(item.damage_dealt > 0 for item in first.combatants))
        self.assertTrue(all(item.rejected_actions == 0 for item in first.combatants))

    def test_level_gates_change_action_usage(self) -> None:
        results = matched_progression_duels(
            levels=(10, 15, 18, 26), power_ranks=(40,), max_ticks=1_000
        )

        by_level = {level: result for level, _, result in results}
        assassin_10 = dict(
            (item.action_key, item.count) for item in by_level[10].combatants[0].actions
        )
        assassin_15 = dict(
            (item.action_key, item.count) for item in by_level[15].combatants[0].actions
        )
        warlock_15 = dict(
            (item.action_key, item.count) for item in by_level[15].combatants[1].actions
        )
        assassin_18 = dict(
            (item.action_key, item.count) for item in by_level[18].combatants[0].actions
        )
        warlock_18 = dict(
            (item.action_key, item.count) for item in by_level[18].combatants[1].actions
        )

        self.assertNotIn(SHADOW_TOUCH, assassin_10)
        self.assertGreater(assassin_15.get(SHADOW_TOUCH, 0), 0)
        self.assertNotIn(PSYCHIC_HEALING, warlock_15)
        self.assertGreater(assassin_18.get(STEAL_BREATH, 0), 0)
        self.assertGreater(warlock_18.get(PSYCHIC_SHIELD, 0), 0)

    def test_rank_brackets_change_compiled_power_usage_or_outcome(self) -> None:
        results = matched_progression_duels(levels=(26,), power_ranks=(0, 40), max_ticks=1_000)

        low = results[0][2]
        high = results[1][2]

        self.assertNotEqual(low.as_dict(), high.as_dict())

    def test_time_limit_is_reported_as_truncation_without_a_winner(self) -> None:
        config = DuelConfig(
            left=CombatantConfig("assassin", "red", build("assassin", 10, 0)),
            right=CombatantConfig("warlock", "blue", build("warlock", 10, 0)),
            max_ticks=1,
        )

        result = run_duel(config)

        self.assertEqual(TerminationReason.TIME_LIMIT, result.reason)
        self.assertIsNone(result.winner_entity_id)
        self.assertEqual(1, result.ticks)

    def test_explicit_power_subset_excludes_unselected_power(self) -> None:
        assassin = CharacterBuild(
            profession="assassin",
            level=26,
            skill_ranks=(("shadowmastery", 200),),
            power_ranks=((SHADOW_BOLT, 40), (SHADOW_TOUCH, 40)),
            enabled_power_keys=(SHADOW_BOLT,),
        )
        config = DuelConfig(
            left=CombatantConfig("assassin", "red", assassin),
            right=CombatantConfig("warlock", "blue", build("warlock", 26, 40)),
        )

        result = run_duel(config)
        assassin_actions = {item.action_key for item in result.combatants[0].actions}

        self.assertNotIn(SHADOW_TOUCH, assassin_actions)

    def test_relational_movement_closes_range_without_rejections(self) -> None:
        assassin = build("assassin", 26, 40)
        warlock = build("warlock", 26, 40)
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
                left=CombatantConfig("assassin", "red", assassin),
                right=CombatantConfig("warlock", "blue", warlock),
                starting_distance=50.0,
                max_ticks=200,
            )
        )

        for combatant in result.combatants:
            actions = {item.action_key for item in combatant.actions}
            self.assertIn("sim.range.close", actions)
            self.assertNotIn("shadowbane.move", actions)
            self.assertIn("shadowbane.basic_attack", actions)
            self.assertEqual(0, combatant.rejected_actions)

    def test_cli_emits_machine_readable_results(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(("--levels", "10", "--ranks", "0", "--json"))

        payload = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(payload))
        self.assertEqual(10, payload[0]["level"])
        self.assertIn(payload[0]["winner_entity_id"], ("assassin", "warlock", None))

    def test_matrix_aggregates_distances_and_seed_variation(self) -> None:
        cells = progression_duel_matrix(
            levels=(10,),
            power_ranks=(0,),
            starting_distances=(15.0, 60.0),
            seeds=(1, 2),
            max_ticks=100,
        )

        self.assertEqual(2, len(cells))
        for cell in cells:
            self.assertEqual(2, cell.matches)
            self.assertEqual(
                cell.matches,
                cell.assassin_wins + cell.warlock_wins + cell.draws,
            )
            self.assertEqual(2, cell.unique_trace_count)

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
                    "--max-ticks",
                    "100",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(payload))
        self.assertEqual(2, payload[0]["matches"])
        self.assertEqual(2, payload[0]["unique_trace_count"])


if __name__ == "__main__":
    unittest.main()
