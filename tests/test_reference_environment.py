import unittest

from shadowbane_lab.protocol import EntityKind, EventKind, Relation, TargetKind, Vector2
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    ActionTriggerSpec,
    ActiveEffectState,
    ApplyEffect,
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
    RestoreResource,
    SubjectRef,
    TargetingSpec,
    TransferItem,
    TriggerConsumption,
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
        decision = action_for(environment, "a", "stun", target_id="b", correlation_id="stun-b")

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
        decision = action_for(environment, "a", "stun", target_id="b", correlation_id="immune")

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
                    effects=(DealDamage(SubjectRef.TARGET, 10.0, "physical"),),
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
                    effects=(DealDamage(SubjectRef.TARGET, 1.0, "arcane"),),
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

    def test_ranked_restore_block_allows_only_higher_rank_healing(self) -> None:
        block_healing = ActionSpec(
            action_key="block_healing",
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
                            "healing_block",
                            5_000,
                            magnitude=20.0,
                            stacking_key="HealingBlock",
                            tags=(
                                "healing.block",
                                "resource.restore.block.health",
                            ),
                        ),
                    ),
                ),
            ),
        )
        weak_heal = ActionSpec(
            action_key="weak_heal",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        RestoreResource(
                            SubjectRef.ACTOR,
                            "health",
                            5.0,
                            effect_rank=20,
                        ),
                    ),
                ),
            ),
        )
        strong_heal = ActionSpec(
            action_key="strong_heal",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        RestoreResource(
                            SubjectRef.ACTOR,
                            "health",
                            5.0,
                            effect_rank=21,
                        ),
                    ),
                ),
            ),
        )
        target = actor(
            "target",
            "blue",
            Vector2(1.0, 0.0),
            ("weak_heal", "strong_heal"),
            health=5.0,
        )
        target.maximums["health"] = 10.0
        environment = ReferenceEnvironment(
            ActionCatalog((block_healing, weak_heal, strong_heal)),
            (
                actor("blocker", "red", Vector2(0.0, 0.0), ("block_healing",)),
                target,
            ),
            seed=51,
        )
        block = action_for(
            environment,
            "blocker",
            "block_healing",
            target_id="target",
            correlation_id="block",
        )
        environment.step((block,))
        weak = action_for(environment, "target", "weak_heal", correlation_id="weak")

        blocked = environment.step((weak,))

        self.assertEqual(5.0, environment.entity("target").scalars["health"])
        restored = next(
            event for event in blocked.events if event.kind == EventKind.RESOURCE_RESTORED
        )
        scalars = {item.name: item.value for item in restored.scalars}
        self.assertEqual(0.0, scalars["effective"])
        self.assertEqual(20.0, scalars["blocking_rank"])
        self.assertIn("reason.blocked_by_rank", restored.tags)

        strong = action_for(environment, "target", "strong_heal", correlation_id="strong")
        environment.step((strong,))

        self.assertEqual(10.0, environment.entity("target").scalars["health"])

    def test_armed_payload_waits_for_and_is_consumed_by_qualifying_action(self) -> None:
        trigger = ActionTriggerSpec(
            trigger_key="armed_strike",
            payload=(DealDamage(SubjectRef.TARGET, 20.0, "physical"),),
            required_action_tags=("attack", "weapon", "melee"),
            forbidden_action_tags=("setup",),
            consume_on=TriggerConsumption.ACTION_START,
            tags=("weapon_power",),
        )
        arm = ActionSpec(
            action_key="arm",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        ApplyEffect(
                            SubjectRef.ACTOR,
                            "armed_strike",
                            5_000,
                            stacking_key="NextWeaponPower",
                            tags=("trigger.armed",),
                        ),
                    ),
                ),
            ),
            armed_trigger=trigger,
            tags=("setup", "weapon_power", "armed_trigger"),
        )
        spell = ActionSpec(
            action_key="spell",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=10.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(DealDamage(SubjectRef.TARGET, 2.0, "cold"),),
                ),
            ),
            tags=("attack", "spell"),
        )
        weapon = ActionSpec(
            action_key="weapon",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=10.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(DealDamage(SubjectRef.TARGET, 3.0, "physical"),),
                ),
            ),
            tags=("attack", "weapon", "melee"),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((arm, spell, weapon)),
            (
                actor(
                    "attacker",
                    "red",
                    Vector2(0.0, 0.0),
                    ("arm", "spell", "weapon"),
                ),
                actor("target", "blue", Vector2(1.0, 0.0), (), health=50.0),
            ),
            seed=52,
        )

        arm_decision = action_for(environment, "attacker", "arm", correlation_id="arm")
        environment.step((arm_decision,))
        self.assertIn("NextWeaponPower", environment.entity("attacker").effects)

        spell_decision = action_for(
            environment,
            "attacker",
            "spell",
            target_id="target",
            correlation_id="spell",
        )
        environment.step((spell_decision,))
        self.assertEqual(48.0, environment.entity("target").scalars["health"])
        self.assertIn("NextWeaponPower", environment.entity("attacker").effects)

        weapon_decision = action_for(
            environment,
            "attacker",
            "weapon",
            target_id="target",
            correlation_id="weapon-1",
        )
        triggered = environment.step((weapon_decision,))
        self.assertEqual(25.0, environment.entity("target").scalars["health"])
        self.assertNotIn("NextWeaponPower", environment.entity("attacker").effects)
        self.assertEqual(
            1, sum(event.kind == EventKind.TRIGGER_FIRED for event in triggered.events)
        )

        second_weapon = action_for(
            environment,
            "attacker",
            "weapon",
            target_id="target",
            correlation_id="weapon-2",
        )
        environment.step((second_weapon,))
        self.assertEqual(22.0, environment.entity("target").scalars["health"])

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
