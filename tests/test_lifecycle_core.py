import unittest

from shadowbane_lab.protocol import EntityKind, EventKind, Relation, TargetKind, Vector2
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionExecutionStatus,
    ActionPhase,
    ActionSpec,
    DealDamage,
    DeliveryKind,
    DeliverySpec,
    EntityState,
    PayloadReleaseStatus,
    PhaseKind,
    ReferenceEnvironment,
    SubjectRef,
    TargetingSpec,
)


def actor(
    entity_id: str,
    team_id: str,
    action_keys: tuple[str, ...],
    *,
    position: Vector2 | None = None,
    health: float = 100.0,
) -> EntityState:
    return EntityState(
        entity_id=entity_id,
        life_id=f"{entity_id}:1",
        kind=EntityKind.ACTOR,
        team_id=team_id,
        position=position if position is not None else Vector2(0.0, 0.0),
        scalars={"health": health, "mana": 100.0, "move_speed": 10.0},
        maximums={"health": health, "mana": 100.0},
        action_keys=action_keys,
    )


def decision(
    environment: ReferenceEnvironment,
    actor_id: str,
    action_key: str,
    correlation_id: str,
    *,
    target_id: str | None = None,
):
    exchange = environment.exchange(actor_id)
    matches = [
        item
        for item in exchange.affordances.affordances
        if item.action_key == action_key
        and (target_id is None or item.binding.target_entity_id == target_id)
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one affordance, found {len(matches)}")
    return exchange.decision(matches[0].affordance_id, correlation_id)


def hostile_targeting(maximum_range: float = 120.0) -> TargetingSpec:
    return TargetingSpec(
        kind=TargetKind.ENTITY,
        allowed_relations=(Relation.ENEMY,),
        maximum_range=maximum_range,
    )


class LifecycleCoreTests(unittest.TestCase):
    def test_execution_snapshot_tracks_current_phase_and_replays(self) -> None:
        cast = ActionSpec(
            action_key="cast",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.WINDUP,
                    400,
                    interruptible=True,
                    movement_allowed=False,
                ),
                ActionPhase(
                    PhaseKind.ACTIVE,
                    200,
                    effects=(DealDamage(SubjectRef.TARGET, 5.0, "magic"),),
                    interruptible=True,
                ),
                ActionPhase(PhaseKind.RECOVERY, 200),
            ),
            cancel_on_damage=True,
        )
        environment = ReferenceEnvironment(
            ActionCatalog((cast,)),
            (
                actor("caster", "red", ("cast",)),
                actor("target", "blue", (), position=Vector2(1.0, 0.0)),
            ),
            seed=1,
        )

        environment.step((decision(environment, "caster", "cast", "cast-1", target_id="target"),))
        execution = environment.execution("cast-1")
        snapshot = environment.snapshot()

        self.assertEqual(0, execution.phase_index)
        self.assertEqual(PhaseKind.WINDUP, execution.phase_kind)
        self.assertEqual(ActionExecutionStatus.ACTIVE, execution.status)
        self.assertFalse(execution.movement_allowed)
        self.assertEqual(PayloadReleaseStatus.NOT_APPLICABLE, execution.payload_release_status)
        expected = environment.step()
        environment.restore(snapshot)
        self.assertEqual(expected, environment.step())

    def test_later_interruptible_phase_does_not_make_windup_interruptible(self) -> None:
        poke = ActionSpec(
            action_key="poke",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    effects=(DealDamage(SubjectRef.TARGET, 1.0, "crush"),),
                ),
            ),
        )
        cast = ActionSpec(
            action_key="cast",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(PhaseKind.WINDUP, 400, interruptible=False),
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    effects=(DealDamage(SubjectRef.TARGET, 7.0, "magic"),),
                    interruptible=True,
                ),
            ),
            cancel_on_damage=True,
        )
        environment = ReferenceEnvironment(
            ActionCatalog((poke, cast)),
            (
                actor("a-poker", "blue", ("poke",), position=Vector2(1.0, 0.0)),
                actor("b-caster", "red", ("cast",)),
            ),
            seed=2,
        )
        result = environment.step(
            (
                decision(
                    environment,
                    "a-poker",
                    "poke",
                    "poke-1",
                    target_id="b-caster",
                ),
                decision(
                    environment,
                    "b-caster",
                    "cast",
                    "cast-1",
                    target_id="a-poker",
                ),
            )
        )
        environment.step()

        self.assertFalse(
            any(
                event.kind == EventKind.ACTION_INTERRUPTED and event.correlation_id == "cast-1"
                for event in result.events
            )
        )
        self.assertEqual(93.0, environment.entity("a-poker").scalars["health"])
        self.assertEqual(ActionExecutionStatus.COMPLETED, environment.execution("cast-1").status)

    def test_same_timestamp_damage_cancels_unreleased_payload_still_in_queue(self) -> None:
        interrupt = ActionSpec(
            action_key="interrupt",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    200,
                    effects=(DealDamage(SubjectRef.TARGET, 1.0, "crush"),),
                ),
            ),
        )
        cast = ActionSpec(
            action_key="cast",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    200,
                    effects=(DealDamage(SubjectRef.TARGET, 20.0, "magic"),),
                    interruptible=True,
                ),
            ),
            cancel_on_damage=True,
        )
        environment = ReferenceEnvironment(
            ActionCatalog((interrupt, cast)),
            (
                actor("a-interrupter", "blue", ("interrupt",), position=Vector2(1.0, 0.0)),
                actor("b-caster", "red", ("cast",)),
            ),
            seed=3,
        )

        result = environment.step(
            (
                decision(
                    environment,
                    "a-interrupter",
                    "interrupt",
                    "interrupt-1",
                    target_id="b-caster",
                ),
                decision(
                    environment,
                    "b-caster",
                    "cast",
                    "cast-1",
                    target_id="a-interrupter",
                ),
            )
        )

        self.assertEqual(100.0, environment.entity("a-interrupter").scalars["health"])
        self.assertEqual(ActionExecutionStatus.INTERRUPTED, environment.execution("cast-1").status)
        self.assertTrue(
            any(
                event.kind == EventKind.ACTION_INTERRUPTED and event.correlation_id == "cast-1"
                for event in result.events
            )
        )

    def test_released_projectile_survives_source_death_without_completed_then_interrupted(
        self,
    ) -> None:
        bolt = ActionSpec(
            action_key="bolt",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    effects=(DealDamage(SubjectRef.TARGET, 9.0, "cold"),),
                    delivery=DeliverySpec(
                        DeliveryKind.PROJECTILE,
                        projectile_speed_units_per_second=60.0,
                    ),
                    interruptible=True,
                ),
            ),
            cancel_on_damage=True,
        )
        kill = ActionSpec(
            action_key="kill",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    effects=(DealDamage(SubjectRef.TARGET, 200.0, "crush"),),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((bolt, kill)),
            (
                actor("caster", "red", ("bolt",)),
                actor("killer", "blue", ("kill",), position=Vector2(1.0, 0.0)),
                actor("target", "blue", (), position=Vector2(60.0, 0.0)),
            ),
            seed=4,
        )
        first = environment.step(
            (decision(environment, "caster", "bolt", "bolt-1", target_id="target"),)
        )
        second = environment.step(
            (decision(environment, "killer", "kill", "kill-1", target_id="caster"),)
        )
        for _ in range(3):
            environment.step()
        impact = environment.step()

        self.assertFalse(environment.entity("caster").alive)
        self.assertEqual(91.0, environment.entity("target").scalars["health"])
        self.assertEqual(ActionExecutionStatus.COMPLETED, environment.execution("bolt-1").status)
        all_events = (*first.events, *second.events, *impact.events)
        self.assertFalse(
            any(
                event.kind == EventKind.ACTION_INTERRUPTED and event.correlation_id == "bolt-1"
                for event in all_events
            )
        )

    def test_death_cancels_source_bound_unreleased_work(self) -> None:
        cast = ActionSpec(
            action_key="cast",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.WINDUP,
                    600,
                    effects=(DealDamage(SubjectRef.TARGET, 25.0, "magic"),),
                    interruptible=False,
                ),
            ),
        )
        kill = ActionSpec(
            action_key="kill",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    effects=(DealDamage(SubjectRef.TARGET, 200.0, "crush"),),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((cast, kill)),
            (
                actor("caster", "red", ("cast",)),
                actor("killer", "blue", ("kill",), position=Vector2(1.0, 0.0)),
            ),
            seed=5,
        )
        environment.step((decision(environment, "caster", "cast", "cast-1", target_id="killer"),))
        death = environment.step(
            (decision(environment, "killer", "kill", "kill-1", target_id="caster"),)
        )
        for _ in range(3):
            environment.step()

        self.assertEqual(100.0, environment.entity("killer").scalars["health"])
        self.assertEqual(ActionExecutionStatus.INTERRUPTED, environment.execution("cast-1").status)
        self.assertTrue(
            any(
                event.kind == EventKind.ACTION_INTERRUPTED
                and event.correlation_id == "cast-1"
                and "reason.death" in event.tags
                for event in death.events
            )
        )


if __name__ == "__main__":
    unittest.main()
