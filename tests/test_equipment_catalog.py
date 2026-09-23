from __future__ import annotations

import json
import unittest

from shadowbane_lab.equipment import (
    AffixChoice,
    AffixPosition,
    EquipmentCatalogLoadError,
    load_bundled_equipment_catalog,
    load_equipment_catalog_text,
)
from shadowbane_lab.equipment.importer import _sql_rows


class EquipmentCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_bundled_equipment_catalog()

    def test_bundled_catalog_preserves_current_and_candidate_boundaries(self) -> None:
        counts = self.catalog.coverage["counts"]
        self.assertEqual(3253, counts["base_items"])
        self.assertEqual(3195, counts["base_item_names_exactly_matched"])
        self.assertEqual(327, counts["current_prefix_names"])
        self.assertEqual(294, counts["current_suffix_names"])
        self.assertEqual(746, counts["modifiers"])
        self.assertEqual("historical_candidate", self.catalog.coverage["base_item_values"])
        self.assertEqual("historical_candidate", self.catalog.coverage["affix_values"])
        self.assertEqual(327, len(self.catalog.current_affix_names(AffixPosition.PREFIX)))
        self.assertEqual(294, len(self.catalog.current_affix_names(AffixPosition.SUFFIX)))

    def test_current_archive_table_alignment_is_explicit(self) -> None:
        alignment = self.catalog.coverage["table_alignment"]
        self.assertEqual([], alignment["general"]["missing_historical_ids"])
        self.assertEqual([], alignment["modifier_type"]["missing_historical_ids"])
        self.assertEqual([314], alignment["item"]["missing_historical_ids"])
        self.assertEqual(
            [247, 248, 249, 250, 3000, 3001, 3002, 3003],
            alignment["modifier"]["missing_historical_ids"],
        )

    def test_rhakanakar_base_stats_are_available_but_requirements_remain_opaque(self) -> None:
        item = self.catalog.item(29390)
        self.assertEqual("Rha'khanakar", item.name)
        self.assertTrue(item.current_name_verified)
        self.assertEqual("Unarmed Combat", item.skill_required)
        self.assertEqual(110, item.skill_percent_required)
        self.assertEqual((4, 16), (item.minimum_damage, item.maximum_damage))
        self.assertEqual(20.0, item.speed)
        self.assertEqual(1, len(item.requirements))
        self.assertEqual(1479762603, item.requirements[0].token)

    def test_affix_route_validates_a_legal_pair_and_rejects_unknown_choice(self) -> None:
        route = self.catalog.routes[0]
        prefixes = self.catalog.choices_for(route.item_id, AffixPosition.PREFIX)
        suffixes = self.catalog.choices_for(route.item_id, AffixPosition.SUFFIX)
        self.assertTrue(prefixes)
        self.assertTrue(suffixes)
        self.assertTrue(
            self.catalog.is_valid_affix_pair(
                route.item_id,
                prefix=prefixes[0].choice,
                suffix=suffixes[0].choice,
            )
        )
        self.assertFalse(
            self.catalog.is_valid_affix_pair(
                route.item_id,
                prefix=AffixChoice(999999, "not-a-real-affix"),
            )
        )

    def test_loader_rejects_unknown_schema(self) -> None:
        with self.assertRaisesRegex(EquipmentCatalogLoadError, "unsupported"):
            load_equipment_catalog_text(json.dumps({"schema_version": 2}))


class EquipmentImporterTests(unittest.TestCase):
    def test_mysql_value_parser_handles_apostrophes_nulls_and_decimals(self) -> None:
        sql = "INSERT INTO `sample` VALUES (1,'Relgor\\'s Elixir',NULL,22.5);"
        self.assertEqual([(1, "Relgor's Elixir", None, 22.5)], _sql_rows(sql, "sample"))


if __name__ == "__main__":
    unittest.main()
