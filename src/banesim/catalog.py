from __future__ import annotations

from .model import (
    ActionSpec,
    ApplyStatus,
    DealDamage,
    Formula,
    ModifyResource,
    Recipient,
    Reposition,
    RepositionMode,
    RestoreHealth,
    ScaleStat,
    StatusKind,
    TargetMode,
)


def default_action_catalog() -> dict[str, ActionSpec]:
    """Return an abstract action catalog built from reusable primitives.

    These are deliberately not claimed to be Reforged values. They are a compact
    stress test for the simulator and future rules compiler.
    """

    actions = [
        ActionSpec(
            id="basic_strike",
            name="Basic Strike",
            target_mode=TargetMode.ENEMY,
            range=2.4,
            cast_time=0.15,
            cooldown=1.0,
            stamina_cost=2.0,
            requires_hit=True,
            tags=frozenset({"damage", "physical", "basic"}),
            effects=(DealDamage(Formula(5.0, ScaleStat.POWER, 0.42), "physical"),),
            description="Low-cost physical attack available to every build.",
        ),
        ActionSpec(
            id="quick_jab",
            name="Quick Jab",
            target_mode=TargetMode.ENEMY,
            range=2.6,
            cast_time=0.05,
            cooldown=0.55,
            stamina_cost=5.0,
            requires_hit=True,
            tags=frozenset({"damage", "physical", "fast"}),
            effects=(DealDamage(Formula(6.0, ScaleStat.POWER, 0.32), "physical"),),
        ),
        ActionSpec(
            id="arc_bolt",
            name="Arc Bolt",
            target_mode=TargetMode.ENEMY,
            range=14.0,
            cast_time=0.7,
            cooldown=1.6,
            mana_cost=9.0,
            requires_hit=True,
            tags=frozenset({"damage", "spell", "ranged"}),
            effects=(DealDamage(Formula(10.0, ScaleStat.POWER, 0.78), "arcane"),),
        ),
        ActionSpec(
            id="ember",
            name="Ember",
            target_mode=TargetMode.ENEMY,
            range=12.0,
            cast_time=0.45,
            cooldown=2.2,
            mana_cost=8.0,
            requires_hit=True,
            tags=frozenset({"damage", "spell", "dot", "ranged"}),
            effects=(
                DealDamage(Formula(4.0, ScaleStat.POWER, 0.28), "fire"),
                ApplyStatus(
                    status=StatusKind.BURN,
                    duration=Formula(4.0, ScaleStat.POWER, 0.025),
                    tick_damage=Formula(1.5, ScaleStat.POWER, 0.11),
                    tick_interval=1.0,
                    damage_type="fire",
                ),
            ),
        ),
        ActionSpec(
            id="mend",
            name="Mend",
            target_mode=TargetMode.SELF,
            range=0.0,
            cast_time=0.6,
            cooldown=3.2,
            mana_cost=12.0,
            tags=frozenset({"heal", "spell", "support"}),
            effects=(RestoreHealth(Formula(11.0, ScaleStat.SUSTAIN, 0.72)),),
        ),
        ActionSpec(
            id="siphon",
            name="Siphon",
            target_mode=TargetMode.ENEMY,
            range=8.0,
            cast_time=0.4,
            cooldown=2.7,
            mana_cost=10.0,
            requires_hit=True,
            tags=frozenset({"damage", "heal", "spell", "ranged"}),
            effects=(
                DealDamage(Formula(6.0, ScaleStat.POWER, 0.45), "arcane"),
                RestoreHealth(Formula(3.0, ScaleStat.SUSTAIN, 0.28)),
            ),
        ),
        ActionSpec(
            id="cripple",
            name="Cripple",
            target_mode=TargetMode.ENEMY,
            range=7.0,
            cast_time=0.2,
            cooldown=4.0,
            stamina_cost=8.0,
            requires_hit=True,
            tags=frozenset({"damage", "control", "physical", "ranged"}),
            effects=(
                DealDamage(Formula(3.0, ScaleStat.POWER, 0.20), "physical"),
                ApplyStatus(
                    status=StatusKind.SNARE,
                    duration=Formula(1.8, ScaleStat.CONTROL, 0.035),
                    magnitude=Formula(0.30, ScaleStat.CONTROL, 0.003),
                ),
            ),
        ),
        ActionSpec(
            id="silence",
            name="Silence",
            target_mode=TargetMode.ENEMY,
            range=10.0,
            cast_time=0.25,
            cooldown=6.5,
            mana_cost=10.0,
            requires_hit=True,
            tags=frozenset({"control", "spell", "ranged"}),
            effects=(
                DealDamage(Formula(1.0, ScaleStat.POWER, 0.08), "arcane"),
                ApplyStatus(
                    status=StatusKind.SILENCE,
                    duration=Formula(0.8, ScaleStat.CONTROL, 0.045),
                ),
            ),
        ),
        ActionSpec(
            id="stun_bash",
            name="Stun Bash",
            target_mode=TargetMode.ENEMY,
            range=2.5,
            cast_time=0.2,
            cooldown=7.0,
            stamina_cost=12.0,
            requires_hit=True,
            tags=frozenset({"damage", "control", "physical"}),
            effects=(
                DealDamage(Formula(5.0, ScaleStat.POWER, 0.30), "physical"),
                ApplyStatus(
                    status=StatusKind.STUN,
                    duration=Formula(0.5, ScaleStat.CONTROL, 0.028),
                ),
            ),
        ),
        ActionSpec(
            id="ward",
            name="Ward",
            target_mode=TargetMode.SELF,
            range=0.0,
            cast_time=0.2,
            cooldown=8.0,
            mana_cost=14.0,
            tags=frozenset({"defense", "spell", "support"}),
            effects=(
                ApplyStatus(
                    status=StatusKind.WARD,
                    duration=Formula(3.0, ScaleStat.SUSTAIN, 0.035),
                    magnitude=Formula(0.18, ScaleStat.SUSTAIN, 0.003),
                    recipient=Recipient.ACTOR,
                ),
            ),
        ),
        ActionSpec(
            id="blink_back",
            name="Blink Back",
            target_mode=TargetMode.ENEMY,
            range=18.0,
            cast_time=0.05,
            cooldown=6.0,
            mana_cost=8.0,
            tags=frozenset({"mobility", "spell", "defense"}),
            effects=(
                Reposition(
                    distance=Formula(3.0, ScaleStat.MOBILITY, 0.09),
                    mode=RepositionMode.AWAY_FROM_TARGET,
                ),
            ),
        ),
        ActionSpec(
            id="shadow_step",
            name="Shadow Step",
            target_mode=TargetMode.ENEMY,
            range=16.0,
            cast_time=0.05,
            cooldown=6.0,
            stamina_cost=7.0,
            tags=frozenset({"mobility", "physical", "engage"}),
            effects=(
                Reposition(
                    distance=Formula(3.0, ScaleStat.MOBILITY, 0.10),
                    mode=RepositionMode.TOWARD_TARGET,
                ),
            ),
        ),
        ActionSpec(
            id="wither",
            name="Wither",
            target_mode=TargetMode.ENEMY,
            range=9.0,
            cast_time=0.35,
            cooldown=5.0,
            mana_cost=9.0,
            requires_hit=True,
            tags=frozenset({"control", "spell", "attrition", "ranged"}),
            effects=(
                DealDamage(Formula(2.0, ScaleStat.POWER, 0.12), "arcane"),
                ApplyStatus(
                    status=StatusKind.HEALING_REDUCTION,
                    duration=Formula(3.0, ScaleStat.CONTROL, 0.055),
                    magnitude=Formula(0.25, ScaleStat.CONTROL, 0.004),
                ),
            ),
        ),
        ActionSpec(
            id="mana_burn",
            name="Mana Burn",
            target_mode=TargetMode.ENEMY,
            range=10.0,
            cast_time=0.5,
            cooldown=4.5,
            mana_cost=8.0,
            requires_hit=True,
            tags=frozenset({"control", "spell", "resource", "ranged"}),
            effects=(
                ModifyResource("mana", Formula(-5.0, ScaleStat.CONTROL, -0.22)),
            ),
        ),
    ]
    return {action.id: action for action in actions}


SEARCHABLE_ACTION_IDS = tuple(
    action_id for action_id in default_action_catalog() if action_id != "basic_strike"
)
