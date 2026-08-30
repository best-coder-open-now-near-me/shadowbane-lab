import unittest

from shadowbane_lab.protocol import EntityKind, Relation, TargetKind, Vector2
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    ApplyEffect,
    EffectOutcomeKind,
    EntityState,
    ModifyTag,
    OutcomeConditional,
    PhaseKind,
    ReferenceEnvironment,
    SubjectRef,
    TagOperation,
    TargetingSpec,
)


def actor(
    entity_id: str,
    team_id: str,
    action_keys: tuple[str, ...],
    *,
    tags: tuple[str, ...] = (),
) -> EntityState:
    return EntityState(
        entity_id=entity_id,
        life_id=f"{entity_id}:1",
        kind=EntityKind.ACTOR,
        team_id=team_id,
        position=Vector2(0.0 if team_id == "red" else 1.0, 0.0),
        scalars={"health": 100.0, "mana": 100.0, "move_speed": 10.0},
        maximums={"health": 100.0, "mana": 100.0},
        tags=set(tags),
        action_keys=action_keys,
    )


def hostile_targeting() -> TargetingSpec:
    return TargetingSpec(
        kind=TargetKind.ENTITY,
        allowed_relations=(Relation.ENEMY,),
        maximum_range=10.0,
    )


def choose(environment: ReferenceEnvironment, action_key: str, correlation_id: str):
    exchange = environment.exchange("caster")
    affordance = next(
        value
        for value in exchange.affordances.affordances
        if value.action_key == action_key and value.binding.target_entity_id == "target"
    )
    return exchange.decision(affordance.affordance_id, correlation_id)


def stun_condition() -> ApplyEffect:
    return ApplyEffect(
        subject=SubjectRef.TARGET,
        effect_key="effect.stun",
        duration_ms=1_000,
        tags=("control.stun",),
    )


