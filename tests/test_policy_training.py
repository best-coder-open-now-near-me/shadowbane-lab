from __future__ import annotations

import unittest
from dataclasses import replace

from shadowbane_lab.optimization.policy_rollout import (
    UtilityPolicyLeagueEvaluator,
    run_open_duel_with_policies,
)
from shadowbane_lab.optimization.policy_search import (
    DiagonalPolicySearchConfig,
    run_diagonal_policy_search,
)
from shadowbane_lab.optimization.training import DuelScenario
from shadowbane_lab.optimization.utility_policy import (
    UtilityPolicyWeights,
    weighted_policy_factory,
)
from shadowbane_lab.rollouts.open_builds import PrimitiveLoadout, run_open_duel
from shadowbane_lab.rollouts.ruleset import load_wonderbane_guide_duel_ruleset


def assassin_loadout() -> PrimitiveLoadout:
    return PrimitiveLoadout(
        loadout_id="policy-assassin",
        display_name="Policy Assassin",
        action_keys=(
            "shadowbane.basic_attack",
            "shadowbane.assassin.shadow_bolt",
            "shadowbane.assassin.shadow_touch",
            "shadowbane.assassin.shadow_mantle",
        ),
        health=600.0,
        mana=420.0,
        stamina=250.0,
        move_speed=22.0,
        scalars=(
            ("attack_rating", 175.0),
            ("attack.power.shadowbane.assassin.shadow_bolt", 185.0),
            ("attack.power.shadowbane.assassin.shadow_touch", 185.0),
            ("defense", 150.0),
            ("weapon.main_hand.damage_min", 10.0),
            ("weapon.main_hand.damage_max", 24.0),
        ),
    )


def warlock_loadout() -> PrimitiveLoadout:
    return PrimitiveLoadout(
        loadout_id="policy-warlock",
        display_name="Policy Warlock",
        action_keys=(
            "shadowbane.basic_attack",
            "shadowbane.warlock.mind_strike",
            "shadowbane.warlock.mind_snare",
            "shadowbane.warlock.psychic_healing",
            "shadowbane.warlock.psychic_shield",
        ),
        health=700.0,
        mana=500.0,
        stamina=220.0,
        move_speed=20.0,
        scalars=(
            ("attack_rating", 160.0),
            ("attack.power.shadowbane.warlock.mind_strike", 190.0),
            ("attack.power.shadowbane.warlock.mind_snare", 190.0),
            ("defense", 165.0),
            ("weapon.main_hand.damage_min", 8.0),
            ("weapon.main_hand.damage_max", 20.0),
        ),
    )


class WeightedUtilityPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ruleset = load_wonderbane_guide_duel_ruleset()

    def test_default_weights_are_trace_identical_to_baseline_policy(self) -> None:
        left = assassin_loadout()
        right = warlock_loadout()
        baseline = run_open_duel(
            self.ruleset,
            left,
            right,
            starting_distance=15.0,
            max_ticks=60,
            seed=17,
        )
        weighted = run_open_duel_with_policies(
            self.ruleset,
            left,
            right,
            left_policy_factory=weighted_policy_factory(UtilityPolicyWeights()),
            right_policy_factory=weighted_policy_factory(UtilityPolicyWeights()),
            starting_distance=15.0,
            max_ticks=60,
            seed=17,
        )

        self.assertEqual(baseline.duel, weighted.duel)
        self.assertEqual(baseline.left, weighted.left)
        self.assertEqual(baseline.right, weighted.right)

    def test_strict_open_duel_does_not_grant_missing_action_requirements(self) -> None:
        backstab = PrimitiveLoadout(
            loadout_id="unproven-backstab",
            display_name="Unproven Backstab",
            action_keys=("shadowbane.assassin.backstab",),
            health=500.0,
            mana=300.0,
            stamina=200.0,
            move_speed=20.0,
        )
        opponent = warlock_loadout()

        strict = run_open_duel_with_policies(
            self.ruleset,
            backstab,
            opponent,
            starting_distance=6.0,
            max_ticks=2,
            seed=1,
            auto_satisfy_action_requirements=False,
        )
        permissive = run_open_duel_with_policies(
            self.ruleset,
            backstab,
            opponent,
            starting_distance=6.0,
            max_ticks=2,
            seed=1,
            auto_satisfy_action_requirements=True,
        )

        self.assertEqual(
            (
                "equipment.melee_weapon",
                "power.stalk",
                "visibility.invisible",
            ),
            strict.left.unsatisfied_requirement_tags,
        )
        self.assertEqual((), strict.left.auto_added_tags)
        self.assertEqual((), permissive.left.unsatisfied_requirement_tags)
        self.assertEqual(
            (
                "equipment.melee_weapon",
                "power.stalk",
                "visibility.invisible",
            ),
            permissive.left.auto_added_tags,
        )

    def test_policy_evaluator_is_deterministic_and_evidence_bound(self) -> None:
        evaluator = UtilityPolicyLeagueEvaluator(
            self.ruleset,
            assassin_loadout(),
            (warlock_loadout(),),
            (DuelScenario("policy-duel", 15.0, max_ticks=30),),
            (3,),
        )
        weights = UtilityPolicyWeights(control=1.25, setup=0.8)

        first = evaluator(weights)
        second = evaluator(weights)

        self.assertEqual(first, second)
        self.assertEqual(2, first.rollout_count)
        self.assertEqual(weights.policy_digest, first.weights.policy_digest)
        self.assertEqual(64, len(first.evidence_digest))

    def test_policy_evidence_ignores_loadout_labels(self) -> None:
        controlled = assassin_loadout()
        opponent = warlock_loadout()
        first = UtilityPolicyLeagueEvaluator(
            self.ruleset,
            controlled,
            (opponent,),
            (DuelScenario("policy-duel", 15.0, max_ticks=20),),
            (7,),
        )(UtilityPolicyWeights())
        second = UtilityPolicyLeagueEvaluator(
            self.ruleset,
            replace(
                controlled,
                loadout_id="renamed-controlled",
                display_name="Renamed Controlled",
            ),
            (
                replace(
                    opponent,
                    loadout_id="renamed-opponent",
                    display_name="Renamed Opponent",
                ),
            ),
            (DuelScenario("policy-duel", 15.0, max_ticks=20),),
            (7,),
        )(UtilityPolicyWeights())

        self.assertEqual(first, second)

    def test_diagonal_search_is_reproducible_and_keeps_baseline_candidate(self) -> None:
        evaluator = UtilityPolicyLeagueEvaluator(
            self.ruleset,
            assassin_loadout(),
            (warlock_loadout(),),
            (DuelScenario("policy-duel", 6.0, max_ticks=20),),
            (5,),
        )
        config = DiagonalPolicySearchConfig(
            generations=2,
            population_size=4,
            elite_count=2,
            seed=29,
            initial_sigma=0.2,
        )

        first = run_diagonal_policy_search(evaluator, config=config)
        second = run_diagonal_policy_search(evaluator, config=config)

        self.assertEqual(first, second)
        self.assertEqual(9, first.evaluated_policy_count)
        self.assertGreaterEqual(first.best.quality, first.initial.quality)
        self.assertEqual(2, len(first.generations))
        self.assertEqual(
            "deterministic_diagonal_evolution_strategy_v1",
            first.as_dict()["algorithm"],
        )
        self.assertTrue(first.as_dict()["not_cma_es"])
        self.assertEqual(64, len(first.result_digest))


if __name__ == "__main__":
    unittest.main()
