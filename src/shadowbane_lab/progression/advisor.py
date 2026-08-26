"""Actionable level-59 and end-state roadmap for the sourced proc-Assassin slice."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from shadowbane_lab.progression.calculator import (
    estimate_procs,
    focus_skill_cap,
    melee_attack_rating,
    rogue_training_points_for_level,
)
from shadowbane_lab.progression.model import (
    ProcEstimate,
    ProcLoadout,
    ProgressionProfile,
    StatLine,
    TrainingTarget,
)


@dataclass(frozen=True, slots=True)
class PowerTarget:
    key: str
    target_rank: int
    priority: int
    purpose: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "key": self.key,
            "target_rank": self.target_rank,
            "priority": self.priority,
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class RankTargetAudit:
    """One observed displayed rank compared with a roadmap target."""

    category: str
    key: str
    current_rank: int
    target_rank: int
    priority: int
    purpose: str | None = None

    def __post_init__(self) -> None:
        if self.category not in {"skill", "power"}:
            raise ValueError("category must be skill or power")
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("key must be a non-empty string")
        for field_name in ("current_rank", "target_rank", "priority"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.purpose is not None and (
            not isinstance(self.purpose, str) or not self.purpose.strip()
        ):
            raise ValueError("purpose must be a non-empty string when supplied")

    @property
    def rank_gap(self) -> int:
        return max(self.target_rank - self.current_rank, 0)

    @property
    def target_met(self) -> bool:
        return self.rank_gap == 0

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "key": self.key,
            "current_rank": self.current_rank,
            "target_rank": self.target_rank,
            "rank_gap": self.rank_gap,
            "target_met": self.target_met,
            "priority": self.priority,
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class ProcAssassinTrainingAudit:
    """Exact observed rank deltas without conflating skill percent with train cost."""

    level: int
    unspent_training_points: int
    skill_targets: tuple[RankTargetAudit, ...]
    power_targets: tuple[RankTargetAudit, ...]

    def __post_init__(self) -> None:
        if isinstance(self.level, bool) or not isinstance(self.level, int) or self.level < 1:
            raise ValueError("level must be a positive integer")
        if (
            isinstance(self.unspent_training_points, bool)
            or not isinstance(self.unspent_training_points, int)
            or self.unspent_training_points < 0
        ):
            raise ValueError("unspent_training_points must be a non-negative integer")
        for targets, category in (
            (self.skill_targets, "skill"),
            (self.power_targets, "power"),
        ):
            keys = tuple(item.key for item in targets)
            if any(item.category != category for item in targets):
                raise ValueError(f"{category}_targets contains the wrong target category")
            if len(keys) != len(set(keys)):
                raise ValueError(f"{category}_targets must not contain duplicate keys")

    @property
    def power_rank_increments_needed(self) -> int:
        return sum(item.rank_gap for item in self.power_targets)

    @property
    def power_training_reserve_after_targets(self) -> int:
        return self.unspent_training_points - self.power_rank_increments_needed

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "unspent_training_points": self.unspent_training_points,
            "power_rank_increments_needed": self.power_rank_increments_needed,
            "power_training_reserve_after_targets": self.power_training_reserve_after_targets,
            "power_cost_assumption": "one training point per power-rank increment",
            "skill_targets": [item.as_dict() for item in self.skill_targets],
            "power_targets": [item.as_dict() for item in self.power_targets],
        }


@dataclass(frozen=True, slots=True)
class ProcBuildCandidate:
    name: str
    stats: StatLine
    attack_rating: float
    baseline_defense: int
    unarmed_focus_cap: float
    procs: ProcEstimate
    provenance: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "stats": self.stats.as_dict(),
            "attack_rating": self.attack_rating,
            "baseline_defense": self.baseline_defense,
            "unarmed_focus_cap": self.unarmed_focus_cap,
            "procs": self.procs.as_dict(),
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class ProcAssassinRoadmap:
    level: int
    training_points_now: int
    training_points_at_75: int
    disciplines_now: tuple[str, ...]
    third_discipline_at_70: str
    skill_targets: tuple[TrainingTarget, ...]
    power_targets: tuple[PowerTarget, ...]
    candidates: tuple[ProcBuildCandidate, ...]
    assumptions: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "training_points_now": self.training_points_now,
            "training_points_at_75": self.training_points_at_75,
            "training_points_still_to_earn": (
                self.training_points_at_75 - self.training_points_now
            ),
            "disciplines_now": list(self.disciplines_now),
            "third_discipline_at_70": self.third_discipline_at_70,
            "skill_targets": [
                {
                    "key": item.key,
                    "target": item.target,
                    "priority": item.priority,
                    "minimum_level": item.minimum_level,
                }
                for item in self.skill_targets
            ],
            "power_targets": [item.as_dict() for item in self.power_targets],
            "candidates": [item.as_dict() for item in self.candidates],
            "assumptions": list(self.assumptions),
        }


def irekei_proc_assassin_roadmap(
    profile: ProgressionProfile, *, level: int = 59
) -> ProcAssassinRoadmap:
    if not 20 <= level <= 75:
        raise ValueError("proc-Assassin roadmap requires level 20 through 75")
    loadout = ProcLoadout(
        weapon_key="generic_fast_fist",
        proc_effect_keys=("tier_three_mental", "poison_blade_rank_40"),
        hands=2,
        successful_hit_rate=1.0,
    )
    candidates = (
        _candidate(
            profile,
            loadout,
            name="observed-trait high-proc at 59",
            stats=StatLine(35, 130, 85, 165, 15),
            provenance=(
                "Live stats and Runestones panes: from 35/55/57/80/15 with 168 points, "
                "apply Sun Dancer (+5 CON) and Saboteur (+20 DEX), raise Intelligence to "
                "120, apply Intelligence of the Gods (+10 current, +40 cap) for 15 points, "
                "finish Intelligence at 165 and Constitution at 85, then place the remaining "
                "55 points in Dexterity"
            ),
        ),
        _candidate(
            profile,
            loadout,
            name="current-cap balanced",
            stats=StatLine(45, 150, 95, 110, 50),
            provenance=(
                "WonderBane Irekei/Rogue bases with Sun Dancer and Saboteur, "
                "using 190 level-earned ability points and no creation-trait modifiers"
            ),
        ),
        _candidate(
            profile,
            loadout,
            name="historical high-proc",
            stats=StatLine(35, 102, 85, 165, 10),
            provenance=(
                "Archived Irekei Rogue Assassin SunDancer +proc community template; "
                "current legality depends on the character's creation and stat runes"
            ),
        ),
    )
    return ProcAssassinRoadmap(
        level=level,
        training_points_now=rogue_training_points_for_level(level),
        training_points_at_75=rogue_training_points_for_level(75),
        disciplines_now=("sun_dancer", "saboteur"),
        third_discipline_at_70="bounty_hunter",
        skill_targets=tuple(
            sorted(
                (item for item in profile.training_targets if item.minimum_level <= level),
                key=lambda item: item.priority,
            )
        ),
        power_targets=_power_targets(),
        candidates=candidates,
        assumptions=(
            "Proc output is normalized to successful hits; target defense and miss chance "
            "are excluded.",
            "Both hands use speed-20.0 fist weapons, one swing per hand every two seconds.",
            "Each successful hit independently checks one tier-three mental proc and rank-40 "
            "Poison Blade at 5% each.",
            "Proc output uses the published spell-damage formula with zero focus scaling and "
            "excludes target resistances.",
            "Attack rating uses 161 Unarmed, 70 Unarmed Mastery, no gear ATR, and a neutral "
            "stance.",
            "The observed-trait candidate is legal only with the live Brilliant Mind and "
            "Wizard's Apprentice traits, Sun Dancer and Saboteur disciplines, and a Godly "
            "Intelligence rune applied at 120 INT.",
            "The generic current-cap candidate excludes creation traits and remains a control.",
        ),
    )


def audit_proc_assassin_training(
    roadmap: ProcAssassinRoadmap,
    *,
    skill_ranks: Mapping[str, int],
    power_ranks: Mapping[str, int],
    unspent_training_points: int,
) -> ProcAssassinTrainingAudit:
    """Compare a semantic client snapshot with the level-appropriate proc roadmap."""

    if not isinstance(roadmap, ProcAssassinRoadmap):
        raise ValueError("roadmap must be ProcAssassinRoadmap")
    if (
        isinstance(unspent_training_points, bool)
        or not isinstance(unspent_training_points, int)
        or unspent_training_points < 0
    ):
        raise ValueError("unspent_training_points must be a non-negative integer")
    observed_skills = _validated_ranks(skill_ranks, "skill_ranks")
    observed_powers = _validated_ranks(power_ranks, "power_ranks")

    final_skill_targets: dict[str, TrainingTarget] = {}
    for target in roadmap.skill_targets:
        existing = final_skill_targets.get(target.key)
        if existing is None or target.target > existing.target:
            final_skill_targets[target.key] = target
    skill_audits = tuple(
        RankTargetAudit(
            category="skill",
            key=target.key,
            current_rank=observed_skills.get(target.key, 0),
            target_rank=target.target,
            priority=target.priority,
        )
        for target in sorted(final_skill_targets.values(), key=lambda item: item.priority)
    )
    power_audits = tuple(
        RankTargetAudit(
            category="power",
            key=target.key,
            current_rank=observed_powers.get(target.key, 0),
            target_rank=target.target_rank,
            priority=target.priority,
            purpose=target.purpose,
        )
        for target in roadmap.power_targets
    )
    return ProcAssassinTrainingAudit(
        level=roadmap.level,
        unspent_training_points=unspent_training_points,
        skill_targets=skill_audits,
        power_targets=power_audits,
    )


def _validated_ranks(values: Mapping[str, int], field_name: str) -> dict[str, int]:
    if not isinstance(values, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    result: dict[str, int] = {}
    for key, rank in values.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 0:
            raise ValueError(f"{field_name} ranks must be non-negative integers")
        result[key] = rank
    return result


def _candidate(
    profile: ProgressionProfile,
    loadout: ProcLoadout,
    *,
    name: str,
    stats: StatLine,
    provenance: str,
) -> ProcBuildCandidate:
    return ProcBuildCandidate(
        name=name,
        stats=stats,
        attack_rating=melee_attack_rating(
            dexterity=stats.dexterity,
            weapon_skill=161,
            weapon_mastery=70,
        ),
        baseline_defense=stats.dexterity * 2,
        unarmed_focus_cap=focus_skill_cap(
            intelligence=stats.intelligence,
            primary_stat=stats.dexterity,
            race_bonus=10,
        ),
        procs=estimate_procs(profile, stats, loadout),
        provenance=provenance,
    )


def _power_targets() -> tuple[PowerTarget, ...]:
    return (
        PowerTarget("poison_blade", 40, 1, "primary self-applied weapon proc"),
        PowerTarget("cloak_of_shadows", 40, 2, "defense and Irekei cold-gap coverage"),
        PowerTarget("shadow_touch", 40, 3, "reliable single-target stun"),
        PowerTarget("shadow_mantle", 40, 4, "group PvP healing denial"),
        PowerTarget("sneak", 21, 5, "Stalk prerequisite and practical stealth"),
        PowerTarget("blindness", 12, 6, "Plague of Blindness prerequisite"),
        PowerTarget("plague_of_blindness", 30, 7, "group attack/defense debuff"),
        PowerTarget("steal_breath", 1, 8, "cheap snare access"),
        PowerTarget("silence", 1, 9, "cheap chant removal/block access"),
        PowerTarget("backstab", 1, 10, "cheap opener; defer GM poison variants"),
        PowerTarget("shadow_bolt", 5, 11, "low-cost ranged interrupt option"),
        PowerTarget("slayers_focus", 1, 12, "stun-immunity access"),
    )
