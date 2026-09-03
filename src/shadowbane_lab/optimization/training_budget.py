"""Typed training-point budgets and conservative selection-cost audits."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .build_model import LegalBuildCompileError, canonical_digest


class TrainingPopulationScope(StrEnum):
    ALL = "all"
    HUMAN = "human"
    NON_HUMAN = "non_human"


class TrainingCostEvidence(StrEnum):
    EXACT = "exact"
    LOWER_BOUND = "lower_bound"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class TrainingLevelBand:
    """Inclusive level band granting a fixed number of trains per level."""

    first_level: int
    last_level: int
    points_per_level: int

    def __post_init__(self) -> None:
        for field_name in ("first_level", "last_level", "points_per_level"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise LegalBuildCompileError(f"{field_name} must be an integer")
        if self.first_level < 2:
            raise LegalBuildCompileError("training level bands must begin at level 2 or later")
        if self.last_level < self.first_level:
            raise LegalBuildCompileError("training level band ends before it begins")
        if self.points_per_level < 0:
            raise LegalBuildCompileError("points_per_level cannot be negative")

    def points_through(self, level: int) -> int:
        if isinstance(level, bool) or not isinstance(level, int) or level < 1:
            raise LegalBuildCompileError("level must be a positive integer")
        final_level = min(level, self.last_level)
        if final_level < self.first_level:
            return 0
        return (final_level - self.first_level + 1) * self.points_per_level

    def as_dict(self) -> dict[str, int]:
        return {
            "first_level": self.first_level,
            "last_level": self.last_level,
            "points_per_level": self.points_per_level,
        }


@dataclass(frozen=True, slots=True)
class TrainingBudgetProfile:
    """One source-pinned earned-training schedule for a character population."""

    profile_id: str
    base_class_key: str
    population_scope: TrainingPopulationScope
    level_bands: tuple[TrainingLevelBand, ...]
    source_id: str
    source_revision: str
    maximum_level: int = 75
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "profile_id",
            "base_class_key",
            "source_id",
            "source_revision",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise LegalBuildCompileError(f"{field_name} must be non-empty text")
        if not isinstance(self.population_scope, TrainingPopulationScope):
            raise LegalBuildCompileError("population_scope has the wrong type")
        if not self.level_bands or any(
            not isinstance(item, TrainingLevelBand) for item in self.level_bands
        ):
            raise LegalBuildCompileError("level_bands must contain TrainingLevelBand values")
        if (
            isinstance(self.maximum_level, bool)
            or not isinstance(self.maximum_level, int)
            or self.maximum_level < 1
        ):
            raise LegalBuildCompileError("maximum_level must be a positive integer")
        previous_end = 1
        for band in self.level_bands:
            if band.first_level <= previous_end:
                raise LegalBuildCompileError("training level bands overlap or are unordered")
            previous_end = band.last_level
        if self.level_bands[-1].last_level > self.maximum_level:
            raise LegalBuildCompileError("training level band exceeds maximum_level")
        if len(self.notes) != len(set(self.notes)) or any(
            not isinstance(item, str) or not item.strip() for item in self.notes
        ):
            raise LegalBuildCompileError("notes must contain unique non-empty strings")

    @property
    def profile_digest(self) -> str:
        return canonical_digest(self.as_dict())

    def applies_to(self, *, race_family: str, base_class_name: str) -> bool:
        race = _key(race_family, "race_family")
        base = _key(base_class_name, "base_class_name")
        if base != self.base_class_key:
            return False
        is_human = race == "human"
        return (
            self.population_scope is TrainingPopulationScope.ALL
            or self.population_scope is TrainingPopulationScope.HUMAN
            and is_human
            or self.population_scope is TrainingPopulationScope.NON_HUMAN
            and not is_human
        )

    def points_for_level(self, level: int) -> int:
        if (
            isinstance(level, bool)
            or not isinstance(level, int)
            or not 1 <= level <= self.maximum_level
        ):
            raise LegalBuildCompileError(
                f"level must be an integer in [1, {self.maximum_level}]"
            )
        return sum(band.points_through(level) for band in self.level_bands)

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "base_class_key": self.base_class_key,
            "population_scope": self.population_scope.value,
            "maximum_level": self.maximum_level,
            "level_bands": [item.as_dict() for item in self.level_bands],
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class TrainingSelectionCost:
    """Known cost boundary for one displayed skill or power rank."""

    category: str
    key: str
    displayed_rank: int
    minimum_points: int
    exact_points: int | None
    evidence: TrainingCostEvidence

    def __post_init__(self) -> None:
        if self.category not in {"skill", "power"}:
            raise LegalBuildCompileError("training cost category must be skill or power")
        _key(self.key, "training key")
        for field_name in ("displayed_rank", "minimum_points"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise LegalBuildCompileError(f"{field_name} must be a non-negative integer")
        if self.exact_points is not None and (
            isinstance(self.exact_points, bool)
            or not isinstance(self.exact_points, int)
            or self.exact_points < self.minimum_points
        ):
            raise LegalBuildCompileError(
                "exact_points must be null or an integer at least minimum_points"
            )
        if not isinstance(self.evidence, TrainingCostEvidence):
            raise LegalBuildCompileError("training cost evidence has the wrong type")
        if self.evidence is TrainingCostEvidence.EXACT and self.exact_points is None:
            raise LegalBuildCompileError("exact training cost evidence requires exact_points")
        if self.evidence is not TrainingCostEvidence.EXACT and self.exact_points is not None:
            raise LegalBuildCompileError(
                "non-exact training cost evidence cannot claim exact_points"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "key": self.key,
            "displayed_rank": self.displayed_rank,
            "minimum_points": self.minimum_points,
            "exact_points": self.exact_points,
            "evidence": self.evidence.value,
        }


@dataclass(frozen=True, slots=True)
class TrainingAllocationAudit:
    """Budget and cost evidence without conflating displayed skill with train cost."""

    race_family: str
    base_class_name: str
    level: int
    budget_profile_id: str | None
    budget_profile_digest: str | None
    budget_points: int | None
    source_id: str | None
    source_revision: str | None
    selections: tuple[TrainingSelectionCost, ...]

    def __post_init__(self) -> None:
        _key(self.race_family, "race_family")
        _key(self.base_class_name, "base_class_name")
        if isinstance(self.level, bool) or not isinstance(self.level, int) or self.level < 1:
            raise LegalBuildCompileError("level must be a positive integer")
        profile_values = (
            self.budget_profile_id,
            self.budget_profile_digest,
            self.budget_points,
            self.source_id,
            self.source_revision,
        )
        if any(item is None for item in profile_values) and any(
            item is not None for item in profile_values
        ):
            raise LegalBuildCompileError("training budget provenance must be all present or absent")
        if self.budget_profile_id is not None:
            for value, field_name in (
                (self.budget_profile_id, "budget_profile_id"),
                (self.source_id, "source_id"),
                (self.source_revision, "source_revision"),
            ):
                if not isinstance(value, str) or not value.strip():
                    raise LegalBuildCompileError(f"{field_name} must be non-empty text")
            if (
                not isinstance(self.budget_profile_digest, str)
                or len(self.budget_profile_digest) != 64
            ):
                raise LegalBuildCompileError("budget_profile_digest must be a SHA-256 string")
            if (
                isinstance(self.budget_points, bool)
                or not isinstance(self.budget_points, int)
                or self.budget_points < 0
            ):
                raise LegalBuildCompileError("budget_points must be a non-negative integer")
        if any(not isinstance(item, TrainingSelectionCost) for item in self.selections):
            raise LegalBuildCompileError("selections must contain TrainingSelectionCost values")
        identities = tuple((item.category, item.key) for item in self.selections)
        if len(identities) != len(set(identities)):
            raise LegalBuildCompileError("training selections must not repeat category/key pairs")

    @property
    def minimum_points_spent(self) -> int:
        return sum(item.minimum_points for item in self.selections)

    @property
    def exact_points_spent(self) -> int | None:
        if any(item.exact_points is None for item in self.selections):
            return None
        return sum(item.exact_points or 0 for item in self.selections)

    @property
    def lower_bound_remaining(self) -> int | None:
        if self.budget_points is None:
            return None
        return self.budget_points - self.minimum_points_spent

    @property
    def exact_remaining(self) -> int | None:
        exact = self.exact_points_spent
        if self.budget_points is None or exact is None:
            return None
        return self.budget_points - exact

    @property
    def lower_bound_overspent(self) -> bool:
        return self.lower_bound_remaining is not None and self.lower_bound_remaining < 0

    @property
    def unresolved_skill_cost_keys(self) -> tuple[str, ...]:
        return tuple(
            item.key
            for item in self.selections
            if item.category == "skill" and item.evidence is TrainingCostEvidence.UNRESOLVED
        )

    @property
    def unresolved_exact_power_cost_keys(self) -> tuple[str, ...]:
        return tuple(
            item.key
            for item in self.selections
            if item.category == "power" and item.evidence is not TrainingCostEvidence.EXACT
        )

    @property
    def evidence_complete(self) -> bool:
        return self.budget_points is not None and self.exact_points_spent is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "race_family": self.race_family,
            "base_class_name": self.base_class_name,
            "level": self.level,
            "budget_profile_id": self.budget_profile_id,
            "budget_profile_digest": self.budget_profile_digest,
            "budget_points": self.budget_points,
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "minimum_points_spent": self.minimum_points_spent,
            "exact_points_spent": self.exact_points_spent,
            "lower_bound_remaining": self.lower_bound_remaining,
            "exact_remaining": self.exact_remaining,
            "lower_bound_overspent": self.lower_bound_overspent,
            "evidence_complete": self.evidence_complete,
            "unresolved_skill_cost_keys": list(self.unresolved_skill_cost_keys),
            "unresolved_exact_power_cost_keys": list(
                self.unresolved_exact_power_cost_keys
            ),
            "selections": [item.as_dict() for item in self.selections],
        }


@dataclass(frozen=True, slots=True)
class TrainingBudgetCatalog:
    catalog_id: str
    profiles: tuple[TrainingBudgetProfile, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.catalog_id, str) or not self.catalog_id.strip():
            raise LegalBuildCompileError("catalog_id must be non-empty text")
        if any(not isinstance(item, TrainingBudgetProfile) for item in self.profiles):
            raise LegalBuildCompileError("profiles must contain TrainingBudgetProfile values")
        profile_ids = tuple(item.profile_id for item in self.profiles)
        if len(profile_ids) != len(set(profile_ids)):
            raise LegalBuildCompileError("training budget profile ids must be unique")

    @property
    def catalog_digest(self) -> str:
        return canonical_digest(
            {
                "catalog_id": self.catalog_id,
                "profiles": [item.as_dict() for item in self.profiles],
            }
        )

    def resolve(
        self,
        *,
        race_family: str,
        base_class_name: str,
    ) -> TrainingBudgetProfile | None:
        matches = tuple(
            item
            for item in self.profiles
            if item.applies_to(
                race_family=race_family,
                base_class_name=base_class_name,
            )
        )
        if len(matches) > 1:
            raise LegalBuildCompileError(
                "training budget profiles overlap for this race/base-class identity"
            )
        return None if not matches else matches[0]

    def audit(
        self,
        *,
        race_family: str,
        base_class_name: str,
        level: int,
        skill_ranks: tuple[tuple[str, int], ...],
        power_ranks: tuple[tuple[str, int], ...],
    ) -> TrainingAllocationAudit:
        profile = self.resolve(
            race_family=race_family,
            base_class_name=base_class_name,
        )
        selections = tuple(
            sorted(
                (
                    *(
                        TrainingSelectionCost(
                            category="skill",
                            key=key,
                            displayed_rank=rank,
                            minimum_points=0,
                            exact_points=None,
                            evidence=TrainingCostEvidence.UNRESOLVED,
                        )
                        for key, rank in skill_ranks
                    ),
                    *(
                        TrainingSelectionCost(
                            category="power",
                            key=key,
                            displayed_rank=rank,
                            minimum_points=rank,
                            exact_points=None,
                            evidence=TrainingCostEvidence.LOWER_BOUND,
                        )
                        for key, rank in power_ranks
                    ),
                ),
                key=lambda item: (item.category, item.key),
            )
        )
        return TrainingAllocationAudit(
            race_family=race_family,
            base_class_name=base_class_name,
            level=level,
            budget_profile_id=None if profile is None else profile.profile_id,
            budget_profile_digest=None if profile is None else profile.profile_digest,
            budget_points=None if profile is None else profile.points_for_level(level),
            source_id=None if profile is None else profile.source_id,
            source_revision=None if profile is None else profile.source_revision,
            selections=selections,
        )


def load_bundled_training_budget_catalog() -> TrainingBudgetCatalog:
    """Return only schedules already supported by checked-in evidence."""

    return TrainingBudgetCatalog(
        catalog_id="wonderbane.training-budgets.v1",
        profiles=(
            TrainingBudgetProfile(
                profile_id="wonderbane.non-human.rogue.v1",
                base_class_key="rogue",
                population_scope=TrainingPopulationScope.NON_HUMAN,
                level_bands=(
                    TrainingLevelBand(2, 10, 4),
                    TrainingLevelBand(11, 59, 10),
                    TrainingLevelBand(60, 64, 5),
                    TrainingLevelBand(65, 69, 4),
                    TrainingLevelBand(70, 74, 3),
                    TrainingLevelBand(75, 75, 2),
                ),
                source_id="wonderbane-proc-assassin-progression",
                source_revision="retrieved-2026-08-29",
                notes=(
                    "The schedule is verified for non-Human Rogue characters only.",
                    "Human bonus trains and Fighter, Healer, or Mage schedules remain unresolved.",
                ),
            ),
        ),
    )


def _key(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LegalBuildCompileError(f"{field_name} must be non-empty text")
    return "_".join(value.casefold().replace("-", " ").split())


__all__ = [
    "TrainingAllocationAudit",
    "TrainingBudgetCatalog",
    "TrainingBudgetProfile",
    "TrainingCostEvidence",
    "TrainingLevelBand",
    "TrainingPopulationScope",
    "TrainingSelectionCost",
    "load_bundled_training_budget_catalog",
]
