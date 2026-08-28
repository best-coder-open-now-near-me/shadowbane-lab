import unittest

from shadowbane_lab.protocol import EntityKind, EventKind, Relation, TargetKind, Vector2
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    ActiveEffectState,
    ApplyEffect,
    ChanceGate,
    DealDamage,
    DeliveryKind,
    DeliverySpec,
    EntityState,
    ModifyObjective,
    MoveEntity,
    MovementMode,
    PhaseKind,
    ReferenceEnvironment,
    ResourceCost,
    SubjectRef,
    TargetingSpec,
    TransferItem,
    UniformAmount,
    WeightedAmount,
)


def action_for(
    environment: ReferenceEnvironment,
    agent_id: str,
    action_key: str,
    *,
    target_id: str | None = None,
    direction: Vector2 | None = None,
    correlation_id: str,
):
    exchange = environment.exchange(agent_id)
    matches = tuple(
        affordance
        for affordance in exchange.affordances.affordances
        if affordance.action_key == action_key
        and (target_id is None or affordance.binding.target_entity_id == target_id)
        and (direction is None or affordance.binding.direction == direction)
    )
    if len(matches) != 1:
        raise AssertionError(f"expected one matching affordance, found {len(matches)}")
    return exchange.decision(matches[0].affordance_id, correlation_id)


def actor(
    entity_id: str,
    team_id: str,
    position: Vector2,
    action_keys: tuple[str, ...],
    *,
    health: float = 10.0,
    mana: float = 10.0,
    inventory: dict[str, float] | None = None,
    move_speed: float = 10.0,
) -> EntityState:
    return EntityState(
        entity_id=entity_id,
        life_id=f"{entity_id}:1",
        kind=EntityKind.ACTOR,
        team_id=team_id,
        position=position,
        scalars={"health": health, "mana": mana, "move_speed": move_speed},
        maximums={"health": health, "mana": mana},
        action_keys=action_keys,
        inventory=inventory or {},
    )


