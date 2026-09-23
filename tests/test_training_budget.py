from __future__ import annotations

import unittest

from shadowbane_lab.equipment import load_bundled_equipment_catalog
from shadowbane_lab.optimization import (
    LegalBuildCompileError,
    LegalBuildGenome,
    TrainingBudgetBackedLegalityGate,
    TrainingCostEvidence,
    load_bundled_training_budget_catalog,
)
from shadowbane_lab.progression import load_bundled_wonderbane_calculator_catalog


class TrainingBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.calculator = load_bundled_wonderbane_calculator_catalog()
        cls.equipment = load_bundled_equipment_catalog()
        cls.budgets = load_bundled_training_budget_catalog()
        cls.rogue_id = next(
            item.record_id
            for item in cls.calculator.base_classes
            if item.name.casefold() == "rogue"
        )
        cls.assassin_id = next(
            item.record_id
            for item in cls.calculator.promotions
            if item.name.casefold() == "assassin"
        )
        cls.irekei_id = next(
            item.record_id
            for item in cls.calculator.races
            if item.family.casefold() == "irekei"
        )
        cls.human_id = next(
            item.record_id
            for item in cls.calculator.races
            if item.family.casefold() == "human"
        )

    def genome(
        self,
        *,
        race_id: int | None = None,
        level: int = 59,
        skill_ranks: tuple[tuple[str, int], ...] = (),
        power_ranks: tuple[tuple[str, int], ...] = (),
    ) -> LegalBuildGenome:
        return LegalBuildGenome(
            genome_id="training-budget-test",
            display_name="Training Budget Test",
            race_id=self.irekei_id if race_id is None else race_id,
            base_class_id=self.rogue_id,
            promotion_id=self.assassin_id,
            level=level,
            move_speed=15.0,
            skill_ranks=skill_ranks,
            power_ranks=power_ranks,
        )

    def test_non_human_rogue_schedule_matches_sourced_breakpoints(self) -> None:
        race = self.calculator.race(self.irekei_id)
        profile = self.budgets.resolve(
            race_family=race.family,
            base_class_name="Rogue",
        )
        self.assertIsNotNone(profile)
        assert profile is not None

        self.assertEqual(36, profile.points_for_level(10))
        self.assertEqual(526, profile.points_for_level(59))
        self.assertEqual(588, profile.points_for_level(75))
        self.assertEqual(64, len(profile.profile_digest))

    def test_human_rogue_does_not_inherit_non_human_schedule(self) -> None:
        race = self.calculator.race(self.human_id)

        profile = self.budgets.resolve(
            race_family=race.family,
            base_class_name="Rogue",
        )
        audit = self.budgets.audit(
            race_family=race.family,
            base_class_name="Rogue",
            level=59,
            skill_ranks=(("unarmed_combat", 110),),
            power_ranks=(("power.example", 40),),
        )

        self.assertIsNone(profile)
        self.assertIsNone(audit.budget_points)
        self.assertIsNone(audit.lower_bound_remaining)
        self.assertFalse(audit.evidence_complete)

    def test_cost_audit_distinguishes_power_lower_bound_from_skill_unknown(self) -> None:
        race = self.calculator.race(self.irekei_id)
        audit = self.budgets.audit(
            race_family=race.family,
            base_class_name="Rogue",
            level=59,
            skill_ranks=(("unarmed_combat", 110),),
            power_ranks=(("power.one", 40), ("power.two", 12)),
        )

        self.assertEqual(526, audit.budget_points)
        self.assertEqual(52, audit.minimum_points_spent)
        self.assertEqual(474, audit.lower_bound_remaining)
        self.assertIsNone(audit.exact_points_spent)
        self.assertEqual(("unarmed_combat",), audit.unresolved_skill_cost_keys)
        power_costs = tuple(
            item for item in audit.selections if item.category == "power"
        )
        self.assertTrue(
            all(item.evidence is TrainingCostEvidence.LOWER_BOUND for item in power_costs)
        )

    def test_typed_gate_rejects_only_proven_lower_bound_overspend(self) -> None:
        gate = TrainingBudgetBackedLegalityGate(
            self.calculator,
            self.equipment,
            budgets=self.budgets,
        )
        legal = gate.audit(
            self.genome(
                power_ranks=(("power.one", 40), ("power.two", 12)),
            )
        )
        self.assertEqual(526, legal.known_power_training_budget)
        self.assertEqual(474, legal.power_training_remaining)
        self.assertEqual(
            "wonderbane.non-human.rogue.v1",
            legal.training_allocation.budget_profile_id,
        )
        self.assertIn("training_allocation", legal.as_dict())

        with self.assertRaisesRegex(
            LegalBuildCompileError,
            "require at least 527 training points",
        ):
            gate.validate(self.genome(power_ranks=(("power.too_expensive", 527),)))

        human = gate.audit(
            self.genome(
                race_id=self.human_id,
                power_ranks=(("power.unknown_human_cost", 527),),
            )
        )
        self.assertIsNone(human.known_power_training_budget)
        self.assertIsNone(human.training_allocation.budget_profile_id)


if __name__ == "__main__":
    unittest.main()
