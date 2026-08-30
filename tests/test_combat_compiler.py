import unittest
from dataclasses import replace

from shadowbane_lab.combat import (
    CombatSheet,
    CompatibilityStatus,
    SheetModifiers,
    StanceModifiers,
    StanceProfile,
    WeaponProcProfile,
    WeaponProfile,
    spell_amount_bounds,
)
from shadowbane_lab.combat.compiler import (
    MAGICBANE_COMBAT_FORMULA_REVISION,
    REQUIRED_RESISTANCE_TYPES,
    CombatCompilePolicy,
    CombatReadinessError,
    compile_combatant,
)
from shadowbane_lab.protocol import Relation, TargetKind, Vector2
from shadowbane_lab.rulesets import CharacterBuild, load_shadowbane_vertical_slice
from shadowbane_lab.sim import (
    ActionPhase,
    ApplyEffect,
    AreaEffect,
    AreaOrigin,
    AttackGate,
    ChanceGate,
    CombatStance,
    DealDamage,
    PhaseKind,
    ResourceImmunity,
    SubjectRef,
    TargetingSpec,
    TriangularAmount,
)

SHADOW_BOLT = "shadowbane.assassin.shadow_bolt"
SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"
SHADOW_MANTLE = "shadowbane.assassin.shadow_mantle"


def _sheet() -> CombatSheet:
    return CombatSheet(
        sheet_id="irekei-assassin-59",
        profession="assassin",
        level=59,
        source_id="live-sheet-test",
        source_revision="fixture-1",
        formula_revision=MAGICBANE_COMBAT_FORMULA_REVISION,
        compatibility=CompatibilityStatus.SOURCE_REVISION_ACCEPTED,
        strength=90,
        dexterity=170,
        constitution=100,
        intelligence=170,
        spirit=90,
        maximum_health=1_200.0,
        maximum_mana=900.0,
        maximum_stamina=700.0,
        move_speed=30.0,
        equipment_defense=140.0,
        skill_values=(("unarmed", 161.0), ("unarmed_mastery", 70.0)),
        power_focus_values=((SHADOW_BOLT, 97.0), (SHADOW_TOUCH, 97.0)),
        resistances=tuple((key, 0.0) for key in sorted(REQUIRED_RESISTANCE_TYPES)),
        passive_defenses=(("block", 0.0), ("parry", 0.0), ("dodge", 25.0)),
        modifiers=SheetModifiers(armor_piercing=0.05),
        weapon=WeaponProfile(
            weapon_key="rha-khanakar",
            damage_type="crush",
            skill_key="unarmed",
            mastery_key="unarmed_mastery",
            base_minimum=4.0,
            base_maximum=16.0,
            speed_tenths=20.0,
            range_units=6.0,
            strength_based=False,
            procs=(
                WeaponProcProfile(
                    proc_key="tier-three-mental",
                    probability=0.05,
                    minimum=20.0,
                    maximum=46.0,
                    damage_type="mental",
                ),
            ),
        ),
    )


def _build() -> CharacterBuild:
    return CharacterBuild(
        profession="assassin",
        level=59,
        skill_ranks=(("shadowmastery", 200),),
        power_ranks=((SHADOW_BOLT, 40), (SHADOW_TOUCH, 40)),
        enabled_power_keys=(SHADOW_BOLT, SHADOW_TOUCH),
    )


