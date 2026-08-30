import unittest
from pathlib import Path

from shadowbane_lab.composition import (
    CompositionFormatError,
    dump_build_blueprint,
    dump_source_package_catalog,
    load_build_blueprint,
    load_build_blueprint_text,
    load_source_package_catalog,
    load_source_package_catalog_text,
    resolve_build_blueprint,
)

ROOT = Path(__file__).resolve().parents[1]


class CompositionIoTests(unittest.TestCase):
    def test_example_catalog_and_blueprint_resolve_end_to_end(self) -> None:
        catalog = load_source_package_catalog(
            ROOT / "configs" / "source-package-catalog.example.json"
        )
        blueprint = load_build_blueprint(ROOT / "configs" / "build-blueprint.example.json")

        view = resolve_build_blueprint(
            catalog,
            blueprint,
            available_action_keys=frozenset(
                {
                    "action.sprint",
                    "attack.basic",
                    "power.backstab",
                    "power.shadow_touch",
                }
            ),
            available_persistent_trigger_keys=frozenset({"trigger.example_weapon_proc"}),
        )

        self.assertEqual(
            (
                "example.base.agile",
                "example.weapon.fast-main-hand",
            ),
            view.auto_added_requirement_ids,
        )
        self.assertEqual(480.0, view.body.health)
        self.assertEqual(360.0, view.body.mana)
        self.assertEqual(220.0, view.body.stamina)
        self.assertEqual(16.0, view.body.move_speed)
        self.assertEqual(995.0, dict(view.scalars)["defense"])
        self.assertEqual(162.0, dict(view.attributes)["dexterity"])
        self.assertEqual((), view.unresolved_training_keys)
        self.assertEqual(1.0, view.coverage_fraction)

    def test_catalog_round_trip_is_canonical(self) -> None:
        catalog = load_source_package_catalog(
            ROOT / "configs" / "source-package-catalog.example.json"
        )
        dumped = dump_source_package_catalog(catalog)
        reloaded = load_source_package_catalog_text(dumped)

        self.assertEqual(dumped, dump_source_package_catalog(reloaded))

    def test_blueprint_round_trip_is_canonical(self) -> None:
        blueprint = load_build_blueprint(ROOT / "configs" / "build-blueprint.example.json")
        dumped = dump_build_blueprint(blueprint)
        reloaded = load_build_blueprint_text(dumped)

        self.assertEqual(dumped, dump_build_blueprint(reloaded))

    def test_unknown_package_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(CompositionFormatError, "kind is unknown"):
            load_source_package_catalog_text(
                """
                {
                  "schema_version": 1,
                  "catalog_id": "invalid",
                  "slot_limits": {},
                  "packages": [
                    {
                      "package_id": "bad",
                      "display_name": "Bad",
                      "kind": "not-a-kind",
                      "grants": {}
                    }
                  ]
                }
                """
            )

    def test_schema_version_is_required(self) -> None:
        with self.assertRaisesRegex(CompositionFormatError, "schema_version 1"):
            load_build_blueprint_text(
                '{"schema_version": 2, "blueprint_id": "x", "display_name": "X"}'
            )


if __name__ == "__main__":
    unittest.main()
