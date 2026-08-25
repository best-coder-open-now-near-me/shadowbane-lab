import unittest

from shadowbane_lab.protocol import NamedScalar, Relation, TargetKind
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    ApplyEffect,
    DealDamage,
    DeliveryKind,
    DeliverySpec,
    ModifyObjective,
    MoveEntity,
    MovementMode,
    PhaseKind,
    ResourceCost,
    RestoreResource,
    SubjectRef,
    TargetingSpec,
    TransferItem,
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
                effects=(DealDamage(SubjectRef.TARGET, 12.0, "physical"),),
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


if __name__ == "__main__":
    unittest.main()
