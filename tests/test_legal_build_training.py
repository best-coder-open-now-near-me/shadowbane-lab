from __future__ import annotations

import unittest

from shadowbane_lab.equipment import load_bundled_equipment_catalog
from shadowbane_lab.optimization import (
    CatalogBackedLegalityGate,
    EquipmentSelection,
    LegalBuildCompileError,
    LegalBuildGenome,
)
from shadowbane_lab.optimization.irekei_assassin import (
    IrekeiAssassinSearchConfig,
    run_irekei_assassin_search,
)
from shadowbane_lab.progression import (
    load_bundled_wonderbane_calculator_catalog,
)


class CatalogBackedLegalityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.calculator = load_bundled_wonderbane_calculator_catalog()
        cls.equipment = load_bundled_equipment_catalog()
        cls.gate = CatalogBackedLegalityGate(cls.calculator, cls.equipment)

    @staticmethod
    def genome(**changes) -> LegalBuildGenome:
        values = {
            "genome_id": "gate-test",
            "display_name": "Gate Test",
            "race_id": 2013,
            "base_class_id": 2502,
            "promotion_id": 2504,
            "level": 59,
            "move_speed": 15.0,
            "equipment": (EquipmentSelection("main_hand", 29390),),
        }
        values.update(changes)
        return LegalBuildGenome(**values)

    def test_named_item_skill_requirement_is_enforced(self) -> None:
        with self.assertRaisesRegex(
            LegalBuildCompileError,
            "requires Unarmed Combat 110",
        ):
            self.gate.validate(self.genome())

        audit = self.gate.validate(
            self.genome(skill_ranks=(("unarmed_combat", 110),))
        )

        self.assertEqual(1, len(audit.equipment_skill_requirements))
        requirement = audit.equipment_skill_requirements[0]
        self.assertTrue(requirement.satisfied)
        self.assertEqual("unarmed_combat", requirement.semantic_skill_key)
        self.assertEqual(110, requirement.observed_rank)
        self.assertGreaterEqual(audit.opaque_item_requirement_count, 1)

    def test_power_rank_lower_bound_cannot_exceed_rogue_pool(self) -> None:
        with self.assertRaisesRegex(
            LegalBuildCompileError,
            "supplies only 526",
        ):
            self.gate.validate(
                self.genome(
                    skill_ranks=(("unarmed_combat", 110),),
                    power_ranks=(
                        ("power.one", 300),
                        ("power.two", 300),
                    ),
                )
            )

        audit = self.gate.validate(
            self.genome(
                skill_ranks=(("unarmed_combat", 110),),
                power_ranks=(("power.one", 40),),
            )
        )
        self.assertEqual(526, audit.known_power_training_budget)
        self.assertEqual(486, audit.power_training_remaining)


class IrekeiAssassinTrainingTests(unittest.TestCase):
    def test_small_search_runs_real_compiler_and_lifecycle_deterministically(self) -> None:
        config = IrekeiAssassinSearchConfig(
            iterations=1,
            mutation_seed=11,
            rollout_seeds=(3,),
            starting_distances=(6.0,),
            max_ticks=30,
            equipment_pool_size=1,
        )

        first = run_irekei_assassin_search(config)
        second = run_irekei_assassin_search(config)

        self.assertEqual(
            first.run.archive.archive_digest,
            second.run.archive.archive_digest,
        )
        self.assertEqual(first.run.insertion_counts, second.run.insertion_counts)
        self.assertEqual(3, first.run.initial_candidate_count)
        self.assertGreater(first.run.evaluated_candidate_count, 0)
        self.assertGreater(first.run.archive.cell_count, 0)
        self.assertEqual(2, len(first.opponents))
        for cell in first.run.archive.cells:
            self.assertIsNotNone(cell.evaluation.evidence_digest)
            metrics = dict(cell.evaluation.metrics)
            self.assertEqual(4.0, metrics["rollout_count"])
            self.assertIn("win_rate", metrics)
            self.assertIn("mean_ticks", metrics)
        best = first.run.archive.best
        self.assertIsNotNone(best)
        assert best is not None
        self.assertEqual(
            best.evaluation.candidate_digest,
            best.candidate.genome_digest,
        )

    def test_report_keeps_candidate_evidence_boundary_explicit(self) -> None:
        report = run_irekei_assassin_search(
            IrekeiAssassinSearchConfig(
                iterations=0,
                rollout_seeds=(1,),
                starting_distances=(15.0,),
                max_ticks=10,
                equipment_pool_size=1,
            )
        )
        payload = report.as_dict()

        self.assertEqual(
            "wonderbane.irekei-assassin-map-elites.v1",
            payload["experiment"],
        )
        self.assertEqual("candidate", payload["run"]["archive"]["required_admission"])
        self.assertTrue(
            any("candidate-grade" in item for item in payload["caveats"])
        )
        self.assertTrue(
            all(
                item["equipment"][0]["item_id"] == 29390
                for item in payload["initial_genomes"]
            )
        )


if __name__ == "__main__":
    unittest.main()
