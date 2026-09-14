import copy
import json
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from shadowbane_lab.equipment.affix_reference import (
    import_field_reference_affixes,
    load_bundled_affix_reference,
    parse_affix_reference,
)
from shadowbane_lab.equipment.model import AffixPosition


class AffixReferenceTests(unittest.TestCase):
    def test_supplied_tiers_and_equipment_restrictions_are_preserved(self):
        reference = load_bundled_affix_reference()
        self.assertEqual(112, len(reference.by_tier(3)))
        self.assertEqual(50, len(reference.by_tier(4)))
        self.assertEqual(9, len(reference.by_tier(2)))
        primal, = reference.lookup(" primal ", position=AffixPosition.PREFIX, tier=3)
        self.assertIn("Wand/scepter", primal.equipment)
        self.assertEqual("Historical / emulator table", primal.evidence)
        self.assertTrue(primal.formula_resource_cost)
        # Generic source categories must not silently turn into scepter eligibility.
        adamant, = reference.lookup("Adamant", position=AffixPosition.PREFIX, tier=3)
        self.assertEqual(("Weapons (source category)",), adamant.equipment)

    def test_same_name_different_tiers_is_not_collapsed(self):
        reference = load_bundled_affix_reference()
        matches = reference.lookup("OF THORNS", position=AffixPosition.SUFFIX)
        self.assertEqual({3, 4}, {row.tier for row in matches})
        self.assertEqual(2, len({row.effects for row in matches}))
        self.assertEqual((), reference.lookup("Thorns", position=AffixPosition.SUFFIX))
        self.assertEqual((), reference.lookup("of Thorns", position=AffixPosition.PREFIX))

    def test_import_ignores_executable_scripts_and_preserves_exact_rows(self):
        data = json.loads(files("shadowbane_lab.equipment").joinpath(
            "data", "wonderbane_affix_reference_v3_7.json"
        ).read_text(encoding="utf-8"))
        document = {"edition": data["edition"], "data": {"affixes": data["affixes"]}}
        block = '<script id="reference-data" type="application/json">'
        html = '<script>throw new Error("must not execute");</script>' + block
        html += json.dumps(document) + "</script>"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reference.html"
            path.write_text(html, encoding="utf-8")
            imported = import_field_reference_affixes(path)
            self.assertEqual(data["affixes"], imported["affixes"])
            self.assertEqual("reference.html", imported["source_document"])
            path.write_text(html + html, encoding="utf-8")
            with self.assertRaises(ValueError):
                import_field_reference_affixes(path)

    def test_invalid_tiers_and_duplicate_rows_are_rejected(self):
        source = json.loads(files("shadowbane_lab.equipment").joinpath(
            "data", "wonderbane_affix_reference_v3_7.json"
        ).read_text(encoding="utf-8"))
        for tier in (True, 0, 5, "3"):
            data = copy.deepcopy(source)
            data["affixes"][0]["Tier"] = tier
            with self.assertRaises(ValueError):
                parse_affix_reference(data)
        source["affixes"].append(source["affixes"][0])
        with self.assertRaises(ValueError):
            parse_affix_reference(source)
