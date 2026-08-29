import json
import unittest
from pathlib import Path

from shadowbane_lab.rollouts.open_builds import round_robin_open_duels
from shadowbane_lab.rollouts.packages import (
    PackageAssemblyError,
    PackageInventory,
    PackagePiece,
    assemble_package_loadout,
    generate_inventory_loadouts,
    load_package_inventory_text,
)
from shadowbane_lab.rollouts.ruleset import load_assassin_warlock_duel_ruleset

BACKSTAB = "shadowbane.assassin.backstab"
FADE = "shadowbane.assassin.fade"
INVISIBILITY = "shadowbane.assassin.invisibility"
MIND_STRIKE = "shadowbane.warlock.mind_strike"
SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"


class PackageAssemblyTests(unittest.TestCase):
    def test_requirements_are_cookie_cut_into_the_loadout(self) -> None:
        inventory = PackageInventory(
            inventory_id="owned",
            packages=(
                PackagePiece(
                    "body.melee",
                    "Melee body",
                    tags=("equipment.melee_weapon", "power.stalk"),
                    health_delta=50,
                ),
                PackagePiece(
                    "rune.stealth",
                    "Stealth rune",
                    action_keys=(FADE, INVISIBILITY),
                ),
                PackagePiece(
                    "rune.weapon-power",
                    "Weapon power rune",
                    action_keys=(BACKSTAB,),
                    requires=("body.melee", "rune.stealth"),
                ),
            ),
        )

        assembly = assemble_package_loadout(
            inventory,
            ("rune.weapon-power",),
            loadout_id="candidate",
            display_name="Candidate",
        )

        self.assertEqual(
            ("body.melee", "rune.stealth"),
            assembly.auto_added_requirement_ids,
        )
        self.assertEqual(
            {BACKSTAB, FADE, INVISIBILITY},
            set(assembly.loadout.action_keys),
        )
        self.assertIn("equipment.melee_weapon", assembly.loadout.tags)
        self.assertEqual(550, assembly.loadout.health)

    def test_conflicting_packages_are_rejected(self) -> None:
        inventory = PackageInventory(
            inventory_id="conflicts",
            packages=(
                PackagePiece(
                    "stance.a",
                    "Stance A",
                    conflicts=("stance.b",),
                ),
                PackagePiece("stance.b", "Stance B"),
            ),
        )

        with self.assertRaisesRegex(PackageAssemblyError, "conflicts"):
            assemble_package_loadout(
                inventory,
                ("stance.a", "stance.b"),
                loadout_id="invalid",
                display_name="Invalid",
            )

    def test_generation_is_reproducible_and_inventory_bounded(self) -> None:
        inventory = PackageInventory(
            inventory_id="toolbox",
            packages=(
                PackagePiece("a", "A", action_keys=(MIND_STRIKE,)),
                PackagePiece("b", "B", action_keys=(SHADOW_TOUCH,)),
                PackagePiece("c", "C", action_keys=(FADE,)),
                PackagePiece("d", "D", action_keys=(INVISIBILITY,)),
            ),
            selection_minimum=1,
            selection_maximum=3,
        )

        first = generate_inventory_loadouts(
            inventory,
            count=6,
            seed=17,
        )
        second = generate_inventory_loadouts(
            inventory,
            count=6,
            seed=17,
        )

        self.assertEqual(first, second)
        known = set(inventory.by_id)
        for assembly in first:
            self.assertTrue(set(assembly.selected_package_ids) <= known)
            self.assertTrue(assembly.loadout.action_keys)

    def test_example_inventory_generates_runnable_open_loadouts(self) -> None:
        source = Path("configs/primitive-package-inventory.example.json").read_text(
            encoding="utf-8"
        )
        inventory = load_package_inventory_text(source)
        assemblies = generate_inventory_loadouts(
            inventory,
            count=4,
            seed=9,
            minimum_packages=2,
            maximum_packages=4,
        )
        cells = round_robin_open_duels(
            load_assassin_warlock_duel_ruleset(),
            tuple(item.loadout for item in assemblies),
            starting_distances=(15.0,),
            seeds=(1,),
            max_ticks=30,
        )

        self.assertEqual(6, len(cells))
        self.assertTrue(all(cell.matches == 2 for cell in cells))

    def test_parser_keeps_source_labels_as_metadata(self) -> None:
        raw = {
            "schema_version": 1,
            "inventory_id": "labels",
            "packages": [
                {
                    "package_id": "owned.thing",
                    "display_name": "Owned Thing",
                    "action_keys": [MIND_STRIKE],
                    "metadata": {
                        "source_kind": "discipline-rune",
                        "original_name": "Whatever",
                    },
                }
            ],
        }

        inventory = load_package_inventory_text(json.dumps(raw))

        self.assertEqual(
            "discipline-rune",
            dict(inventory.packages[0].metadata)["source_kind"],
        )
        assembly = assemble_package_loadout(
            inventory,
            ("owned.thing",),
            loadout_id="labels.candidate",
            display_name="Labels candidate",
        )
        self.assertEqual((MIND_STRIKE,), assembly.loadout.action_keys)


if __name__ == "__main__":
    unittest.main()
