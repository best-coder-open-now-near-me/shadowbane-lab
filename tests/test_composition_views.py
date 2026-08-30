import unittest

from shadowbane_lab.composition import (
    BodyDelta,
    BodyValues,
    BuildBlueprint,
    BuildResolutionError,
    ResolvedScenarioView,
    ScenarioOverlay,
    ScenarioSlotView,
    SimulationCaseView,
    SimulationParticipantView,
    SourcePackage,
    SourcePackageCatalog,
    SourcePackageKind,
    build_view_from_primitive_loadout,
    canonical_json,
    primitive_loadout_from_build_view,
    resolve_build_blueprint,
)
from shadowbane_lab.rollouts.open_builds import PrimitiveLoadout


def package(
    package_id: str,
    kind: SourcePackageKind,
    *,
    slot: str | None = None,
    actions: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    triggers: tuple[str, ...] = (),
    training_access: tuple[str, ...] = (),
    body_delta: BodyDelta | None = None,
    scalars: tuple[tuple[str, float], ...] = (),
    attributes: tuple[tuple[str, float], ...] = (),
    requires: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
) -> SourcePackage:
    return SourcePackage(
        package_id=package_id,
        display_name=package_id,
        kind=kind,
        selection_slot=slot,
        action_keys=actions,
        tags=tags,
        persistent_trigger_keys=triggers,
        training_access_keys=training_access,
        body_delta=body_delta or BodyDelta(),
        scalar_deltas=scalars,
        attribute_deltas=attributes,
        requires=requires,
        conflicts=conflicts,
    )


def sample_catalog(*, catalog_id: str = "wonderbane") -> SourcePackageCatalog:
    return SourcePackageCatalog(
        catalog_id=catalog_id,
        slot_limits=(
            ("race", 1),
            ("base_class", 1),
            ("discipline", 2),
        ),
        packages=(
            package(
                "race.irekei",
                SourcePackageKind.RACE,
                slot="race",
                body_delta=BodyDelta(health=20.0, move_speed=1.0),
                attributes=(("dexterity", 5.0),),
            ),
            package(
                "base.rogue",
                SourcePackageKind.BASE_CLASS,
                slot="base_class",
                tags=("capability.stealth",),
                actions=("attack.basic",),
            ),
            package(
                "discipline.sun_dancer",
                SourcePackageKind.DISCIPLINE,
                slot="discipline",
                actions=("power.backstab",),
                tags=("equipment.melee",),
                triggers=("trigger.weapon_poison",),
                training_access=("power.backstab",),
                scalars=(("weapon.main_hand.damage_min", 3.0),),
                requires=("base.rogue",),
            ),
            package(
                "discipline.bounty_hunter",
                SourcePackageKind.DISCIPLINE,
                slot="discipline",
                actions=("power.detect_hidden",),
                requires=("base.rogue",),
            ),
        ),
    )


def sample_blueprint(
    *,
    blueprint_id: str = "sundancer",
    package_ids: tuple[str, ...] = (
        "race.irekei",
        "discipline.sun_dancer",
    ),
) -> BuildBlueprint:
    return BuildBlueprint(
        blueprint_id=blueprint_id,
        display_name="Irekei Sun Dancer",
        requested_package_ids=package_ids,
        base_body=BodyValues(
            health=500.0,
            mana=350.0,
            stamina=220.0,
            move_speed=15.0,
        ),
        direct_action_keys=("action.sprint",),
        base_scalars=(("defense", 100.0),),
        attributes=(("dexterity", 100.0), ("intelligence", 160.0)),
        training=(("power.backstab", 40.0),),
    )


