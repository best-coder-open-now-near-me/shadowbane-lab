"""Shared action timing derived from immutable specs and mutable actor state."""

from __future__ import annotations

from shadowbane_lab.sim.actions import ActionSpec
from shadowbane_lab.sim.state import EntityState

WEAPON_DELAY_SCALAR = "action.weapon.delay.factor"


def effective_action_cooldown_ms(actor: EntityState, action: ActionSpec) -> int:
    """Return the cooldown after the actor's current weapon-delay modifiers."""

    if "weapon" not in action.tags or action.cooldown_ms == 0:
        return action.cooldown_ms
    try:
        factor = actor.effective_scalar(WEAPON_DELAY_SCALAR)
    except KeyError:
        factor = 1.0
    return max(1, round(action.cooldown_ms * factor))
