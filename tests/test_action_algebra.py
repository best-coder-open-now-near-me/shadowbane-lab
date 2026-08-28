import unittest

from shadowbane_lab.protocol import NamedScalar, Relation, TargetKind
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    ApplyEffect,
    AreaEffect,
    AreaOrigin,
    AttackKind,
    ChanceGate,
    DamageType,
    DealDamage,
    DeliveryKind,
    DeliverySpec,
    ModifyObjective,
    MoveEntity,
    MovementMode,
    PhaseKind,
    ResistanceType,
    ResourceCost,
    ResourceImmunity,
    RestoreResource,
    SubjectRef,
    TargetingSpec,
    TransferItem,
    UniformAmount,
    UniformIntegerAmount,
    WeightedAmount,
)


def representative_actions() -> tuple[ActionSpec, ...]:
    move = ActionSpec(
        action_key="generic.move",
        targeting=TargetingSpec(kind=TargetKind.DIRECTION),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=200,
                effects=(MoveEntity(SubjectRef.ACTOR, MovementMode.WALK),),
            ),
        ),
        features=(NamedScalar("commitment_ms", 200.0),),
        tags=("movement",),
    )
    melee = ActionSpec(
        action_key="generic.melee_attack",
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ENEMY,),
            maximum_range=3.0,
            requires_line_of_sight=True,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=600,
                effects=(DealDamage(SubjectRef.TARGET, 12.0, "crush"),),
            ),
        ),
        cooldown_ms=800,
        tags=("harmful", "melee"),
    )
    projectile = ActionSpec(
        action_key="generic.projectile",
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ENEMY,),
            maximum_range=120.0,
            requires_line_of_sight=True,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.WINDUP,
                duration_ms=500,
                interruptible=True,
                movement_allowed=False,
            ),
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=0,
                effects=(DealDamage(SubjectRef.TARGET, 18.0, "cold"),),
                delivery=DeliverySpec(
                    DeliveryKind.PROJECTILE,
                    projectile_speed_units_per_second=60.0,
                ),
            ),
        ),
        costs=(ResourceCost("mana", 10.0),),
        tags=("harmful", "projectile", "ranged"),
    )
    heal = ActionSpec(
        action_key="generic.heal",
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.SELF, Relation.ALLY),
            maximum_range=30.0,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=800,
                effects=(RestoreResource(SubjectRef.TARGET, "health", 20.0),),
                interruptible=True,
            ),
        ),
        costs=(ResourceCost("mana", 8.0),),
        tags=("beneficial", "healing"),
    )
    stealth = ActionSpec(
        action_key="generic.stealth",
        targeting=TargetingSpec(kind=TargetKind.SELF),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=200,
                effects=(
                    ApplyEffect(
                        SubjectRef.ACTOR,
                        "concealed",
                        duration_ms=10_000,
                        stacking_key="concealment",
                        tags=("visibility.concealed",),
                    ),
                ),
            ),
        ),
        forbidden_actor_tags=("visibility.revealed",),
        tags=("beneficial", "stealth"),
    )
    transfer = ActionSpec(
        action_key="generic.transfer_item",
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ALLY, Relation.NEUTRAL),
            maximum_range=2.0,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=0,
                effects=(TransferItem(SubjectRef.ACTOR, SubjectRef.TARGET),),
            ),
        ),
        tags=("interaction", "transfer"),
    )
    capture = ActionSpec(
        action_key="generic.capture_objective",
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ENEMY, Relation.NEUTRAL),
            maximum_range=4.0,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=1_000,
                effects=(ModifyObjective(SubjectRef.OBJECTIVE, 0.1),),
                interruptible=True,
            ),
        ),
        tags=("interaction", "objective"),
    )
    return move, melee, projectile, heal, stealth, transfer, capture


