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
from shadowbane_lab.rollouts.nearby_mob import (
    NearbyMobSimulationConfig,
    NearbyMobSimulationResult,
    frost_walker_observed_config,
    run_nearby_mob_simulation,
)

__all__ = [
    "ActionCount",
    "CombatantConfig",
    "CombatantResult",
    "DuelConfig",
    "DuelResult",
    "NearbyMobSimulationConfig",
    "NearbyMobSimulationResult",
    "TerminationReason",
    "UtilityDuelPolicy",
    "matched_progression_duels",
    "frost_walker_observed_config",
    "run_duel",
    "run_nearby_mob_simulation",
]
