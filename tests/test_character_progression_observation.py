from __future__ import annotations

import unittest

from shadowbane_lab.client_observation import (
    ARC_HUD_CHARACTER_DATA_FIELDS,
    CharacterProgressionObservation,
    EquippedItemObservation,
    TrainedRankObservation,
)
from shadowbane_lab.progression import StatLine


class CharacterProgressionObservationTests(unittest.TestCase):
    def test_snapshot_derives_ruleset_build_from_known_power_mapping(self) -> None:
        observation = CharacterProgressionObservation(
            profile_id="wonderbane-test",
            sequence=12,
            race="Irekei",
            base_class="Rogue",
            profession="Assassin",
            level=59,
            stats=StatLine(45, 150, 95, 110, 50),
            stat_caps=StatLine(85, 150, 95, 110, 85),
            unspent_ability_points=0,
            unspent_training_points=526,
            skills=(TrainedRankObservation("shadowmastery", "Shadowmastery", 97),),
            powers=(
                TrainedRankObservation("shadow_touch", "Shadow Touch", 40),
                TrainedRankObservation("poison_blade", "Poison Blade", 20),
            ),
            discipline_keys=("sun_dancer", "saboteur"),
            equipment=(EquippedItemObservation("right_hand", "Doomfist", "unarmed"),),
        )
        build = observation.ruleset_build({"shadow_touch": "shadowbane.assassin.shadow_touch"})
        self.assertEqual("assassin", build.profession)
        self.assertEqual(59, build.level)
        self.assertEqual(97, build.skill_rank("shadowmastery"))
        self.assertEqual(
            40,
            build.power_rank("shadowbane.assassin.shadow_touch"),
        )
        self.assertIsNone(build.power_rank("poison_blade"))

    def test_arc_hud_data_fields_are_semantic_not_pixel_coordinates(self) -> None:
        self.assertEqual(1, ARC_HUD_CHARACTER_DATA_FIELDS["strength"])
        self.assertEqual(33, ARC_HUD_CHARACTER_DATA_FIELDS["ability_points"])
        self.assertEqual(38, ARC_HUD_CHARACTER_DATA_FIELDS["intelligence_quality_label"])
        self.assertEqual(149, ARC_HUD_CHARACTER_DATA_FIELDS["skill_list"])
        self.assertEqual(408, ARC_HUD_CHARACTER_DATA_FIELDS["skill_rank"])

    def test_duplicate_observed_power_key_is_rejected(self) -> None:
        duplicate = TrainedRankObservation("shadow_touch", "Shadow Touch", 40)
        with self.assertRaisesRegex(ValueError, "powers must not contain duplicate"):
            CharacterProgressionObservation(
                profile_id="wonderbane-test",
                sequence=1,
                race="Irekei",
                base_class="Rogue",
                profession="Assassin",
                level=59,
                stats=StatLine(45, 65, 45, 110, 25),
                stat_caps=StatLine(85, 130, 90, 110, 85),
                unspent_ability_points=135,
                unspent_training_points=526,
                skills=(),
                powers=(duplicate, duplicate),
                discipline_keys=(),
                equipment=(),
            )


if __name__ == "__main__":
    unittest.main()