class ReferenceEnvironmentTests(unittest.TestCase):
    def test_chance_gate_emits_seeded_outcome_and_applies_damage_only_on_success(self) -> None:
        proc_attack = ActionSpec(
            action_key="proc_attack",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=3.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        ChanceGate(
                            "weapon_proc",
                            0.5,
                            (DealDamage(SubjectRef.TARGET, 4.0, "mental"),),
                        ),
                    ),
                ),
            ),
        )

        def run(seed: int):
            environment = ReferenceEnvironment(
                ActionCatalog((proc_attack,)),
                (
                    actor("attacker", "red", Vector2(0.0, 0.0), ("proc_attack",)),
                    actor("target", "blue", Vector2(1.0, 0.0), (), health=10.0),
                ),
                seed=seed,
            )
            decision = action_for(
                environment,
                "attacker",
                "proc_attack",
                target_id="target",
                correlation_id=f"proc-{seed}",
            )
            return environment, environment.step((decision,))

        triggered_environment, triggered = run(0)
        missed_environment, missed = run(1)

        triggered_chance = next(
            event for event in triggered.events if event.kind == EventKind.CHANCE_RESOLVED
        )
        missed_chance = next(
            event for event in missed.events if event.kind == EventKind.CHANCE_RESOLVED
        )
        self.assertIn("outcome.triggered", triggered_chance.tags)
        self.assertIn("outcome.not_triggered", missed_chance.tags)
        self.assertEqual(6.0, triggered_environment.entity("target").scalars["health"])
        self.assertEqual(10.0, missed_environment.entity("target").scalars["health"])

    def test_stun_blocks_affordances_until_effect_expiry(self) -> None:
        wait = ActionSpec(
            action_key="wait",
            targeting=TargetingSpec(kind=TargetKind.NONE),
            phases=(ActionPhase(kind=PhaseKind.ACTIVE, duration_ms=0),),
        )
        stun = ActionSpec(
            action_key="stun",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=10.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        ApplyEffect(
                            SubjectRef.TARGET,
                            "stunned",
                            400,
                            stacking_key="Stun",
                            tags=("control.stun",),
                        ),
                    ),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((stun, wait)),
            (
                actor("a", "red", Vector2(0.0, 0.0), ("stun",)),
                actor("b", "blue", Vector2(1.0, 0.0), ("wait",)),
            ),
            seed=1,
        )
        decision = action_for(
            environment, "a", "stun", target_id="b", correlation_id="stun-b"
        )

        environment.step((decision,))

        self.assertEqual((), environment.exchange("b").affordances.affordances)
        environment.step()
        self.assertEqual(1, len(environment.exchange("b").affordances.affordances))

    def test_stun_immunity_prevents_new_stun_effect(self) -> None:
        stun = ActionSpec(
            action_key="stun",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=10.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        ApplyEffect(
                            SubjectRef.TARGET,
                            "stunned",
                            1_000,
                            stacking_key="Stun",
                            tags=("control.stun",),
                        ),
                    ),
                ),
            ),
        )
        immune_target = actor("b", "blue", Vector2(1.0, 0.0), ())
        immune_target.effects["NoStun"] = ActiveEffectState(
            effect_key="stun_immunity",
            source_entity_id="b",
            magnitude=1.0,
            expires_at_ms=5_000,
            stacking_key="NoStun",
            tags={"immunity.stun"},
        )
        environment = ReferenceEnvironment(
            ActionCatalog((stun,)),
            (
                actor("a", "red", Vector2(0.0, 0.0), ("stun",)),
                immune_target,
            ),
            seed=1,
        )
        decision = action_for(
            environment, "a", "stun", target_id="b", correlation_id="immune"
        )

        events = environment.step((decision,)).events

        self.assertNotIn("Stun", environment.entity("b").effects)
        self.assertFalse(
            any(
                event.kind == EventKind.EFFECT_ADDED and "effect.stunned" in event.tags
                for event in events
            )
        )

    def test_joint_actions_resolve_from_the_same_alive_set(self) -> None:
        attack = ActionSpec(
            action_key="attack",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=3.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(DealDamage(SubjectRef.TARGET, 10.0, "crush"),),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((attack,)),
            (
                actor("a", "red", Vector2(0.0, 0.0), ("attack",)),
                actor("b", "blue", Vector2(1.0, 0.0), ("attack",)),
            ),
            seed=1,
            terminate_on_last_team=True,
        )
        decision_a = action_for(
            environment, "a", "attack", target_id="b", correlation_id="a-attacks"
        )
        decision_b = action_for(
            environment, "b", "attack", target_id="a", correlation_id="b-attacks"
        )

        result = environment.step((decision_b, decision_a))

        self.assertFalse(environment.entity("a").alive)
        self.assertFalse(environment.entity("b").alive)
        self.assertEqual(("a:1", "b:1"), result.life_terminated)
        self.assertTrue(result.world_terminated)
        self.assertEqual(
            2,
            sum(event.kind == EventKind.DAMAGE_APPLIED for event in result.events),
        )

    def test_projectile_uses_virtual_travel_time(self) -> None:
        projectile = ActionSpec(
            action_key="bolt",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=120.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    delivery=DeliverySpec(
                        DeliveryKind.PROJECTILE,
                        projectile_speed_units_per_second=60.0,
                    ),
                    effects=(DealDamage(SubjectRef.TARGET, 4.0, "cold"),),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((projectile,)),
            (
                actor("caster", "red", Vector2(0.0, 0.0), ("bolt",)),
                actor("target", "blue", Vector2(60.0, 0.0), ()),
            ),
            seed=2,
        )
        decision = action_for(
            environment, "caster", "bolt", target_id="target", correlation_id="bolt-1"
        )

        environment.step((decision,))
        for _ in range(3):
            environment.step()
        self.assertEqual(10.0, environment.entity("target").scalars["health"])

        result = environment.step()

        self.assertEqual(6.0, environment.entity("target").scalars["health"])
        damage = next(event for event in result.events if event.kind == EventKind.DAMAGE_APPLIED)
        self.assertEqual(1_000, damage.sim_time_ms)

    def test_snapshot_restores_pending_timeline_for_exact_replay(self) -> None:
        projectile = ActionSpec(
            action_key="bolt",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=120.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    delivery=DeliverySpec(
                        DeliveryKind.PROJECTILE,
                        projectile_speed_units_per_second=50.0,
                    ),
                    effects=(DealDamage(SubjectRef.TARGET, 3.0, "cold"),),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((projectile,)),
            (
                actor("caster", "red", Vector2(0.0, 0.0), ("bolt",)),
                actor("target", "blue", Vector2(20.0, 0.0), ()),
            ),
            seed=3,
        )
        decision = action_for(
            environment, "caster", "bolt", target_id="target", correlation_id="bolt-1"
        )
        environment.step((decision,))
        snapshot = environment.snapshot()

        expected_events = environment.step()
        expected_state = environment.snapshot()
        environment.restore(snapshot)
        actual_events = environment.step()

        self.assertEqual(expected_events, actual_events)
        self.assertEqual(expected_state, environment.snapshot())

    def test_snapshot_replays_seeded_uniform_damage_exactly(self) -> None:
        attack = ActionSpec(
            action_key="variable-attack",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=3.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        DealDamage(
                            SubjectRef.TARGET,
                            UniformAmount(4.0, 9.0),
                            "crush",
                        ),
                    ),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((attack,)),
            (
                actor("a", "red", Vector2(0.0, 0.0), ("variable-attack",)),
                actor("b", "blue", Vector2(1.0, 0.0), ()),
            ),
            seed=91,
        )
        snapshot = environment.snapshot()
        decision = action_for(
            environment,
            "a",
            "variable-attack",
            target_id="b",
            correlation_id="variable-1",
        )

        expected_events = environment.step((decision,))
        expected_state = environment.snapshot()
        damage_event = next(
            event for event in expected_events.events if event.kind == EventKind.DAMAGE_APPLIED
        )
        requested = next(item.value for item in damage_event.scalars if item.name == "requested")
        environment.restore(snapshot)
        actual_events = environment.step((decision,))

        self.assertGreaterEqual(requested, 4.0)
        self.assertLess(requested, 9.0)
        self.assertEqual(expected_events, actual_events)
        self.assertEqual(expected_state, environment.snapshot())

    def test_snapshot_replays_seeded_weighted_damage_exactly(self) -> None:
        attack = ActionSpec(
            action_key="observed-attack",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=3.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        DealDamage(
                            SubjectRef.TARGET,
                            WeightedAmount(((5.0, 1), (17.0, 2))),
                            "unknown",
                        ),
                    ),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((attack,)),
            (
                actor("a", "red", Vector2(0.0, 0.0), ("observed-attack",)),
                actor("b", "blue", Vector2(1.0, 0.0), ()),
            ),
            seed=91,
        )
        snapshot = environment.snapshot()
        decision = action_for(
            environment,
            "a",
            "observed-attack",
            target_id="b",
            correlation_id="observed-1",
        )

        expected_events = environment.step((decision,))
        expected_state = environment.snapshot()
        damage_event = next(
            event for event in expected_events.events if event.kind == EventKind.DAMAGE_APPLIED
        )
        requested = next(item.value for item in damage_event.scalars if item.name == "requested")
        environment.restore(snapshot)

        self.assertIn(requested, (5.0, 17.0))
        self.assertEqual(expected_events, environment.step((decision,)))
        self.assertEqual(expected_state, environment.snapshot())

    def test_stale_decision_is_rejected_without_execution(self) -> None:
        wait = ActionSpec(
            action_key="wait",
            targeting=TargetingSpec(kind=TargetKind.NONE),
            phases=(ActionPhase(kind=PhaseKind.ACTIVE, duration_ms=0),),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((wait,)),
            (actor("bot", "red", Vector2(0.0, 0.0), ("wait",)),),
            seed=4,
        )
        decision = action_for(environment, "bot", "wait", correlation_id="old")
        environment.step()

        result = environment.step((decision,))

        self.assertEqual(1, len(result.events))
        self.assertEqual(EventKind.ACTION_REJECTED, result.events[0].kind)

    def test_cost_and_cooldown_change_future_affordances(self) -> None:
        cast = ActionSpec(
            action_key="cast",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=10.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(DealDamage(SubjectRef.TARGET, 1.0, "magic"),),
                ),
            ),
            costs=(ResourceCost("mana", 5.0),),
            cooldown_ms=400,
        )
        environment = ReferenceEnvironment(
            ActionCatalog((cast,)),
            (
                actor("caster", "red", Vector2(0.0, 0.0), ("cast",)),
                actor("target", "blue", Vector2(1.0, 0.0), ()),
            ),
            seed=5,
        )
        decision = action_for(
            environment, "caster", "cast", target_id="target", correlation_id="cast-1"
        )

        environment.step((decision,))

        self.assertEqual(5.0, environment.entity("caster").scalars["mana"])
        self.assertEqual((), environment.exchange("caster").affordances.affordances)
        environment.step()
        self.assertEqual(1, len(environment.exchange("caster").affordances.affordances))

    def test_movement_uses_bound_direction_and_phase_duration(self) -> None:
        move = ActionSpec(
            action_key="move",
            targeting=TargetingSpec(kind=TargetKind.DIRECTION),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=200,
                    effects=(MoveEntity(SubjectRef.ACTOR, MovementMode.WALK),),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((move,)),
            (actor("bot", "red", Vector2(0.0, 0.0), ("move",)),),
            seed=6,
        )
        decision = action_for(
            environment,
            "bot",
            "move",
            direction=Vector2(1.0, 0.0),
            correlation_id="move-1",
        )

        environment.step((decision,))

        self.assertEqual(Vector2(2.0, 0.0), environment.entity("bot").position)

    def test_push_moves_the_target_away_from_the_actor(self) -> None:
        push = ActionSpec(
            action_key="push",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=3.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(MoveEntity(SubjectRef.TARGET, MovementMode.PUSH, distance=2.0),),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((push,)),
            (
                actor("caster", "red", Vector2(0.0, 0.0), ("push",)),
                actor("target", "blue", Vector2(1.0, 0.0), ()),
            ),
            seed=61,
        )
        decision = action_for(
            environment, "caster", "push", target_id="target", correlation_id="push-1"
        )

        environment.step((decision,))

        self.assertEqual(Vector2(3.0, 0.0), environment.entity("target").position)

    def test_effect_expiry_is_scheduled_at_exact_virtual_time(self) -> None:
        stealth = ActionSpec(
            action_key="stealth",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        ApplyEffect(
                            SubjectRef.ACTOR,
                            "concealed",
                            duration_ms=300,
                            tags=("visibility.concealed",),
                        ),
                    ),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((stealth,)),
            (actor("bot", "red", Vector2(0.0, 0.0), ("stealth",)),),
            seed=7,
        )
        decision = action_for(environment, "bot", "stealth", correlation_id="stealth-1")

        environment.step((decision,))
        self.assertIn("concealed", environment.entity("bot").effective_tags)
        result = environment.step()

        self.assertNotIn("concealed", environment.entity("bot").effective_tags)
        removed = next(event for event in result.events if event.kind == EventKind.EFFECT_REMOVED)
        self.assertEqual(300, removed.sim_time_ms)

    def test_item_transfer_and_objective_progress_use_bound_entities(self) -> None:
        transfer = ActionSpec(
            action_key="transfer",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ALLY,),
                maximum_range=2.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(TransferItem(SubjectRef.ACTOR, SubjectRef.TARGET),),
                ),
            ),
        )
        capture = ActionSpec(
            action_key="capture",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.NEUTRAL,),
                maximum_range=2.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(ModifyObjective(SubjectRef.OBJECTIVE, 0.25),),
                ),
            ),
        )
        objective = EntityState(
            entity_id="mine",
            life_id="mine:1",
            kind=EntityKind.OBJECTIVE,
            team_id=None,
            position=Vector2(1.0, 0.0),
            scalars={"objective_progress": 0.0},
            maximums={"objective_progress": 1.0},
        )
        environment = ReferenceEnvironment(
            ActionCatalog((transfer, capture)),
            (
                actor(
                    "giver",
                    "red",
                    Vector2(0.0, 0.0),
                    ("transfer", "capture"),
                    inventory={"potion": 2.0},
                ),
                actor("ally", "red", Vector2(1.0, 0.0), ()),
                objective,
            ),
            seed=8,
        )
        transfer_decision = action_for(
            environment, "giver", "transfer", target_id="ally", correlation_id="transfer-1"
        )
        environment.step((transfer_decision,))
        capture_decision = action_for(
            environment, "giver", "capture", target_id="mine", correlation_id="capture-1"
        )

        environment.step((capture_decision,))

        self.assertEqual(0.0, environment.entity("giver").inventory["potion"])
        self.assertEqual(2.0, environment.entity("ally").inventory["potion"])
        self.assertEqual(0.25, environment.entity("mine").scalars["objective_progress"])


if __name__ == "__main__":
    unittest.main()
