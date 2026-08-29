import json
import unittest

from shadowbane_lab.rollouts.duel import (
    BACKSTAB,
    INVISIBILITY,
    MIND_STRIKE,
    PSYCHIC_HEALING,
    SHADOW_MANTLE,
)
from shadowbane_lab.rollouts.open_builds import (
    PrimitiveLoadout,
    generate_primitive_loadouts,
    load_open_roster_text,
    resolve_primitive_loadout,
    round_robin_open_duels,
    run_open_duel,
)
from shadowbane_lab.rollouts.ruleset import load_assassin_warlock_duel_ruleset


class OpenBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ruleset = load_assassin_warlock_duel_ruleset()

    def test_resolution_ignores_class_labels_and_reports_unknown_actions(self) -> None:
        loadout = PrimitiveLoadout(
            loadout_id="mixed",
            display_name="Mixed primitive bag",
            action_keys=(MIND_STRIKE, SHADOW_MANTLE, "unknown.future.proc"),
            metadata=(
                ("race", "irekei"),
                ("class", "not-semantic"),
                ("discipline", "also-not-semantic"),
            ),
        )

        resolved = resolve_primitive_loadout(loadout, self.ruleset)

        self.assertEqual((MIND_STRIKE, SHADOW_MANTLE), resolved.executable_action_keys)
        self.assertEqual(("unknown.future.proc",), resolved.omitted_action_keys)
        self.assertIn("capability.damage", resolved.capability_tags)
        self.assertIn("capability.healing_block", resolved.capability_tags)
        self.assertAlmostEqual(2 / 3, resolved.coverage_fraction)

    def test_cross_source_primitive_bags_run_through_normal_harness(self) -> None:
        left = PrimitiveLoadout(
            loadout_id="left-mix",
            display_name="Mind strike plus mantle",
            action_keys=(MIND_STRIKE, SHADOW_MANTLE, "future.absorber"),
        )
        right = PrimitiveLoadout(
            loadout_id="right-mix",
            display_name="Heal plus backstab",
            action_keys=(PSYCHIC_HEALING, BACKSTAB),
        )

        result = run_open_duel(
            self.ruleset,
            left,
            right,
            starting_distance=15.0,
            max_ticks=12,
            seed=9,
        )

        self.assertEqual(("future.absorber",), result.left.omitted_action_keys)
        self.assertNotIn("visibility.invisible", result.right.auto_added_tags)
        self.assertIn("visibility.invisible", result.right.unsatisfied_requirement_tags)
        self.assertEqual("open", result.duel.combatants[0].profession)
        self.assertEqual(0, result.duel.combatants[0].rejected_actions)
        self.assertEqual(0, result.duel.combatants[1].rejected_actions)

    def test_open_duel_reports_actual_trigger_use_not_just_ownership(self) -> None:
        left = PrimitiveLoadout(
            loadout_id="trigger-user",
            display_name="Stealth into armed weapon action",
            action_keys=(INVISIBILITY, BACKSTAB),
            health=2_000.0,
        )
        right = PrimitiveLoadout(
            loadout_id="durable-target",
            display_name="Durable target",
            action_keys=(MIND_STRIKE,),
            health=2_000.0,
        )

        result = run_open_duel(
            self.ruleset,
            left,
            right,
            starting_distance=15.0,
            max_ticks=60,
            seed=11,
        )
        left_result = next(
            item for item in result.duel.combatants if item.entity_id == left.loadout_id
        )

        self.assertEqual(
            {"backstab_armed": 1}, {item.trigger_key: item.count for item in left_result.triggers}
        )

    def test_generator_is_reproducible_and_uses_behavior_groups(self) -> None:
        first = generate_primitive_loadouts(
            self.ruleset,
            count=6,
            seed=44,
            minimum_actions=2,
            maximum_actions=4,
        )
        second = generate_primitive_loadouts(
            self.ruleset,
            count=6,
            seed=44,
            minimum_actions=2,
            maximum_actions=4,
        )

        self.assertEqual(first, second)
        records = {record.action_key: record for record in self.ruleset.records}
        for loadout in first:
            tags = {
                tag for action_key in loadout.action_keys for tag in records[action_key].action.tags
            }
            self.assertTrue(tags & {"damage", "attack", "control"})
            self.assertNotIn("profession", dict(loadout.metadata))

    def test_round_robin_mirrors_each_pair(self) -> None:
        loadouts = generate_primitive_loadouts(
            self.ruleset,
            count=3,
            seed=3,
            minimum_actions=2,
            maximum_actions=3,
        )

        cells = round_robin_open_duels(
            self.ruleset,
            loadouts,
            starting_distances=(15.0,),
            seeds=(1,),
            max_ticks=8,
            mirrored=True,
        )

        self.assertEqual(3, len(cells))
        self.assertTrue(all(cell.matches == 2 for cell in cells))
        self.assertTrue(all(0.0 <= cell.mean_coverage <= 1.0 for cell in cells))

    def test_roster_keeps_labels_as_metadata_only(self) -> None:
        roster = {
            "schema_version": 1,
            "loadouts": [
                {
                    "loadout_id": "anything",
                    "display_name": "Anything",
                    "action_keys": [MIND_STRIKE, SHADOW_MANTLE],
                    "health": 612,
                    "metadata": {
                        "race": "shade",
                        "promotion": "warlock",
                        "note": "labels only",
                    },
                }
            ],
        }

        loaded = load_open_roster_text(json.dumps(roster))

        self.assertEqual(612, loaded[0].health)
        self.assertEqual("warlock", dict(loaded[0].metadata)["promotion"])
        self.assertEqual((MIND_STRIKE, SHADOW_MANTLE), loaded[0].action_keys)


if __name__ == "__main__":
    unittest.main()
