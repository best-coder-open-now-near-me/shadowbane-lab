import unittest

from shadowbane_lab.protocol import EntityKind, Relation, TargetKind, Vector2
from shadowbane_lab.rollouts.duel import _cancel_dead_actor_schedule
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    DamageType,
    DealDamage,
    EntityState,
    PhaseKind,
    ReferenceEnvironment,
    SubjectRef,
    TargetingSpec,
)

DELAYED = "test.delayed"
KILL = "test.kill"


def decision(environment: ReferenceEnvironment, actor_id: str, action_key: str, target_id: str):
    exchange = environment.exchange(actor_id)
    selected = next(
        affordance
        for affordance in exchange.affordances.affordances
        if affordance.action_key == action_key and affordance.binding.target_entity_id == target_id
    )
    return exchange.decision(selected.affordance_id, f"{actor_id}:{action_key}")


class RolloutGuardTests(unittest.TestCase):
    def test_dead_actor_future_resolution_is_cancelled(self) -> None:
        catalog = ActionCatalog(
            (
                ActionSpec(
                    action_key=DELAYED,
                    targeting=TargetingSpec(
                        TargetKind.ENTITY,
                        allowed_relations=(Relation.ENEMY,),
                        maximum_range=100.0,
                    ),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            400,
                            effects=(
                                DealDamage(SubjectRef.TARGET, 50.0, DamageType.CRUSH),
                            ),
                        ),
                    ),
                    cooldown_ms=400,
                ),
                ActionSpec(
                    action_key=KILL,
                    targeting=TargetingSpec(
                        TargetKind.ENTITY,
                        allowed_relations=(Relation.ENEMY,),
                        maximum_range=100.0,
                    ),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            0,
                            effects=(
                                DealDamage(SubjectRef.TARGET, 10.0, DamageType.CRUSH),
                            ),
                        ),
                    ),
                ),
            )
        )
        caster = EntityState(
            "caster",
            "caster:1",
            EntityKind.ACTOR,
            "red",
            Vector2(0.0, 0.0),
            scalars={"health": 10.0},
            maximums={"health": 10.0},
            action_keys=(DELAYED,),
        )
        target = EntityState(
            "target",
            "target:1",
            EntityKind.ACTOR,
            "blue",
            Vector2(10.0, 0.0),
            scalars={"health": 100.0},
            maximums={"health": 100.0},
        )
        executioner = EntityState(
            "executioner",
            "executioner:1",
            EntityKind.ACTOR,
            "blue",
            Vector2(5.0, 0.0),
            scalars={"health": 100.0},
            maximums={"health": 100.0},
            action_keys=(KILL,),
        )
        environment = ReferenceEnvironment(catalog, (caster, target, executioner), seed=9)

        environment.step(
            (
                decision(environment, "caster", DELAYED, "target"),
                decision(environment, "executioner", KILL, "caster"),
            )
        )
        removed = _cancel_dead_actor_schedule(environment)
        environment.step()

        self.assertFalse(environment.entity("caster").alive)
        self.assertGreaterEqual(removed, 1)
        self.assertEqual(100.0, environment.entity("target").scalars["health"])


if __name__ == "__main__":
    unittest.main()
