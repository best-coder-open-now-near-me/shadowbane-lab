"""Scenario rollouts and deterministic baseline policies."""

from shadowbane_lab.rollouts.duel import (
    ActionCount,
    CombatantConfig,
    CombatantResult,
    DuelConfig,
    DuelResult,
    TerminationReason,
    UtilityDuelPolicy,
    matched_progression_duels,
    run_duel,
)

__all__ = [
    "ActionCount",
    "CombatantConfig",
    "CombatantResult",
    "DuelConfig",
    "DuelResult",
    "TerminationReason",
    "UtilityDuelPolicy",
    "matched_progression_duels",
    "run_duel",
]