class CombatCompilerTests(unittest.TestCase):
    def test_source_stance_profiles_compile_as_actions_and_dynamic_scalar_channels(
        self,
    ) -> None:
        sheet = replace(
            _sheet(),
            stance_profiles=(
                StanceProfile(
                    profile_key="rogue_assassin",
                    stance=CombatStance.PRECISE,
                    rank=25,
                    source_id="stance-fixture",
                    source_revision="1",
                    modifiers=StanceModifiers(
                        attack_percent=0.36,
                        damage_dealt_percent=-0.19,
                    ),
                ),
            ),
        )
        policy = CombatCompilePolicy(
            accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
            allow_ruleset_overrides=True,
        )

        compiled = compile_combatant(
            sheet,
            _build(),
            load_shadowbane_vertical_slice(),
            policy=policy,
        )
        entity = compiled.entity("assassin", "red", Vector2(0.0, 0.0))
        self.assertEqual(939.0, entity.effective_scalar("attack.main_hand"))
        entity.stance = CombatStance.PRECISE

        self.assertEqual(1277.0, entity.effective_scalar("attack.main_hand"))
        self.assertAlmostEqual(0.81, entity.effective_scalar("outgoing.damage.factor"))
        precise = compiled.catalog.get(compiled.action_key("shadowbane.stance.precise"))
        normal = compiled.catalog.get(compiled.action_key("shadowbane.stance.normal"))
        self.assertEqual(20_000, precise.cooldown_ms)
        self.assertIn("stance.change.precise", precise.tags)
        self.assertIn("stance.precise", precise.forbidden_actor_tags)
        self.assertIn("stance.change.normal", normal.tags)

    def test_no_hit_roll_debuff_needs_no_focus_and_compiles_without_attack_gate(self) -> None:
        build = replace(
            _build(),
            power_ranks=((SHADOW_MANTLE, 40),),
            enabled_power_keys=(SHADOW_MANTLE,),
        )
        sheet = replace(_sheet(), power_focus_values=())
        policy = CombatCompilePolicy(
            accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
            allow_ruleset_overrides=True,
        )

        compiled = compile_combatant(
            sheet,
            build,
            load_shadowbane_vertical_slice(),
            policy=policy,
        )

        mantle = compiled.catalog.get(compiled.action_key(SHADOW_MANTLE))
        effect = mantle.phases[0].effects[0]
        self.assertIsInstance(effect, ApplyEffect)
        assert isinstance(effect, ApplyEffect)
        self.assertEqual(40, effect.trains)
        self.assertEqual((ResourceImmunity("health"),), effect.modifiers)
        self.assertEqual(
            16_000.0,
            {feature.name: feature.value for feature in mantle.features}["commitment_ms"],
        )

    def test_default_policy_rejects_unverified_compatibility_and_ruleset_overrides(self) -> None:
        with self.assertRaises(CombatReadinessError) as raised:
            compile_combatant(_sheet(), _build(), load_shadowbane_vertical_slice())

        self.assertIn(
            "sheet compatibility source_revision_accepted is not accepted",
            raised.exception.issues,
        )
        self.assertTrue(
            any(
                "requires ruleset-override acceptance" in issue for issue in raised.exception.issues
            )
        )

    def test_explicit_source_acceptance_compiles_sheet_stats_weapon_procs_and_powers(self) -> None:
        policy = CombatCompilePolicy(
            accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
            allow_ruleset_overrides=True,
        )

        compiled = compile_combatant(
            _sheet(),
            _build(),
            load_shadowbane_vertical_slice(),
            policy=policy,
        )

        basic = compiled.catalog.get(compiled.action_key("shadowbane.basic_attack"))
        basic_gate = basic.phases[0].effects[0]
        self.assertIsInstance(basic_gate, AttackGate)
        assert isinstance(basic_gate, AttackGate)
        self.assertIsInstance(basic_gate.effects[0], DealDamage)
        self.assertIsInstance(basic_gate.effects[1], ChanceGate)
        self.assertEqual(2_000, basic.cooldown_ms)
        features = {item.name: item.value for item in basic.features}
        self.assertAlmostEqual(
            ((basic_gate.effects[0].amount.minimum + basic_gate.effects[0].amount.maximum) / 2)
            + 0.05 * 33.0,
            features["expected_damage"],
        )
        self.assertEqual(
            ("passive.block", "passive.parry", "passive.dodge"),
            basic_gate.passive_defense_keys,
        )

        shadow_bolt = compiled.catalog.get(compiled.action_key(SHADOW_BOLT))
        power_gate = shadow_bolt.phases[0].effects[0]
        self.assertIsInstance(power_gate, AttackGate)
        assert isinstance(power_gate, AttackGate)
        damage = next(effect for effect in power_gate.effects if isinstance(effect, DealDamage))
        minimum, maximum = spell_amount_bounds(24.0, 33.0, 170, 90, 97.0)
        self.assertEqual(TriangularAmount(float(minimum), float(maximum)), damage.amount)
        self.assertTrue(damage.uses_resistance)
        self.assertEqual(40, damage.power_trains)

        scalars = dict(compiled.scalars)
        self.assertGreater(scalars["attack.main_hand"], 0.0)
        self.assertGreater(scalars[f"attack.power.{SHADOW_BOLT}"], 0.0)
        self.assertEqual(0.05, scalars["armor_piercing"])
        self.assertEqual(1_200.0, dict(compiled.maximums)["health"])

    def test_dual_wield_sheet_compiles_independent_per_hand_attack_schedules(self) -> None:
        main_hand = replace(_sheet().weapon, dual_wielding=True)
        assert main_hand is not None
        off_hand = replace(
            main_hand,
            weapon_key="khan-xhir",
            speed_tenths=21.5,
            procs=(),
        )
        sheet = replace(
            _sheet(),
            weapon=main_hand,
            off_hand_weapon=off_hand,
        )
        policy = CombatCompilePolicy(
            accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
            allow_ruleset_overrides=True,
        )

        compiled = compile_combatant(
            sheet,
            _build(),
            load_shadowbane_vertical_slice(),
            policy=policy,
        )

        main = compiled.catalog.get(compiled.action_key("shadowbane.basic_attack"))
        off = compiled.catalog.get(compiled.action_key("shadowbane.basic_attack.off_hand"))
        self.assertEqual(2_000, main.cooldown_ms)
        self.assertEqual(2_100, off.cooldown_ms)
        self.assertIn("weapon.main_hand", main.tags)
        self.assertIn("weapon.off_hand", off.tags)
        self.assertIn("attack.off_hand", dict(compiled.scalars))

    def test_missing_complete_resistance_vector_fails_before_simulation(self) -> None:
        sheet = replace(
            _sheet(),
            resistances=tuple(item for item in _sheet().resistances if item[0] != "mental"),
        )
        policy = CombatCompilePolicy(
            accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
            allow_ruleset_overrides=True,
        )

        with self.assertRaises(CombatReadinessError) as raised:
            compile_combatant(
                sheet,
                _build(),
                load_shadowbane_vertical_slice(),
                policy=policy,
            )

        self.assertIn("missing resistances: mental", raised.exception.issues)

    def test_hostile_area_power_scales_damage_and_rolls_to_hit_per_victim(self) -> None:
        ruleset = load_shadowbane_vertical_slice()
        record = ruleset.record(SHADOW_BOLT)
        assert record.action is not None
        area_action = replace(
            record.action,
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        AreaEffect(
                            origin=AreaOrigin.ACTOR,
                            radius=8.0,
                            allowed_relations=(Relation.ENEMY,),
                            effects=(
                                DealDamage(
                                    SubjectRef.TARGET,
                                    24.0,
                                    "mental",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        area_record = replace(record, action=area_action)
        ruleset = replace(
            ruleset,
            records=tuple(
                area_record if item.action_key == SHADOW_BOLT else item for item in ruleset.records
            ),
        )
        policy = CombatCompilePolicy(
            accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
            allow_ruleset_overrides=True,
        )

        compiled = compile_combatant(_sheet(), _build(), ruleset, policy=policy)

        action = compiled.catalog.get(compiled.action_key(SHADOW_BOLT))
        area = action.phases[0].effects[0]
        self.assertIsInstance(area, AreaEffect)
        assert isinstance(area, AreaEffect)
        gate = area.effects[0]
        self.assertIsInstance(gate, AttackGate)
        assert isinstance(gate, AttackGate)
        damage = gate.effects[0]
        self.assertIsInstance(damage, DealDamage)
        assert isinstance(damage, DealDamage)
        minimum, maximum = spell_amount_bounds(24.0, 24.0, 170, 90, 97.0)
        self.assertEqual(TriangularAmount(float(minimum), float(maximum)), damage.amount)
        self.assertEqual(
            (minimum + maximum) / 2.0,
            {feature.name: feature.value for feature in action.features}["expected_damage"],
        )


if __name__ == "__main__":
    unittest.main()
