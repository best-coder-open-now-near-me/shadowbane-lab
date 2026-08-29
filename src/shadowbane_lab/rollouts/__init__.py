"""Scenario rollouts and deterministic baseline policies."""

from shadowbane_lab.rollouts.duel import (
    ActionCount,
    CombatantConfig,
    CombatantResult,
    DuelConfig,
    DuelResult,
    ProgressionMatrixCell,
    TerminationReason,
    UtilityDuelPolicy,
    matched_progression_duels,
    progression_build,
    progression_duel_matrix,
    run_duel,
)
from shadowbane_lab.rollouts.presets import (
    CombatantPreset,
    wonderbane_deflock,
    wonderbane_sundancer_proc_assassin,
    wonderbane_sundancer_vs_deflock,
)
from shadowbane_lab.rollouts.ruleset import (
    load_assassin_warlock_duel_ruleset,
    progression_milestones,
)

__all__ = [
    "ActionCount",
    "CombatantConfig",
    "CombatantPreset",
    "CombatantResult",
    "DuelConfig",
    "DuelResult",
    "ProgressionMatrixCell",
    "TerminationReason",
    "UtilityDuelPolicy",
    "load_assassin_warlock_duel_ruleset",
    "matched_progression_duels",
    "progression_build",
    "progression_duel_matrix",
    "progression_milestones",
    "run_duel",
    "wonderbane_deflock",
    "wonderbane_sundancer_proc_assassin",
    "wonderbane_sundancer_vs_deflock",
]
