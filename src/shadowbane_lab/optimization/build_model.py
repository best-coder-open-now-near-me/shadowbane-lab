"""Immutable contracts for calculator-legal build optimization."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from shadowbane_lab.composition import ResolvedBuildView
from shadowbane_lab.progression import CalculatorBuildOutput, StatLine
from shadowbane_lab.rulesets import CharacterBuild

LEGAL_BUILD_GENOME_SCHEMA_VERSION = 1
LEGAL_BUILD_COMPILER_VERSION = 1
_KEY_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]*")


class LegalBuildCompileError(ValueError):
    """Raised when a build cannot be validated without guessing."""


class BuildCompilationStatus(StrEnum):
    CHASSIS_VERIFIED = "chassis_verified"
    SOURCE_CANDIDATE = "source_candidate"
    SIMULATION_READY = "simulation_ready"


@dataclass(frozen=True, slots=True)
class LegalBuildCompilePolicy:
    allow_ruleset_overrides: bool = False
    apply_candidate_equipment_values: bool = False
    require_simulation_ready: bool = False

    def __post_init__(self) -> None:
        for name in (
            "allow_ruleset_overrides",
            "apply_candidate_equipment_values",
            "require_simulation_ready",
        ):
            if not isinstance(getattr(self, name), bool):
                raise LegalBuildCompileError(f"{name} must be a boolean")

    def as_dict(self) -> dict[str, bool]:
        return {
            "allow_ruleset_overrides": self.allow_ruleset_overrides,
            "apply_candidate_equipment_values": self.apply_candidate_equipment_values,
            "require_simulation_ready": self.require_simulation_ready,
        }


@dataclass(frozen=True, slots=True)
class SelectedAffix:
    table_id: int
    action_id: str
    roll: float | None = None

    def __post_init__(self) -> None:
        _positive_int(self.table_id, "affix table_id")
        _text(self.action_id, "affix action_id")
        if self.roll is not None:
            _number(self.roll, "affix roll")

    def as_dict(self) -> dict[str, object]:
        return {"table_id": self.table_id, "action_id": self.action_id, "roll": self.roll}


@dataclass(frozen=True, slots=True)
class EquipmentSelection:
    slot_key: str
    item_id: int
    prefix: SelectedAffix | None = None
    suffix: SelectedAffix | None = None

    def __post_init__(self) -> None:
        if _KEY_PATTERN.fullmatch(_text(self.slot_key, "equipment slot_key")) is None:
            raise LegalBuildCompileError("equipment slot_key is not a stable lowercase key")
        _positive_int(self.item_id, "equipment item_id")
        for value, name in ((self.prefix, "prefix"), (self.suffix, "suffix")):
            if value is not None and not isinstance(value, SelectedAffix):
                raise LegalBuildCompileError(f"{name} must be SelectedAffix or null")

    def as_dict(self) -> dict[str, object]:
        return {
            "slot_key": self.slot_key,
            "item_id": self.item_id,
            "prefix": None if self.prefix is None else self.prefix.as_dict(),
            "suffix": None if self.suffix is None else self.suffix.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class LegalBuildGenome:
    genome_id: str
    display_name: str
    race_id: int
    base_class_id: int
    promotion_id: int | None
    level: int
    move_speed: float
    trained_modifiers: StatLine = StatLine()
    rune_ids: tuple[int, ...] = ()
    skill_ranks: tuple[tuple[str, int], ...] = ()
    power_ranks: tuple[tuple[str, int], ...] = ()
    equipment: tuple[EquipmentSelection, ...] = ()

    def __post_init__(self) -> None:
        _text(self.genome_id, "genome_id")
        _text(self.display_name, "display_name")
        _positive_int(self.race_id, "race_id")
        _positive_int(self.base_class_id, "base_class_id")
        if self.promotion_id is not None:
            _positive_int(self.promotion_id, "promotion_id")
        if (
            isinstance(self.level, bool)
            or not isinstance(self.level, int)
            or not 1 <= self.level <= 80
        ):
            raise LegalBuildCompileError("level must be an integer in [1, 80]")
        if _number(self.move_speed, "move_speed") <= 0:
            raise LegalBuildCompileError("move_speed must be positive")
        if not isinstance(self.trained_modifiers, StatLine):
            raise LegalBuildCompileError("trained_modifiers must be StatLine")
        _unique(self.rune_ids, "rune_ids")
        for rune_id in self.rune_ids:
            _positive_int(rune_id, "rune_id")
        _ranks(self.skill_ranks, "skill_ranks")
        _ranks(self.power_ranks, "power_ranks")
        if any(not isinstance(item, EquipmentSelection) for item in self.equipment):
            raise LegalBuildCompileError("equipment must contain EquipmentSelection values")
        _unique(tuple(item.slot_key for item in self.equipment), "equipment slot keys")

    @property
    def genome_digest(self) -> str:
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": LEGAL_BUILD_GENOME_SCHEMA_VERSION,
            "genome_id": self.genome_id,
            "display_name": self.display_name,
            "race_id": self.race_id,
            "base_class_id": self.base_class_id,
            "promotion_id": self.promotion_id,
            "level": self.level,
            "move_speed": float(self.move_speed),
            "trained_modifiers": self.trained_modifiers.as_dict(),
            "rune_ids": list(self.rune_ids),
            "skill_ranks": dict(sorted(self.skill_ranks)),
            "power_ranks": dict(sorted(self.power_ranks)),
            "equipment": [item.as_dict() for item in self.equipment],
        }


@dataclass(frozen=True, slots=True)
class BuildCoverageReport:
    calculator_review_status: str
    equipment_catalog_status: str
    ruleset_id: str | None
    requested_action_count: int
    executable_action_count: int
    requested_equipment_count: int
    candidate_equipment_values_applied: bool
    unresolved: tuple[str, ...] = ()
    accepted_assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.calculator_review_status, "calculator_review_status")
        _text(self.equipment_catalog_status, "equipment_catalog_status")
        if self.ruleset_id is not None:
            _text(self.ruleset_id, "ruleset_id")
        for name in (
            "requested_action_count",
            "executable_action_count",
            "requested_equipment_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise LegalBuildCompileError(f"{name} must be a non-negative integer")
        if self.executable_action_count > self.requested_action_count:
            raise LegalBuildCompileError("executable action count exceeds requested actions")
        if not isinstance(self.candidate_equipment_values_applied, bool):
            raise LegalBuildCompileError("candidate equipment flag must be a boolean")
        _unique(self.unresolved, "unresolved entries")
        _unique(self.accepted_assumptions, "accepted assumptions")

    @property
    def action_coverage_fraction(self) -> float:
        return (
            1.0
            if self.requested_action_count == 0
            else self.executable_action_count / self.requested_action_count
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "calculator_review_status": self.calculator_review_status,
            "equipment_catalog_status": self.equipment_catalog_status,
            "ruleset_id": self.ruleset_id,
            "requested_action_count": self.requested_action_count,
            "executable_action_count": self.executable_action_count,
            "action_coverage_fraction": self.action_coverage_fraction,
            "requested_equipment_count": self.requested_equipment_count,
            "candidate_equipment_values_applied": self.candidate_equipment_values_applied,
            "unresolved": list(self.unresolved),
            "accepted_assumptions": list(self.accepted_assumptions),
        }


@dataclass(frozen=True, slots=True)
class CompiledLegalBuild:
    status: BuildCompilationStatus
    genome: LegalBuildGenome
    calculator_output: CalculatorBuildOutput
    character_build: CharacterBuild
    view: ResolvedBuildView
    coverage: BuildCoverageReport
    source_fingerprints: tuple[tuple[str, str], ...]
    compile_policy: LegalBuildCompilePolicy

    def __post_init__(self) -> None:
        if not isinstance(self.status, BuildCompilationStatus):
            raise LegalBuildCompileError("status must be BuildCompilationStatus")
        if not isinstance(self.genome, LegalBuildGenome):
            raise LegalBuildCompileError("genome must be LegalBuildGenome")
        if not isinstance(self.calculator_output, CalculatorBuildOutput):
            raise LegalBuildCompileError("calculator_output has the wrong type")
        if not isinstance(self.character_build, CharacterBuild):
            raise LegalBuildCompileError("character_build has the wrong type")
        if not isinstance(self.view, ResolvedBuildView):
            raise LegalBuildCompileError("view has the wrong type")
        if not isinstance(self.coverage, BuildCoverageReport):
            raise LegalBuildCompileError("coverage has the wrong type")
        if not isinstance(self.compile_policy, LegalBuildCompilePolicy):
            raise LegalBuildCompileError("compile_policy has the wrong type")
        _unique(tuple(key for key, _ in self.source_fingerprints), "fingerprint keys")

    @property
    def strict_archive_eligible(self) -> bool:
        return self.status is BuildCompilationStatus.SIMULATION_READY

    @property
    def compilation_digest(self) -> str:
        return canonical_digest(
            {
                "compiler_version": LEGAL_BUILD_COMPILER_VERSION,
                "genome_digest": self.genome.genome_digest,
                "status": self.status.value,
                "mechanical_signature": self.view.mechanical_signature,
                "construction_signature": self.view.construction_signature,
                "coverage": self.coverage.as_dict(),
                "source_fingerprints": dict(self.source_fingerprints),
                "compile_policy": self.compile_policy.as_dict(),
            }
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "compiler_version": LEGAL_BUILD_COMPILER_VERSION,
            "status": self.status.value,
            "strict_archive_eligible": self.strict_archive_eligible,
            "genome": self.genome.as_dict(),
            "calculator_output": self.calculator_output.to_dict(),
            "character_build": {
                "profession": self.character_build.profession,
                "level": self.character_build.level,
                "skill_ranks": dict(self.character_build.skill_ranks),
                "power_ranks": dict(self.character_build.power_ranks),
                "enabled_power_keys": list(self.character_build.enabled_power_keys or ()),
            },
            "view": self.view.as_dict(),
            "coverage": self.coverage.as_dict(),
            "source_fingerprints": dict(self.source_fingerprints),
            "compile_policy": self.compile_policy.as_dict(),
            "compilation_digest": self.compilation_digest,
        }


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LegalBuildCompileError(f"{name} must be non-empty text")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise LegalBuildCompileError(f"{name} must be a finite number")
    return float(value)


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LegalBuildCompileError(f"{name} must be a positive integer")
    return value


def _unique(values: tuple[object, ...], name: str) -> None:
    if len(values) != len(set(values)):
        raise LegalBuildCompileError(f"{name} must not contain duplicates")


def _ranks(values: tuple[tuple[str, int], ...], name: str) -> None:
    _unique(tuple(key for key, _ in values), f"{name} keys")
    for key, rank in values:
        _text(key, f"{name} key")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 0:
            raise LegalBuildCompileError(f"{name}.{key} must be a non-negative integer")


__all__ = [
    "LEGAL_BUILD_COMPILER_VERSION",
    "LEGAL_BUILD_GENOME_SCHEMA_VERSION",
    "BuildCompilationStatus",
    "BuildCoverageReport",
    "CompiledLegalBuild",
    "EquipmentSelection",
    "LegalBuildCompileError",
    "LegalBuildCompilePolicy",
    "LegalBuildGenome",
    "SelectedAffix",
    "canonical_digest",
]
