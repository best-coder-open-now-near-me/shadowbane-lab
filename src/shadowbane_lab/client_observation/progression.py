"""Structured character progression used by both the harness and simulator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from shadowbane_lab.progression import StatLine
from shadowbane_lab.rulesets import CharacterBuild

CHARACTER_PROGRESSION_SCHEMA_VERSION = 1

# Verified in WonderBane's HUD_Stats.cfg and the live stats pane. These are ArcHUD
# data-model fields, not screen positions. Fields 35-39 render qualitative labels
# such as "Average" and "Excellent"; they are not numeric attribute caps.
ARC_HUD_CHARACTER_DATA_FIELDS = {
    "strength": 1,
    "dexterity": 2,
    "constitution": 3,
    "intelligence": 4,
    "spirit": 5,
    "ability_points": 33,
    "strength_quality_label": 35,
    "dexterity_quality_label": 36,
    "constitution_quality_label": 37,
    "intelligence_quality_label": 38,
    "spirit_quality_label": 39,
    "skill_list": 149,
    "skill_name": 400,
    "skill_rank": 408,
}


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class TrainedRankObservation:
    key: str
    display_name: str
    rank: int

    def __post_init__(self) -> None:
        _identifier(self.key, "key")
        _identifier(self.display_name, "display_name")
        _non_negative_integer(self.rank, "rank")


@dataclass(frozen=True, slots=True)
class EquippedItemObservation:
    slot: str
    item_name: str
    weapon_skill_key: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.slot, "slot")
        _identifier(self.item_name, "item_name")
        if self.weapon_skill_key is not None:
            _identifier(self.weapon_skill_key, "weapon_skill_key")


@dataclass(frozen=True, slots=True)
class CharacterProgressionObservation:
    """One complete, read-only snapshot of character build state."""

    profile_id: str
    sequence: int
    race: str
    base_class: str
    profession: str
    level: int
    stats: StatLine
    stat_caps: StatLine
    unspent_ability_points: int
    unspent_training_points: int
    skills: tuple[TrainedRankObservation, ...]
    powers: tuple[TrainedRankObservation, ...]
    discipline_keys: tuple[str, ...]
    equipment: tuple[EquippedItemObservation, ...]
    schema_version: int = CHARACTER_PROGRESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("profile_id", "race", "base_class", "profession"):
            _identifier(getattr(self, name), name)
        _non_negative_integer(self.sequence, "sequence")
        if isinstance(self.level, bool) or not isinstance(self.level, int) or self.level < 1:
            raise ValueError("level must be a positive integer")
        _non_negative_integer(self.unspent_ability_points, "unspent_ability_points")
        _non_negative_integer(self.unspent_training_points, "unspent_training_points")
        for entries, name in ((self.skills, "skills"), (self.powers, "powers")):
            keys = tuple(item.key for item in entries)
            if len(keys) != len(set(keys)):
                raise ValueError(f"{name} must not contain duplicate keys")
        if len(self.discipline_keys) != len(set(self.discipline_keys)):
            raise ValueError("discipline_keys must not contain duplicates")
        for key in self.discipline_keys:
            _identifier(key, "discipline key")
        slots = tuple(item.slot for item in self.equipment)
        if len(slots) != len(set(slots)):
            raise ValueError("equipment slots must not contain duplicates")
        if self.schema_version != CHARACTER_PROGRESSION_SCHEMA_VERSION:
            raise ValueError("unsupported character progression schema version")

    def ruleset_build(self, power_action_keys: Mapping[str, str]) -> CharacterBuild:
        """Derive the compiled-ruleset input without exposing unknown client powers."""

        mapped_powers = tuple(
            sorted(
                (power_action_keys[item.key], item.rank)
                for item in self.powers
                if item.key in power_action_keys
            )
        )
        return CharacterBuild(
            profession=self.profession.casefold(),
            level=self.level,
            skill_ranks=tuple(sorted((item.key, item.rank) for item in self.skills)),
            power_ranks=mapped_powers,
            enabled_power_keys=tuple(key for key, _ in mapped_powers),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "sequence": self.sequence,
            "identity": {
                "race": self.race,
                "base_class": self.base_class,
                "profession": self.profession,
                "level": self.level,
            },
            "stats": self.stats.as_dict(),
            "stat_caps": self.stat_caps.as_dict(),
            "unspent_ability_points": self.unspent_ability_points,
            "unspent_training_points": self.unspent_training_points,
            "skills": [
                {"key": item.key, "display_name": item.display_name, "rank": item.rank}
                for item in self.skills
            ],
            "powers": [
                {"key": item.key, "display_name": item.display_name, "rank": item.rank}
                for item in self.powers
            ],
            "discipline_keys": list(self.discipline_keys),
            "equipment": [
                {
                    "slot": item.slot,
                    "item_name": item.item_name,
                    "weapon_skill_key": item.weapon_skill_key,
                }
                for item in self.equipment
            ],
        }