class BuildResolverTests(unittest.TestCase):
    def test_requirement_closure_materializes_one_build_view(self) -> None:
        view = resolve_build_blueprint(
            sample_catalog(),
            sample_blueprint(),
            available_action_keys=frozenset(
                {"attack.basic", "power.backstab", "action.sprint"}
            ),
            available_persistent_trigger_keys=frozenset(
                {"trigger.weapon_poison"}
            ),
        )

        self.assertEqual(
            (
                "base.rogue",
                "discipline.sun_dancer",
                "race.irekei",
            ),
            view.selected_package_ids,
        )
        self.assertEqual(("base.rogue",), view.auto_added_requirement_ids)
        self.assertEqual(520.0, view.body.health)
        self.assertEqual(16.0, view.body.move_speed)
        self.assertEqual(
            ("action.sprint", "attack.basic", "power.backstab"),
            view.executable_action_keys,
        )
        self.assertEqual((), view.omitted_action_keys)
        self.assertEqual((), view.unresolved_training_keys)
        self.assertEqual(1.0, view.coverage_fraction)
        backstab_source = next(
            source
            for source in view.grant_sources
            if source.grant_kind == "action"
            and source.grant_key == "power.backstab"
        )
        self.assertEqual(
            ("discipline.sun_dancer",),
            backstab_source.source_package_ids,
        )

    def test_slot_limits_reject_impossible_source_selection(self) -> None:
        catalog = SourcePackageCatalog(
            catalog_id="slots",
            slot_limits=(("race", 1),),
            packages=(
                package("race.a", SourcePackageKind.RACE, slot="race"),
                package("race.b", SourcePackageKind.RACE, slot="race"),
            ),
        )
        blueprint = BuildBlueprint(
            blueprint_id="invalid",
            display_name="Invalid",
            requested_package_ids=("race.a", "race.b"),
        )

        with self.assertRaisesRegex(BuildResolutionError, "selection slot race"):
            resolve_build_blueprint(catalog, blueprint)

    def test_package_conflicts_are_checked_after_requirement_closure(self) -> None:
        catalog = SourcePackageCatalog(
            catalog_id="conflicts",
            packages=(
                package(
                    "package.a",
                    SourcePackageKind.EXPERIMENTAL,
                    conflicts=("package.b",),
                ),
                package("package.b", SourcePackageKind.EXPERIMENTAL),
            ),
        )
        blueprint = BuildBlueprint(
            blueprint_id="invalid",
            display_name="Invalid",
            requested_package_ids=("package.a", "package.b"),
        )

        with self.assertRaisesRegex(BuildResolutionError, "conflicts with"):
            resolve_build_blueprint(catalog, blueprint)

    def test_partial_catalog_retains_omissions_and_training_uncertainty(self) -> None:
        catalog = SourcePackageCatalog(
            catalog_id="partial",
            packages=(
                package(
                    "piece",
                    SourcePackageKind.EXPERIMENTAL,
                    actions=("known.action", "unknown.action"),
                    triggers=("known.trigger", "unknown.trigger"),
                    training_access=("known.training",),
                ),
            ),
        )
        blueprint = BuildBlueprint(
            blueprint_id="partial",
            display_name="Partial",
            requested_package_ids=("piece",),
            training=(("known.training", 20.0), ("unknown.training", 5.0)),
        )

        view = resolve_build_blueprint(
            catalog,
            blueprint,
            available_action_keys=frozenset({"known.action"}),
            available_persistent_trigger_keys=frozenset({"known.trigger"}),
        )

        self.assertEqual(("known.action",), view.executable_action_keys)
        self.assertEqual(("unknown.action",), view.omitted_action_keys)
        self.assertEqual(("known.trigger",), view.executable_persistent_trigger_keys)
        self.assertEqual(("unknown.trigger",), view.omitted_persistent_trigger_keys)
        self.assertEqual(("unknown.training",), view.unresolved_training_keys)
        self.assertEqual(0.5, view.coverage_fraction)

    def test_mechanical_and_construction_signatures_are_distinct_concepts(self) -> None:
        first_catalog = SourcePackageCatalog(
            catalog_id="first-catalog",
            packages=(
                package(
                    "rune.first",
                    SourcePackageKind.DISCIPLINE,
                    actions=("power.same",),
                    tags=("capability.same",),
                    scalars=(("defense", 10.0),),
                ),
            ),
        )
        second_catalog = SourcePackageCatalog(
            catalog_id="second-catalog",
            packages=(
                package(
                    "rune.second",
                    SourcePackageKind.DISCIPLINE,
                    actions=("power.same",),
                    tags=("capability.same",),
                    scalars=(("defense", 10.0),),
                ),
            ),
        )
        first = resolve_build_blueprint(
            first_catalog,
            BuildBlueprint(
                blueprint_id="first",
                display_name="First",
                requested_package_ids=("rune.first",),
            ),
        )
        second = resolve_build_blueprint(
            second_catalog,
            BuildBlueprint(
                blueprint_id="second",
                display_name="Second",
                requested_package_ids=("rune.second",),
            ),
        )

        self.assertEqual(first.mechanical_signature, second.mechanical_signature)
        self.assertNotEqual(first.construction_signature, second.construction_signature)

    def test_request_order_does_not_change_resolved_signatures(self) -> None:
        first = resolve_build_blueprint(
            sample_catalog(),
            sample_blueprint(
                blueprint_id="first",
                package_ids=(
                    "race.irekei",
                    "discipline.sun_dancer",
                    "discipline.bounty_hunter",
                ),
            ),
        )
        second = resolve_build_blueprint(
            sample_catalog(),
            sample_blueprint(
                blueprint_id="second",
                package_ids=(
                    "discipline.bounty_hunter",
                    "discipline.sun_dancer",
                    "race.irekei",
                ),
            ),
        )

        self.assertEqual(first.mechanical_signature, second.mechanical_signature)
        self.assertEqual(first.construction_signature, second.construction_signature)

    def test_primitive_loadout_adapter_preserves_resolved_mechanics(self) -> None:
        original = PrimitiveLoadout(
            loadout_id="open-build",
            display_name="Open Build",
            action_keys=("known", "unknown"),
            health=610.0,
            mana=420.0,
            stamina=250.0,
            move_speed=18.0,
            tags=("equipment.melee",),
            scalars=(("defense", 250.0),),
            persistent_trigger_keys=("proc.known",),
        )
        view = build_view_from_primitive_loadout(
            original,
            available_action_keys=frozenset({"known"}),
            available_persistent_trigger_keys=frozenset({"proc.known"}),
        )
        adapted = primitive_loadout_from_build_view(view)

        self.assertEqual(("known",), adapted.action_keys)
        self.assertEqual(610.0, adapted.health)
        self.assertEqual(("equipment.melee",), adapted.tags)
        self.assertIn("mechanical_signature", dict(adapted.metadata))
        self.assertTrue(any(note.startswith("Omitted actions") for note in adapted.notes))


class SimulationCaseViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.build = resolve_build_blueprint(sample_catalog(), sample_blueprint())
        self.left_overlay = ScenarioOverlay(
            overlay_id="left-default",
            position=(0.0, 0.0),
            resource_fractions=(("health", 1.0), ("mana", 1.0)),
            added_tags=("visibility.invisible",),
        )
        self.right_overlay = ScenarioOverlay(
            overlay_id="right-default",
            position=(40.0, 0.0),
            resource_fractions=(("health", 1.0), ("mana", 1.0)),
        )

    def scenario(
        self,
        *,
        right_position: float = 40.0,
        affiliation_digest: str = "affiliations-a",
    ) -> ResolvedScenarioView:
        return ResolvedScenarioView(
            scenario_id="duel",
            ruleset_revision="wonderbane:test",
            environment_profile_id="flat-arena",
            slots=(
                ScenarioSlotView(
                    slot_id="left",
                    entity_id="left-actor",
                    overlay=self.left_overlay,
                    legacy_team_id="left-side",
                    affiliation_entity_id="entity:left",
                ),
                ScenarioSlotView(
                    slot_id="right",
                    entity_id="right-actor",
                    overlay=ScenarioOverlay(
                        overlay_id="right-variable",
                        position=(right_position, 0.0),
                        resource_fractions=(
                            ("health", 1.0),
                            ("mana", 1.0),
                        ),
                    ),
                    legacy_team_id="right-side",
                    affiliation_entity_id="entity:right",
                ),
            ),
            affiliation_snapshot_id="groups:duel",
            affiliation_snapshot_digest=affiliation_digest,
            affiliation_revision=1,
            duration_limit_ms=480_000,
            tick_ms=200,
        )

    def participants(
        self,
        *,
        left_policy: str = "setup-aware",
    ) -> tuple[SimulationParticipantView, ...]:
        return (
            SimulationParticipantView(
                slot_id="left",
                build=self.build,
                policy_key=left_policy,
            ),
            SimulationParticipantView(
                slot_id="right",
                build=self.build,
                policy_key="resource-aware",
            ),
        )

    def test_build_policy_and_scenario_axes_remain_independent(self) -> None:
        scenario = self.scenario()
        first = SimulationCaseView(
            case_id="first",
            scenario=scenario,
            participants=self.participants(left_policy="setup-aware"),
            seed=7,
        )
        second = SimulationCaseView(
            case_id="second",
            scenario=scenario,
            participants=self.participants(left_policy="greedy"),
            seed=7,
        )

        self.assertEqual(
            first.participants[0].build.mechanical_signature,
            second.participants[0].build.mechanical_signature,
        )
        self.assertEqual(first.scenario.scenario_signature, second.scenario.scenario_signature)
        self.assertNotEqual(first.case_signature, second.case_signature)

    def test_starting_state_changes_scenario_not_build_signature(self) -> None:
        close = self.scenario(right_position=15.0)
        far = self.scenario(right_position=100.0)

        self.assertNotEqual(close.scenario_signature, far.scenario_signature)
        self.assertEqual(
            self.build.mechanical_signature,
            self.participants()[0].build.mechanical_signature,
        )

    def test_opaque_affiliation_snapshot_participates_in_case_identity(self) -> None:
        first = self.scenario(affiliation_digest="party-layout-a")
        second = self.scenario(affiliation_digest="party-layout-b")

        self.assertNotEqual(first.scenario_signature, second.scenario_signature)
        self.assertEqual("groups:duel", first.affiliation_snapshot_id)

    def test_participant_order_does_not_change_case_signature(self) -> None:
        scenario = self.scenario()
        participants = self.participants()
        first = SimulationCaseView(
            case_id="first",
            scenario=scenario,
            participants=participants,
            seed=10,
        )
        second = SimulationCaseView(
            case_id="second",
            scenario=scenario,
            participants=tuple(reversed(participants)),
            seed=10,
        )

        self.assertEqual(first.case_signature, second.case_signature)
        self.assertEqual(first.construction_signature, second.construction_signature)

    def test_case_requires_exact_scenario_slot_coverage(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "participant slots do not match scenario slots",
        ):
            SimulationCaseView(
                case_id="missing-right",
                scenario=self.scenario(),
                participants=(self.participants()[0],),
                seed=1,
            )

    def test_canonical_json_is_stable(self) -> None:
        case = SimulationCaseView(
            case_id="stable-json",
            scenario=self.scenario(),
            participants=self.participants(),
            seed=1,
        )

        self.assertEqual(canonical_json(case), canonical_json(case.as_dict()))


if __name__ == "__main__":
    unittest.main()
