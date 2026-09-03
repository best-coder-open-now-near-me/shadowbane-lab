from __future__ import annotations

import hashlib
import json
import unittest

from shadowbane_lab.equipment import load_bundled_equipment_catalog
from shadowbane_lab.optimization import (
    ArchiveAdmission,
    BuildCompilationStatus,
    DescriptorAxis,
    EquipmentSelection,
    LegalBuildCompileError,
    LegalBuildCompilePolicy,
    LegalBuildCompiler,
    LegalBuildGenome,
    MapElitesArchive,
    MapElitesError,
    MapElitesEvaluation,
    MapElitesInsertStatus,
    SelectedAffix,
    load_legal_build_genome_text,
    run_map_elites,
)
from shadowbane_lab.progression import (
    StatLine,
    load_bundled_wonderbane_calculator_catalog,
)
from shadowbane_lab.rollouts.ruleset import load_wonderbane_guide_duel_ruleset
from shadowbane_lab.sim import DeterministicRandom


def _digest(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _genome(**changes) -> LegalBuildGenome:
    values = {
        "genome_id": "irekei-assassin-59",
        "display_name": "Irekei Assassin 59",
        "race_id": 2013,
        "base_class_id": 2502,
        "promotion_id": 2504,
        "level": 59,
        "move_speed": 15.0,
    }
    values.update(changes)
    return LegalBuildGenome(**values)


class LegalBuildCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.calculator = load_bundled_wonderbane_calculator_catalog()
        cls.equipment = load_bundled_equipment_catalog()

    def compiler(
        self,
        *,
        policy: LegalBuildCompilePolicy = LegalBuildCompilePolicy(),
        with_ruleset: bool = False,
    ) -> LegalBuildCompiler:
        ruleset = (
            load_wonderbane_guide_duel_ruleset()
            if with_ruleset
            else None
        )
        return LegalBuildCompiler(
            self.calculator,
            self.equipment,
            ruleset=ruleset,
            policy=policy,
        )

    def test_calculator_legal_chassis_compiles_without_mechanics_guessing(self) -> None:
        compiler = self.compiler()

        first = compiler.compile(_genome())
        second = compiler.compile(_genome())

        self.assertEqual(BuildCompilationStatus.CHASSIS_VERIFIED, first.status)
        self.assertEqual(("ruleset.not_supplied",), first.coverage.unresolved)
        self.assertFalse(first.strict_archive_eligible)
        self.assertEqual("assassin", first.character_build.profession)
        self.assertEqual(first.calculator_output.health, first.view.body.health)
        self.assertEqual(first.calculator_output.mana, first.view.body.mana)
        self.assertEqual(first.calculator_output.stamina, first.view.body.stamina)
        self.assertEqual(first.compilation_digest, second.compilation_digest)
        self.assertIn("calculator.race.2013", first.view.selected_package_ids)
        self.assertIn("calculator.base_class.2502", first.view.selected_package_ids)
        self.assertIn("calculator.promotion.2504", first.view.selected_package_ids)

    def test_invalid_promotion_and_attribute_overspend_fail_closed(self) -> None:
        compiler = self.compiler()

        with self.assertRaisesRegex(LegalBuildCompileError, "calculator rejected"):
            compiler.compile(_genome(base_class_id=2500))
        with self.assertRaisesRegex(LegalBuildCompileError, "calculator rejected"):
            compiler.compile(
                _genome(trained_modifiers=StatLine(1_000, 1_000, 1_000, 1_000, 1_000))
            )

    def test_equipment_is_candidate_only_until_flags_and_effects_are_resolved(self) -> None:
        route = self.equipment.routes[0]
        genome = _genome(
            equipment=(EquipmentSelection("body", route.item_id),),
        )

        result = self.compiler().compile(genome)

        self.assertEqual(BuildCompilationStatus.SOURCE_CANDIDATE, result.status)
        self.assertFalse(result.strict_archive_eligible)
        unresolved = set(result.coverage.unresolved)
        prefix = f"equipment.body.{route.item_id}"
        self.assertIn(f"{prefix}.slot_semantics_unverified", unresolved)
        self.assertIn(f"{prefix}.base_values_not_applied", unresolved)

    def test_candidate_equipment_values_require_explicit_policy(self) -> None:
        route = self.equipment.routes[0]
        policy = LegalBuildCompilePolicy(apply_candidate_equipment_values=True)

        result = self.compiler(policy=policy).compile(
            _genome(equipment=(EquipmentSelection("body", route.item_id),))
        )

        self.assertEqual(BuildCompilationStatus.SOURCE_CANDIDATE, result.status)
        self.assertTrue(result.coverage.candidate_equipment_values_applied)
        self.assertIn(
            "equipment.candidate_values.body",
            result.coverage.accepted_assumptions,
        )

    def test_unknown_affix_and_strict_requirement_are_rejected(self) -> None:
        route = self.equipment.routes[0]
        invalid = EquipmentSelection(
            "body",
            route.item_id,
            prefix=SelectedAffix(999_999_999, "not-a-real-affix"),
        )
        with self.assertRaisesRegex(LegalBuildCompileError, "unknown affix"):
            self.compiler().compile(_genome(equipment=(invalid,)))

        with self.assertRaisesRegex(LegalBuildCompileError, "not strict simulation-ready"):
            self.compiler(
                policy=LegalBuildCompilePolicy(require_simulation_ready=True)
            ).compile(_genome())

    def test_ruleset_overrides_are_visible_instead_of_becoming_strict(self) -> None:
        result = self.compiler(
            with_ruleset=True,
            policy=LegalBuildCompilePolicy(allow_ruleset_overrides=True),
        ).compile(_genome())

        self.assertEqual(BuildCompilationStatus.SOURCE_CANDIDATE, result.status)
        self.assertGreater(result.coverage.requested_action_count, 0)
        self.assertEqual(
            result.coverage.requested_action_count,
            result.coverage.executable_action_count,
        )
        self.assertTrue(
            any(
                assumption.startswith("ruleset.override.")
                for assumption in result.coverage.accepted_assumptions
            )
        )

    def test_attribute_mutation_is_deterministic_and_remains_legal(self) -> None:
        compiler = self.compiler()
        parent = _genome(trained_modifiers=StatLine(1, 1, 1, 1, 1))

        first = compiler.mutate_attributes(parent, DeterministicRandom(17))
        second = compiler.mutate_attributes(parent, DeterministicRandom(17))

        self.assertEqual(first.genome_digest, second.genome_digest)
        self.assertEqual(
            parent.trained_modifiers.total,
            first.trained_modifiers.total,
        )
        compiler.compile(first)

    def test_genome_json_round_trip_and_unknown_fields(self) -> None:
        genome = _genome(trained_modifiers=StatLine(1, 2, 3, 4, 5))

        decoded = load_legal_build_genome_text(json.dumps(genome.as_dict()))

        self.assertEqual(genome, decoded)
        source = genome.as_dict()
        source["unexpected"] = True
        with self.assertRaisesRegex(LegalBuildCompileError, "unknown fields"):
            load_legal_build_genome_text(json.dumps(source))


class MapElitesArchiveTests(unittest.TestCase):
    def evaluation(
        self,
        candidate: str,
        quality: float,
        feature: float,
        *,
        admission: ArchiveAdmission = ArchiveAdmission.STRICT,
    ) -> MapElitesEvaluation:
        return MapElitesEvaluation(
            candidate_digest=_digest(candidate),
            quality=quality,
            admission=admission,
            features=(("durability", feature),),
            metrics=(("wins", max(0.0, quality)),),
        )

    def test_descriptor_boundaries_and_replacement_are_deterministic(self) -> None:
        axis = DescriptorAxis("durability", (100.0, 200.0))
        archive = MapElitesArchive[str]((axis,))
        self.assertEqual((0, 1, 2), tuple(axis.locate(value) for value in (99, 100, 200)))

        first = self.evaluation("first", 2.0, 150.0)
        weaker = self.evaluation("weaker", 1.0, 175.0)
        stronger = self.evaluation("stronger", 3.0, 175.0)

        self.assertEqual(
            MapElitesInsertStatus.ADDED,
            archive.insert("first", first, candidate_digest=_digest("first")),
        )
        self.assertEqual(
            MapElitesInsertStatus.REJECTED_NOT_BETTER,
            archive.insert("weaker", weaker, candidate_digest=_digest("weaker")),
        )
        self.assertEqual(
            MapElitesInsertStatus.REPLACED,
            archive.insert("stronger", stronger, candidate_digest=_digest("stronger")),
        )
        self.assertEqual(_digest("stronger"), archive.best.evaluation.candidate_digest)

    def test_strict_archive_rejects_candidate_grade_mechanics(self) -> None:
        archive = MapElitesArchive[str](
            (DescriptorAxis("durability", (100.0,)),),
            required_admission=ArchiveAdmission.STRICT,
        )
        evaluation = self.evaluation(
            "candidate",
            10.0,
            150.0,
            admission=ArchiveAdmission.CANDIDATE,
        )

        result = archive.insert(
            "candidate",
            evaluation,
            candidate_digest=_digest("candidate"),
        )

        self.assertEqual(MapElitesInsertStatus.REJECTED_ADMISSION, result)
        self.assertEqual(0, archive.cell_count)

    def test_digest_and_descriptor_mismatches_fail_closed(self) -> None:
        archive = MapElitesArchive[str]((DescriptorAxis("durability", (100.0,)),))
        evaluation = self.evaluation("candidate", 1.0, 50.0)

        with self.assertRaisesRegex(MapElitesError, "does not match"):
            archive.insert("candidate", evaluation, candidate_digest=_digest("other"))
        incomplete = MapElitesEvaluation(
            candidate_digest=_digest("candidate"),
            quality=1.0,
            admission=ArchiveAdmission.STRICT,
            features=(("range", 10.0),),
        )
        with self.assertRaisesRegex(MapElitesError, "do not match archive axes"):
            archive.insert(
                "candidate",
                incomplete,
                candidate_digest=_digest("candidate"),
            )

    def test_search_repeats_exactly_for_the_same_seed(self) -> None:
        def evaluate(candidate: int) -> MapElitesEvaluation:
            return MapElitesEvaluation(
                candidate_digest=_digest(candidate),
                quality=float(candidate),
                admission=ArchiveAdmission.STRICT,
                features=(("style", float(candidate % 3)),),
            )

        def mutate(candidate: int, random: DeterministicRandom) -> int:
            return candidate + 1 + random.randbelow(4)

        def run():
            archive = MapElitesArchive[int](
                (DescriptorAxis("style", (0.5, 1.5)),),
                required_admission=ArchiveAdmission.STRICT,
            )
            return run_map_elites(
                (0, 1),
                archive=archive,
                iterations=30,
                seed=99,
                candidate_digest=_digest,
                evaluate=evaluate,
                mutate=mutate,
            )

        first = run()
        second = run()

        self.assertEqual(first.archive.archive_digest, second.archive.archive_digest)
        self.assertEqual(first.insertion_counts, second.insertion_counts)
        self.assertGreater(first.archive.cell_count, 0)
        self.assertEqual(30, first.iterations)


if __name__ == "__main__":
    unittest.main()