class ActionAlgebraTests(unittest.TestCase):
    def test_damage_and_resistance_channels_are_closed_vocabularies(self) -> None:
        damage = DealDamage(SubjectRef.TARGET, 12.0, "cold")
        healing = RestoreResource(
            SubjectRef.TARGET,
            "health",
            12.0,
            uses_resistance=True,
            resistance_type="healing",
        )

        self.assertIs(DamageType.COLD, damage.damage_type)
        self.assertIs(ResistanceType.HEALING, healing.resistance_type)
        with self.assertRaisesRegex(ValueError, "DamageType"):
            DealDamage(SubjectRef.TARGET, 12.0, "physical")
        with self.assertRaisesRegex(ValueError, "unknown damage cannot use resistance"):
            DealDamage(
                SubjectRef.TARGET,
                12.0,
                DamageType.UNKNOWN,
                uses_resistance=True,
            )
        with self.assertRaisesRegex(ValueError, "ResistanceType"):
            RestoreResource(
                SubjectRef.TARGET,
                "health",
                12.0,
                uses_resistance=True,
                resistance_type="invented",
            )

    def test_area_is_a_target_set_combinator_not_a_second_damage_primitive(self) -> None:
        damage = DealDamage(SubjectRef.TARGET, 12.0, DamageType.FIRE)
        direct = ActionSpec(
            action_key="direct",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
            ),
            phases=(ActionPhase(PhaseKind.ACTIVE, 0, (damage,)),),
        )
        area = ActionSpec(
            action_key="area",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    (
                        AreaEffect(
                            origin=AreaOrigin.ACTOR,
                            radius=10.0,
                            allowed_relations=(Relation.ENEMY,),
                            effects=(damage,),
                        ),
                    ),
                ),
            ),
        )

        self.assertIs(damage, direct.phases[0].effects[0])
        wrapped = area.phases[0].effects[0]
        assert isinstance(wrapped, AreaEffect)
        self.assertIs(damage, wrapped.effects[0])

    def test_hit_resolution_is_independent_of_target_shape(self) -> None:
        hostile = ActionSpec(
            action_key="hostile-power",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
            ),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    (DealDamage(SubjectRef.TARGET, 1.0, DamageType.MENTAL),),
                ),
            ),
            hit_roll=AttackKind.POWER,
        )

        self.assertIs(AttackKind.POWER, hostile.hit_roll)
        with self.assertRaisesRegex(ValueError, "hostile"):
            ActionSpec(
                action_key="self-hit-roll",
                targeting=TargetingSpec(kind=TargetKind.SELF),
                phases=(ActionPhase(PhaseKind.ACTIVE, 0),),
                hit_roll=AttackKind.POWER,
            )

    def test_effect_mechanics_are_typed_instead_of_runtime_tag_conventions(self) -> None:
        effect = ApplyEffect(
            SubjectRef.TARGET,
            "healing-lock",
            1_000,
            modifiers=(ResourceImmunity("health"),),
        )

        self.assertEqual(("immunity.resource.health",), effect.modifiers[0].semantic_tags)
        with self.assertRaisesRegex(ValueError, "typed effect modifiers"):
            ApplyEffect(
                SubjectRef.TARGET,
                "invalid",
                1_000,
                modifiers=(object(),),  # type: ignore[arg-type]
            )

    def test_chance_gate_requires_a_bounded_direct_effect_bundle(self) -> None:
        gate = ChanceGate(
            "weapon_proc",
            0.05,
            (DealDamage(SubjectRef.TARGET, 12.0, "mental"),),
        )

        self.assertEqual(0.05, gate.probability)
        with self.assertRaisesRegex(ValueError, "at least one"):
            ChanceGate("empty", 0.5, ())
        with self.assertRaisesRegex(ValueError, "direct effect"):
            ChanceGate("nested", 0.5, (gate,))  # type: ignore[arg-type]

    def test_uniform_amount_is_bounded_and_exposes_its_expected_value(self) -> None:
        amount = UniformAmount(24.0, 33.0)

        self.assertEqual(28.5, amount.expected)
        self.assertEqual(amount, DealDamage(SubjectRef.TARGET, amount, "cold").amount)

        with self.assertRaisesRegex(ValueError, "greater than minimum"):
            UniformAmount(10.0, 10.0)

    def test_uniform_integer_amount_has_inclusive_integer_bounds(self) -> None:
        amount = UniformIntegerAmount(4, 5)

        self.assertEqual(4.5, amount.expected)
        self.assertEqual(amount, DealDamage(SubjectRef.TARGET, amount, "crush").amount)

        with self.assertRaisesRegex(ValueError, "must be an integer"):
            UniformIntegerAmount(4, 5.5)  # type: ignore[arg-type]

    def test_weighted_amount_preserves_observed_outcomes_and_expected_value(self) -> None:
        amount = WeightedAmount(((10.0, 1), (40.0, 3)))

        self.assertEqual(4, amount.total_weight)
        self.assertEqual(32.5, amount.expected)
        self.assertEqual(amount, DealDamage(SubjectRef.TARGET, amount, "unknown").amount)

        with self.assertRaisesRegex(ValueError, "sorted"):
            WeightedAmount(((40.0, 1), (10.0, 1)))

    def test_one_grammar_represents_all_required_action_families(self) -> None:
        catalog = ActionCatalog(representative_actions())

        self.assertEqual(7, len(catalog))
        self.assertEqual(
            {
                "generic.capture_objective",
                "generic.heal",
                "generic.melee_attack",
                "generic.move",
                "generic.projectile",
                "generic.stealth",
                "generic.transfer_item",
            },
            {action.action_key for action in catalog.actions},
        )

    def test_catalog_order_is_deterministic(self) -> None:
        actions = representative_actions()

        forward = ActionCatalog(actions)
        reverse = ActionCatalog(tuple(reversed(actions)))

        self.assertEqual(forward.actions, reverse.actions)

    def test_catalog_rejects_duplicate_action_keys(self) -> None:
        action = representative_actions()[0]

        with self.assertRaisesRegex(ValueError, "action keys"):
            ActionCatalog((action, action))

    def test_projectile_delivery_requires_positive_speed(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a speed"):
            DeliverySpec(DeliveryKind.PROJECTILE)

    def test_entity_targeting_requires_relations(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowed relation"):
            TargetingSpec(kind=TargetKind.ENTITY)

    def test_action_rejects_untyped_effects_during_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "typed effect primitives"):
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=0,
                effects=(object(),),  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
