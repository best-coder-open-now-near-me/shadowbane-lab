import json
import unittest
from importlib.resources import files

from shadowbane_lab.progression import (
    CatalogVariantStatus,
    CharacterSex,
    CoreBuildIdentity,
    CoverageStatus,
    GameCatalogLoadError,
    IllegalCoreBuildError,
    StatLine,
    load_game_catalog_text,
    load_shadowbane_legacy_catalog,
)


def bundled_source() -> dict:
    resource = files("shadowbane_lab.progression").joinpath(
        "data/shadowbane_legacy_catalog_v1.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


class GameCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_shadowbane_legacy_catalog()

    def test_bundled_catalog_loads_complete_legacy_identity_universe(self) -> None:
        self.assertEqual("shadowbane.legacy-build-catalog.v1", self.catalog.catalog_id)
        self.assertEqual("wonderbane", self.catalog.target_variant)
        self.assertEqual(CatalogVariantStatus.LEGACY_BASELINE, self.catalog.variant_status)
        self.assertEqual(12, len(self.catalog.races))
        self.assertEqual(4, len(self.catalog.base_classes))
        self.assertEqual(22, len(self.catalog.professions))
        self.assertEqual(47, len(self.catalog.disciplines))
        self.assertEqual(319, len(self.catalog.legal_core_builds()))

    def test_variant_and_mechanics_gaps_remain_machine_readable(self) -> None:
        self.assertEqual(
            CoverageStatus.COMPLETE,
            self.catalog.coverage_for("core_identity").status,
        )
        self.assertEqual(
            CoverageStatus.UNRESOLVED,
            self.catalog.coverage_for("wonderbane_variant").status,
        )
        self.assertEqual(
            CoverageStatus.PARTIAL,
            self.catalog.coverage_for("discipline_legality").status,
        )
        self.assertEqual(
            CoverageStatus.UNRESOLVED,
            self.catalog.coverage_for("combat_formulas").status,
        )

    def test_irekei_stats_and_racial_disciplines_match_pinned_source(self) -> None:
        irekei = self.catalog.race("irekei")

        self.assertEqual(15, irekei.creation_cost)
        self.assertEqual(StatLine(40, 55, 40, 45, 30), irekei.starting_attributes)
        self.assertEqual(StatLine(85, 130, 90, 110, 85), irekei.maximum_attributes)
        self.assertEqual(("blood_prophet", "sun_dancer"), irekei.racial_discipline_keys)
        self.assertEqual(("irekei",), self.catalog.discipline("sun_dancer").racial_access_keys)

    def test_legal_build_checks_all_four_identity_dimensions(self) -> None:
        legal = CoreBuildIdentity(
            race_key="aracoix",
            base_class_key="fighter",
            profession_key="warlock",
            sex=CharacterSex.MALE,
        )

        self.assertIs(legal, self.catalog.validate_core_build(legal))

        with self.assertRaisesRegex(IllegalCoreBuildError, "cannot select base class mage"):
            self.catalog.validate_core_build(
                CoreBuildIdentity(
                    race_key="aracoix",
                    base_class_key="mage",
                    profession_key="warlock",
                    sex=CharacterSex.MALE,
                )
            )
        with self.assertRaisesRegex(IllegalCoreBuildError, "does not allow sex female"):
            self.catalog.validate_core_build(
                CoreBuildIdentity(
                    race_key="aracoix",
                    base_class_key="fighter",
                    profession_key="warlock",
                    sex=CharacterSex.FEMALE,
                )
            )

    def test_race_and_profession_sex_restrictions_are_independent(self) -> None:
        with self.assertRaisesRegex(IllegalCoreBuildError, "Dwarf does not allow sex female"):
            self.catalog.validate_core_build(
                CoreBuildIdentity(
                    race_key="dwarf",
                    base_class_key="fighter",
                    profession_key="warrior",
                    sex=CharacterSex.FEMALE,
                )
            )
        self.catalog.validate_core_build(
            CoreBuildIdentity(
                race_key="elf",
                base_class_key="mage",
                profession_key="fury",
                sex=CharacterSex.FEMALE,
            )
        )

    def test_class_page_edges_admit_aelfborn_mage_wizard(self) -> None:
        build = CoreBuildIdentity(
            race_key="aelfborn",
            base_class_key="mage",
            profession_key="wizard",
            sex=CharacterSex.MALE,
        )

        self.catalog.validate_core_build(build)
        self.assertIn(build, self.catalog.legal_core_builds())

    def test_unknown_cross_reference_fails_closed(self) -> None:
        source = bundled_source()
        source["races"][0]["allowed_base_class_keys"].append("adventurer")

        with self.assertRaisesRegex(GameCatalogLoadError, "unknown keys: adventurer"):
            load_game_catalog_text(json.dumps(source))

    def test_inconsistent_racial_discipline_edge_fails_closed(self) -> None:
        source = bundled_source()
        sun_dancer = next(item for item in source["disciplines"] if item["key"] == "sun_dancer")
        sun_dancer["racial_access_keys"] = []

        with self.assertRaisesRegex(GameCatalogLoadError, "racial access declarations"):
            load_game_catalog_text(json.dumps(source))

    def test_invalid_variant_status_is_reported_as_load_error(self) -> None:
        source = bundled_source()
        source["variant_status"] = "probably-current"

        with self.assertRaises(GameCatalogLoadError):
            load_game_catalog_text(json.dumps(source))


if __name__ == "__main__":
    unittest.main()
