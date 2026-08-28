import unittest

from shadowbane_lab.combat import StackPriority, triangular_roll
from shadowbane_lab.protocol import EntityKind, EventKind, Relation, TargetKind, Vector2
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    ActiveEffectState,
    ApplyEffect,
    AttackGate,
    AttackKind,
    DealDamage,
    DeterministicRandom,
    EntityState,
    PeriodicPulse,
    PhaseKind,
    ReferenceEnvironment,
    ResourceImmunity,
    RestoreResource,
    SubjectRef,
    TargetingSpec,
    TriangularAmount,
)


def _actor(
    entity_id: str,
    team_id: str,
    action_keys: tuple[str, ...],
    scalars: dict[str, float],
) -> EntityState:
    health = scalars["health"]
    return EntityState(
        entity_id=entity_id,
        life_id=f"{entity_id}:1",
        kind=EntityKind.ACTOR,
        team_id=team_id,
        position=Vector2(0.0 if team_id == "red" else 1.0, 0.0),
        scalars=scalars,
        maximums={"health": health},
        action_keys=action_keys,
    )


def _attack_action(effect: DealDamage, *, passives: tuple[str, ...] = ()) -> ActionSpec:
    return ActionSpec(
        action_key="power",
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
                    AttackGate(
                        attack_key="test-power",
                        kind=AttackKind.POWER,
                        attack_rating_key="attack.power",
                        defense_rating_key="defense",
                        effects=(effect,),
                        passive_defense_keys=passives,
                    ),
                ),
            ),
        ),
    )


def _decision(environment: ReferenceEnvironment, correlation_id: str = "attack"):
    exchange = environment.exchange("caster")
    affordance = exchange.affordances.affordances[0]
    return exchange.decision(affordance.affordance_id, correlation_id)