def conditional_stun_action() -> ActionSpec:
    return ActionSpec(
        action_key="conditional-stun",
        targeting=hostile_targeting(),
        phases=(
            ActionPhase(
                PhaseKind.ACTIVE,
                0,
                effects=(
                    OutcomeConditional(
                        conditional_key="stun-followups",
                        condition=stun_condition(),
                        outcomes=(EffectOutcomeKind.APPLIED,),
                        effects=(
                            ModifyTag(
                                SubjectRef.TARGET,
                                "movement.flight",
                                TagOperation.REMOVE,
                            ),
                            ApplyEffect(
                                subject=SubjectRef.TARGET,
                                effect_key="effect.stun-immunity",
                                duration_ms=3_000,
                                tags=("immunity.stun",),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


class EffectOutcomeTests(unittest.TestCase):
    def test_applied_condition_runs_followups(self) -> None:
        action = conditional_stun_action()
        environment = ReferenceEnvironment(
            ActionCatalog((action,)),
            (
                actor("caster", "red", (action.action_key,)),
                actor("target", "blue", (), tags=("movement.flight",)),
            ),
            seed=1,
        )

        result = environment.step((choose(environment, action.action_key, "cast-1"),))
        target = environment.entity("target")

        self.assertIn("effect.stun", target.effects)
        self.assertIn("effect.stun-immunity", target.effects)
        self.assertNotIn("movement.flight", target.tags)
        conditional = next(
            event for event in result.events if event.kind == "effect_outcome_resolved"
        )
        self.assertIn("outcome.applied", conditional.tags)
        self.assertIn("branch.effects", conditional.tags)

    def test_blocked_condition_does_not_run_followups(self) -> None:
        action = conditional_stun_action()
        environment = ReferenceEnvironment(
            ActionCatalog((action,)),
            (
                actor("caster", "red", (action.action_key,)),
                actor(
                    "target",
                    "blue",
                    (),
                    tags=("movement.flight", "immunity.stun"),
                ),
            ),
            seed=2,
        )

        result = environment.step((choose(environment, action.action_key, "cast-1"),))
        target = environment.entity("target")

        self.assertNotIn("effect.stun", target.effects)
        self.assertNotIn("effect.stun-immunity", target.effects)
        self.assertIn("movement.flight", target.tags)
        conditional = next(
            event for event in result.events if event.kind == "effect_outcome_resolved"
        )
        self.assertIn("outcome.blocked_immunity", conditional.tags)
        self.assertIn("branch.else_effects", conditional.tags)

    def test_refresh_outcome_can_select_its_own_branch(self) -> None:
        initial = ActionSpec(
            action_key="initial-stun",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    effects=(stun_condition(),),
                ),
            ),
        )
        refresh = ActionSpec(
            action_key="refresh-stun",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    effects=(
                        OutcomeConditional(
                            conditional_key="refresh-only",
                            condition=stun_condition(),
                            outcomes=(EffectOutcomeKind.REFRESHED,),
                            effects=(
                                ModifyTag(
                                    SubjectRef.TARGET,
                                    "marker.refreshed",
                                    TagOperation.ADD,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((initial, refresh)),
            (
                actor(
                    "caster",
                    "red",
                    (initial.action_key, refresh.action_key),
                ),
                actor("target", "blue", ()),
            ),
            seed=3,
        )
        environment.step((choose(environment, initial.action_key, "initial"),))
        result = environment.step((choose(environment, refresh.action_key, "refresh"),))

        self.assertIn("marker.refreshed", environment.entity("target").tags)
        conditional = next(
            event for event in result.events if event.kind == "effect_outcome_resolved"
        )
        self.assertIn("outcome.refreshed", conditional.tags)

    def test_else_branch_is_explicit(self) -> None:
        action = ActionSpec(
            action_key="else-branch",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    effects=(
                        OutcomeConditional(
                            conditional_key="blocked-marker",
                            condition=stun_condition(),
                            outcomes=(EffectOutcomeKind.APPLIED,),
                            effects=(
                                ModifyTag(
                                    SubjectRef.TARGET,
                                    "marker.applied",
                                    TagOperation.ADD,
                                ),
                            ),
                            else_effects=(
                                ModifyTag(
                                    SubjectRef.TARGET,
                                    "marker.blocked",
                                    TagOperation.ADD,
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
                actor("caster", "red", (action.action_key,)),
                actor("target", "blue", (), tags=("immunity.stun",)),
            ),
            seed=4,
        )

        environment.step((choose(environment, action.action_key, "cast"),))

        self.assertIn("marker.blocked", environment.entity("target").tags)
        self.assertNotIn("marker.applied", environment.entity("target").tags)

    def test_generic_immunity_tags_block_non_stun_effects(self) -> None:
        action = ActionSpec(
            action_key="generic-immunity",
            targeting=hostile_targeting(),
            phases=(
                ActionPhase(
                    PhaseKind.ACTIVE,
                    0,
                    effects=(
                        OutcomeConditional(
                            conditional_key="root",
                            condition=ApplyEffect(
                                subject=SubjectRef.TARGET,
                                effect_key="effect.root",
                                duration_ms=1_000,
                                tags=("control.root",),
                                immunity_tags=("immunity.root",),
                            ),
                            outcomes=(EffectOutcomeKind.BLOCKED_IMMUNITY,),
                            effects=(
                                ModifyTag(
                                    SubjectRef.TARGET,
                                    "marker.root-blocked",
                                    TagOperation.ADD,
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
                actor("caster", "red", (action.action_key,)),
                actor("target", "blue", (), tags=("immunity.root",)),
            ),
            seed=5,
        )

        environment.step((choose(environment, action.action_key, "cast"),))

        target = environment.entity("target")
        self.assertNotIn("effect.root", target.effects)
        self.assertIn("marker.root-blocked", target.tags)

    def test_conditional_grammar_rejects_duplicate_outcomes(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicates"):
            OutcomeConditional(
                conditional_key="bad",
                condition=stun_condition(),
                outcomes=(
                    EffectOutcomeKind.APPLIED,
                    EffectOutcomeKind.APPLIED,
                ),
                effects=(
                    ModifyTag(
                        SubjectRef.TARGET,
                        "marker",
                        TagOperation.ADD,
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()
