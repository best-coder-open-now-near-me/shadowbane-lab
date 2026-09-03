from __future__ import annotations

import unittest

from shadowbane_lab.optimization import (
    CalculatorAllocationSpace,
    LegalBuildGenome,
    genome_mechanical_digest,
)
from shadowbane_lab.progression import load_bundled_wonderbane_calculator_catalog
from shadowbane_lab.sim import DeterministicRandom


class CalculatorAllocationSpaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.calculator = load_bundled_wonderbane_calculator_catalog()
        cls.space = CalculatorAllocationSpace(cls.calculator)

    @staticmethod
    def genome() -> LegalBuildGenome:
        return LegalBuildGenome(
            genome_id="allocation-test",
            display_name="Allocation Test",
            race_id=2013,
            base_class_id=2502,
            promotion_id=2504,
            level=59,
            move_speed=15.0,
        )

    def test_spend_and_transfer_neighbors_are_calculator_authoritative(self) -> None:
        genome = self.genome()
        initial = self.space.evaluate(genome)
        self.assertGreater(initial.available_points, 0)

        spends = self.space.legal_neighbors(
            genome,
            include_spend=True,
            include_transfer=False,
        )
        self.assertGreater(len(spends), 0)
        self.assertTrue(all(item.operation == "spend" for item in spends))
        self.assertTrue(
            all(
                item.allocation.available_points == initial.available_points - 1
                for item in spends
            )
        )

        full = self.space.fill(genome, DeterministicRandom(7))
        full_receipt = self.space.evaluate(full)
        self.assertTrue(full_receipt.fully_allocated)
        transfers = self.space.legal_neighbors(
            full,
            include_spend=False,
            include_transfer=True,
        )
        self.assertGreater(len(transfers), 0)
        self.assertTrue(all(item.operation == "transfer" for item in transfers))
        self.assertTrue(
            all(
                item.allocation.trained_points == full_receipt.trained_points
                for item in transfers
            )
        )

    def test_distinct_variants_remain_fully_allocated_and_reproducible(self) -> None:
        full = self.space.fill(self.genome(), DeterministicRandom(13))

        first = self.space.distinct_variants(full, count=3)
        second = self.space.distinct_variants(full, count=3)

        first_digests = tuple(genome_mechanical_digest(item) for item in first)
        self.assertEqual(first_digests, tuple(genome_mechanical_digest(item) for item in second))
        self.assertEqual(3, len(set(first_digests)))
        self.assertTrue(all(self.space.evaluate(item).fully_allocated for item in first))

    def test_rune_repair_refunds_and_reuses_the_calculator_point_pool(self) -> None:
        full = self.space.fill(self.genome(), DeterministicRandom(23))
        initial = self.space.evaluate(full)
        selected = None
        selected_rune = None
        for rune in self.calculator.eligible_runes(
            race_id=full.race_id,
            base_class_id=full.base_class_id,
            promotion_id=full.promotion_id,
            level=full.level,
            trained_modifiers=full.trained_modifiers,
        ):
            if rune.cost <= 0:
                continue
            candidate = self.space.repair_runes(
                full,
                (rune.record_id,),
                DeterministicRandom(29),
            )
            if candidate is not None:
                selected = candidate
                selected_rune = rune
                break
        self.assertIsNotNone(selected)
        self.assertIsNotNone(selected_rune)
        assert selected is not None
        assert selected_rune is not None

        added = self.space.evaluate(selected)
        self.assertTrue(added.fully_allocated)
        self.assertEqual((selected_rune.record_id,), selected.rune_ids)
        self.assertEqual(initial.point_pool, added.trained_points + added.rune_cost)

        removed = self.space.repair_runes(
            selected,
            (),
            DeterministicRandom(31),
        )
        self.assertIsNotNone(removed)
        assert removed is not None
        removed_receipt = self.space.evaluate(removed)
        self.assertTrue(removed_receipt.fully_allocated)
        self.assertEqual(initial.point_pool, removed_receipt.trained_points)
        self.assertEqual(
            selected_rune.cost,
            removed_receipt.trained_points - added.trained_points,
        )


if __name__ == "__main__":
    unittest.main()