class ShadowbaneCombatRuntimeTests(unittest.TestCase):
    def test_periodic_effect_ticks_on_virtual_time_and_snapshot_replays_exactly(self) -> None:
        damage = DealDamage(
            SubjectRef.TARGET,
            5.0,
            "poison",
            source_key="test-dot",
        )
        action = ActionSpec(
            action_key="dot",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=3.0,
            ),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    (
                        ApplyEffect(
                            SubjectRef.TARGET,
                            "poisoned",
                            600,
                            modifiers=(
                                PeriodicPulse(
                                    "poison",
                                    interval_ms=200,
                                    tick_count=3,
                                    effects=(damage,),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((action,)),
            (
                _actor("caster", "red", ("dot",), {"health": 50.0}),
                _actor("target", "blue", (), {"health": 50.0}),
            ),
            seed=4,
        )

        first = environment.step((_decision(environment, "dot"),))
        snapshot = environment.snapshot()
        expected_second = environment.step()
        expected_third = environment.step()
        expected_snapshot = environment.snapshot()

        self.assertEqual(45.0, snapshot.entities[1].scalars[0][1])
        self.assertEqual(
            [200],
            [
                event.sim_time_ms
                for event in first.events
                if event.kind == EventKind.EFFECT_PULSED
            ],
        )
        self.assertNotIn("poisoned", environment.entity("target").effects)

        environment.restore(snapshot)
        actual_second = environment.step()
        actual_third = environment.step()

        self.assertEqual(expected_second, actual_second)
        self.assertEqual(expected_third, actual_third)
        self.assertEqual(expected_snapshot, environment.snapshot())
        self.assertEqual(35.0, environment.entity("target").scalars["health"])
        pulse_times = [
            event.sim_time_ms
            for batch in (first, actual_second, actual_third)
            for event in batch.events
            if event.kind == EventKind.EFFECT_PULSED
        ]
        self.assertEqual([200, 400, 600], pulse_times)

    def test_replacing_periodic_effect_invalidates_old_scheduled_pulses(self) -> None:
        action = ActionSpec(
            action_key="dot",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=3.0,
            ),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    (
                        ApplyEffect(
                            SubjectRef.TARGET,
                            "poisoned",
                            600,
                            stacking_key="poison",
                            modifiers=(
                                PeriodicPulse(
                                    "poison",
                                    interval_ms=200,
                                    tick_count=3,
                                    effects=(
                                        DealDamage(
                                            SubjectRef.TARGET,
                                            5.0,
                                            "poison",
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((action,)),
            (
                _actor("caster", "red", ("dot",), {"health": 50.0}),
                _actor("target", "blue", (), {"health": 50.0}),
            ),
            seed=5,
        )

        environment.step((_decision(environment, "first"),))
        second = environment.step((_decision(environment, "replacement"),))

        self.assertEqual(40.0, environment.entity("target").scalars["health"])
        self.assertEqual(
            1,
            sum(event.kind == EventKind.EFFECT_PULSED for event in second.events),
        )

    def test_ranked_resource_immunity_blocks_only_equal_or_weaker_restoration(self) -> None:
        mantle = ActionSpec(
            action_key="mantle",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=3.0,
            ),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    (
                        ApplyEffect(
                            SubjectRef.TARGET,
                            "healing-lock",
                            30_000,
                            modifiers=(ResourceImmunity("health"),),
                            trains=40,
                        ),
                    ),
                ),
            ),
        )

        def heal(action_key: str, trains: int) -> ActionSpec:
            return ActionSpec(
                action_key=action_key,
                targeting=TargetingSpec(
                    kind=TargetKind.ENTITY,
                    allowed_relations=(Relation.SELF, Relation.ALLY),
                    maximum_range=3.0,
                ),
                phases=(
                    ActionPhase(
                        PhaseKind.ACTIVE,
                        0,
                        (
                            RestoreResource(
                                SubjectRef.TARGET,
                                "health",
                                25.0,
                                power_trains=trains,
                            ),
                        ),
                    ),
                ),
            )

        target = _actor("target", "blue", (), {"health": 100.0})
        target.maximums["health"] = 200.0
        environment = ReferenceEnvironment(
            ActionCatalog((mantle, heal("weak-heal", 40), heal("strong-heal", 41))),
            (
                _actor("assassin", "red", ("mantle",), {"health": 200.0}),
                _actor(
                    "healer",
                    "blue",
                    ("weak-heal", "strong-heal"),
                    {"health": 200.0},
                ),
                target,
            ),
            seed=1,
        )

        def decision(actor_id: str, action_key: str, target_id: str):
            exchange = environment.exchange(actor_id)
            affordance = next(
                item
                for item in exchange.affordances.affordances
                if item.action_key == action_key
                and item.binding.target_entity_id == target_id
            )
            return exchange.decision(affordance.affordance_id, action_key)

        environment.step((decision("assassin", "mantle", "target"),))
        self.assertIn(
            "immunity.resource.health",
            environment.entity("target").effective_tags,
        )
        blocked = environment.step((decision("healer", "weak-heal", "target"),))

        self.assertEqual(100.0, environment.entity("target").scalars["health"])
        blocked_event = next(
            event
            for event in blocked.events
            if event.kind == EventKind.RESOURCE_RESTORED
        )
        self.assertIn("outcome.blocked_by_resource_immunity", blocked_event.tags)

        environment.step((decision("healer", "strong-heal", "target"),))

        self.assertEqual(125.0, environment.entity("target").scalars["health"])

    def test_triangular_amount_consumes_two_seeded_rolls(self) -> None:
        action = ActionSpec(
            action_key="strike",
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
                            TriangularAmount(40.0, 80.0),
                            "crush",
                        ),
                    ),
                ),
            ),
        )
        expected_random = DeterministicRandom(7)
        expected = triangular_roll(
            40.0,
            80.0,
            expected_random.random(),
            expected_random.random(),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((action,)),
            (
                _actor("caster", "red", ("strike",), {"health": 200.0}),
                _actor("target", "blue", (), {"health": 200.0}),
            ),
            seed=7,
        )

        result = environment.step((_decision(environment),))

        damage = next(event for event in result.events if event.kind == EventKind.DAMAGE_APPLIED)
        requested = next(item.value for item in damage.scalars if item.name == "requested")
        self.assertEqual(expected, requested)

    def test_power_hit_gate_applies_resistance_and_armor_piercing(self) -> None:
        action = _attack_action(
            DealDamage(
                SubjectRef.TARGET,
                100.0,
                "mental",
                uses_resistance=True,
                power_trains=40,
            )
        )
        environment = ReferenceEnvironment(
            ActionCatalog((action,)),
            (
                _actor(
                    "caster",
                    "red",
                    ("power",),
                    {"health": 200.0, "attack.power": 900.0, "armor_piercing": 0.1},
                ),
                _actor(
                    "target",
                    "blue",
                    (),
                    {"health": 200.0, "defense": 1_000.0, "resist.mental": 25.0},
                ),
            ),
            seed=2,
        )

        result = environment.step((_decision(environment),))

        attack = next(event for event in result.events if event.kind == EventKind.ATTACK_RESOLVED)
        self.assertIn("outcome.hit", attack.tags)
        damage = next(event for event in result.events if event.kind == EventKind.DAMAGE_APPLIED)
        mitigated = next(item.value for item in damage.scalars if item.name == "mitigated")
        self.assertAlmostEqual(85.0, mitigated, places=4)
        self.assertAlmostEqual(115.0, environment.entity("target").scalars["health"], places=4)

    def test_miss_and_passive_defense_each_suppress_nested_damage(self) -> None:
        action = _attack_action(
            DealDamage(SubjectRef.TARGET, 100.0, "mental"),
            passives=("passive.dodge",),
        )
        entities = (
            _actor(
                "caster",
                "red",
                ("power",),
                {"health": 200.0, "attack.power": 900.0},
            ),
            _actor(
                "target",
                "blue",
                (),
                {"health": 200.0, "defense": 1_000.0, "passive.dodge": 75.0},
            ),
        )
        miss_environment = ReferenceEnvironment(ActionCatalog((action,)), entities, seed=0)
        miss = miss_environment.step((_decision(miss_environment, "miss"),))
        self.assertFalse(any(event.kind == EventKind.DAMAGE_APPLIED for event in miss.events))

        passive_environment = ReferenceEnvironment(
            ActionCatalog((action,)),
            tuple(entity.clone() for entity in entities),
            seed=7,
        )
        passive = passive_environment.step((_decision(passive_environment, "passive"),))
        passive_event = next(
            event
            for event in passive.events
            if event.kind == EventKind.PASSIVE_DEFENSE_RESOLVED
        )
        self.assertIn("outcome.triggered", passive_event.tags)
        self.assertFalse(any(event.kind == EventKind.DAMAGE_APPLIED for event in passive.events))

    def test_effect_stack_priority_blocks_weaker_same_order_effect(self) -> None:
        action = ActionSpec(
            action_key="debuff",
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
                        ApplyEffect(
                            SubjectRef.TARGET,
                            "incoming",
                            1_000,
                            stacking_key="MentalDebuff",
                            stack_order=2,
                            trains=20,
                            stack_priority=StackPriority.GREATER_THAN_OR_EQUAL,
                        ),
                    ),
                ),
            ),
        )
        target = _actor("target", "blue", (), {"health": 200.0})
        target.effects["MentalDebuff"] = ActiveEffectState(
            effect_key="existing",
            source_entity_id="other",
            magnitude=1.0,
            expires_at_ms=5_000,
            stacking_key="MentalDebuff",
            stack_order=2,
            trains=40,
            stack_priority=StackPriority.GREATER_THAN_OR_EQUAL,
        )
        environment = ReferenceEnvironment(
            ActionCatalog((action,)),
            (_actor("caster", "red", ("debuff",), {"health": 200.0}), target),
            seed=1,
        )

        result = environment.step((_decision(environment, "debuff"),))

        active = environment.entity("target").effects["MentalDebuff"]
        self.assertEqual("existing", active.effect_key)
        blocked = next(event for event in result.events if event.kind == EventKind.EFFECT_BLOCKED)
        self.assertIn("reason.stack_priority", blocked.tags)

    def test_explicit_damage_and_stun_flags_interrupt_pending_actions(self) -> None:
        for trigger, incoming_effect in (
            ("damage", DealDamage(SubjectRef.TARGET, 1.0, "mental")),
            (
                "stun",
                ApplyEffect(
                    SubjectRef.TARGET,
                    "stunned",
                    500,
                    tags=("control.stun",),
                ),
            ),
        ):
            with self.subTest(trigger=trigger):
                channel = ActionSpec(
                    action_key="channel",
                    targeting=TargetingSpec(kind=TargetKind.SELF),
                    phases=(
                        ActionPhase(
                            kind=PhaseKind.ACTIVE,
                            duration_ms=1_000,
                            interruptible=True,
                        ),
                    ),
                    cancel_on_damage=trigger == "damage",
                    cancel_on_stun=trigger == "stun",
                )
                interrupt = ActionSpec(
                    action_key="interrupt",
                    targeting=TargetingSpec(
                        kind=TargetKind.ENTITY,
                        allowed_relations=(Relation.ENEMY,),
                        maximum_range=3.0,
                    ),
                    phases=(
                        ActionPhase(
                            kind=PhaseKind.ACTIVE,
                            duration_ms=0,
                            effects=(incoming_effect,),
                        ),
                    ),
                )
                environment = ReferenceEnvironment(
                    ActionCatalog((channel, interrupt)),
                    (
                        _actor("caster", "red", ("channel",), {"health": 200.0}),
                        _actor("attacker", "blue", ("interrupt",), {"health": 200.0}),
                    ),
                    seed=1,
                )
                caster_exchange = environment.exchange("caster")
                caster_decision = caster_exchange.decision(
                    caster_exchange.affordances.affordances[0].affordance_id,
                    f"channel-{trigger}",
                )
                attacker_exchange = environment.exchange("attacker")
                attacker_decision = attacker_exchange.decision(
                    attacker_exchange.affordances.affordances[0].affordance_id,
                    f"interrupt-{trigger}",
                )

                result = environment.step((caster_decision, attacker_decision))

                interrupted = next(
                    event
                    for event in result.events
                    if event.kind == EventKind.ACTION_INTERRUPTED
                )
                self.assertEqual(f"channel-{trigger}", interrupted.correlation_id)
                self.assertIn(f"reason.{trigger}", interrupted.tags)
                self.assertEqual(0, environment.entity("caster").busy_until_ms)


if __name__ == "__main__":
    unittest.main()
