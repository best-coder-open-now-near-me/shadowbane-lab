import unittest

from shadowbane_lab.equipment.crafting_assessment import (
    assess_native_crafting_roll,
    compact_affix_token,
)
from shadowbane_lab.equipment.rolling_policy import RollDisposition

BUILD = "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87"


def result(prefix=0, suffix=419992475):
    return {
        "schema_version": 2, "record_type": "crafting_message",
        "direction": "server_to_client", "executable_sha256": BUILD,
        "message": {
            "action_id": 8, "prefix_token": prefix, "suffix_token": suffix,
            "error_code": 0, "roll": {
                "template_id": 26990, "seconds_remaining": 0,
                "in_progress": 0, "complete_flag": 1,
            },
        },
    }


class CraftingAssessmentTests(unittest.TestCase):
    def test_definition_hashes_match_native_parent_and_components(self):
        for identifier, expected in (
            ("SUF-123", 419992475), ("SUF-143", 423138203), ("PRE-028", 428679032),
            ("SUF-123A", 487101323), ("SUF-123B", 285774731),
            ("PRE-028A", 495787880), ("PRE-028B", 294461288),
        ):
            self.assertEqual(expected, compact_affix_token(identifier))
        for invalid in ("OfGenius", "suf-123", "SUF-1234", "SUF-123AB", "INV-123", ""):
            with self.assertRaises(ValueError):
                compact_affix_token(invalid)

    def test_genius_is_tier_three_but_assessment_never_admits_a_command(self):
        assessment = assess_native_crafting_roll(result())
        self.assertEqual(RollDisposition.KEEP, assessment.disposition)
        self.assertEqual("SUF-123", assessment.suffix.identifier)
        self.assertEqual("of Genius", assessment.suffix.name)
        self.assertEqual(3, assessment.suffix.tier)
        self.assertEqual(0, assessment.prefix.tier)
        self.assertFalse(assessment.command_admitted)

    def test_unlisted_affixes_and_components_remain_unknown_and_kept(self):
        for prefix, suffix in ((428679032, 423138203), (0, 487101323), (1234, 419992475)):
            assessment = assess_native_crafting_roll(result(prefix, suffix))
            self.assertEqual(RollDisposition.KEEP, assessment.disposition)
            self.assertEqual("unknown_affix_preserved", assessment.reason)
        assessment = assess_native_crafting_roll(result(428679032, 423138203))
        self.assertEqual("Taripontor", assessment.prefix.name)
        self.assertIsNone(assessment.prefix.tier)
        self.assertEqual("of Cruelty", assessment.suffix.name)
        self.assertIsNone(assessment.suffix.tier)

    def test_other_build_or_recipe_never_inherits_qualification(self):
        for field in ("build", "recipe"):
            record = result()
            if field == "build":
                record["executable_sha256"] = "0" * 64
            else:
                record["message"]["roll"]["template_id"] = 1
            self.assertIsNone(assess_native_crafting_roll(record).suffix.tier)

    def test_cooking_errors_and_conflicting_completion_wait(self):
        for progress, complete, seconds, error in (
            (1, 0, 599, 0), (1, 1, 0, 0), (0, 0, 0, 0), (0, 1, 1, 0), (0, 1, 0, 1),
        ):
            record = result(0, 0)
            record["message"]["error_code"] = error
            record["message"]["roll"].update(
                in_progress=progress, complete_flag=complete, seconds_remaining=seconds
            )
            assessment = assess_native_crafting_roll(record)
            self.assertEqual(RollDisposition.WAIT, assessment.disposition)
            self.assertIsNone(assessment.prefix.tier)

    def test_invalid_or_wrong_direction_records_cannot_be_assessed(self):
        for field, value in (
            ("schema_version", 1), ("direction", "client_to_server"),
            ("record_type", "session_start"),
        ):
            record = result()
            record[field] = value
            with self.assertRaises(ValueError):
                assess_native_crafting_roll(record)
        record = result()
        record["message"]["prefix_token"] = True
        with self.assertRaises(ValueError):
            assess_native_crafting_roll(record)
