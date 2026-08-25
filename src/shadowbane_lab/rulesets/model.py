"""Provenance-aware records produced by a ruleset compiler."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shadowbane_lab.sim import ActionCatalog, ActionSpec


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


class CompilationStatus(StrEnum):
    COMPILED = "compiled"
    COMPILED_WITH_OVERRIDE = "compiled_with_override"
    UNRESOLVED = "unresolved"


class SourceKind(StrEnum):
    EMULATOR_SOURCE = "emulator_source"
    EMULATOR_DATA = "emulator_data"
    CACHE_EXPORT = "cache_export"
    WIKI = "wiki"
    OBSERVED_TRACE = "observed_trace"
    REVIEWED_OVERRIDE = "reviewed_override"


@dataclass(frozen=True, slots=True)
class TrainingRequirement:
    training_key: str
    minimum_rank: int

    def __post_init__(self) -> None:
        _identifier(self.training_key, "training_key")
        if (
            isinstance(self.minimum_rank, bool)
            or not isinstance(self.minimum_rank, int)
            or self.minimum_rank < 0
        ):
            raise ValueError("minimum_rank must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class CharacterBuild:
    """Player-selected progression state, kept separate from compiled power mechanics."""

    profession: str
    level: int
    skill_ranks: tuple[tuple[str, int], ...] = ()
    power_ranks: tuple[tuple[str, int], ...] = ()
    enabled_power_keys: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _identifier(self.profession, "profession")
        if isinstance(self.level, bool) or not isinstance(self.level, int) or self.level < 1:
            raise ValueError("level must be a positive integer")
        self._validate_training(self.skill_ranks, "skill_ranks")
        self._validate_training(self.power_ranks, "power_ranks")
        if self.enabled_power_keys is not None:
            if len(self.enabled_power_keys) != len(set(self.enabled_power_keys)):
                raise ValueError("enabled_power_keys must not contain duplicates")
            for action_key in self.enabled_power_keys:
                _identifier(action_key, "enabled power key")

    def skill_rank(self, training_key: str) -> int:
        return dict(self.skill_ranks).get(training_key, 0)

    def power_rank(self, action_key: str) -> int | None:
        return dict(self.power_ranks).get(action_key)

    @staticmethod
    def _validate_training(values: tuple[tuple[str, int], ...], field_name: str) -> None:
        keys = tuple(key for key, _ in values)
        if len(keys) != len(set(keys)):
            raise ValueError(f"{field_name} must not contain duplicate keys")
        for key, rank in values:
            _identifier(key, f"{field_name} key")
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 0:
                raise ValueError(f"{field_name} ranks must be non-negative integers")


@dataclass(frozen=True, slots=True)
class PowerProgression:
    professions: tuple[str, ...]
    granted_level: int
    maximum_rank: int
    fixed_rank: int | None = None
    skill_requirements: tuple[TrainingRequirement, ...] = ()
    power_requirements: tuple[TrainingRequirement, ...] = ()

    def __post_init__(self) -> None:
        if not self.professions:
            raise ValueError("power progression requires at least one profession")
        if len(self.professions) != len(set(self.professions)):
            raise ValueError("progression professions must not contain duplicates")
        for profession in self.professions:
            _identifier(profession, "progression profession")
        for value, name in (
            (self.granted_level, "granted_level"),
            (self.maximum_rank, "maximum_rank"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.granted_level < 1:
            raise ValueError("granted_level must be positive")
        if self.fixed_rank is not None and (
            isinstance(self.fixed_rank, bool)
            or not isinstance(self.fixed_rank, int)
            or not 0 <= self.fixed_rank <= self.maximum_rank
        ):
            raise ValueError("fixed_rank must be between zero and maximum_rank")
        for requirements, name in (
            (self.skill_requirements, "skill requirements"),
            (self.power_requirements, "power requirements"),
        ):
            if any(not isinstance(item, TrainingRequirement) for item in requirements):
                raise ValueError(f"{name} must contain TrainingRequirement values")
            keys = tuple(item.training_key for item in requirements)
            if len(keys) != len(set(keys)):
                raise ValueError(f"{name} must not contain duplicate keys")

    def available_to(self, action_key: str, build: CharacterBuild) -> bool:
        if build.profession not in self.professions or build.level < self.granted_level:
            return False
        if build.enabled_power_keys is not None and action_key not in build.enabled_power_keys:
            return False
        if any(
            build.skill_rank(item.training_key) < item.minimum_rank
            for item in self.skill_requirements
        ):
            return False
        if any(
            (build.power_rank(item.training_key) or 0) < item.minimum_rank
            for item in self.power_requirements
        ):
            return False
        return True

    def validate_rank(self, rank: int) -> None:
        if isinstance(rank, bool) or not isinstance(rank, int) or not 0 <= rank <= self.maximum_rank:
            raise ValueError(f"power rank must be between zero and {self.maximum_rank}")
        if self.fixed_rank is not None and rank != self.fixed_rank:
            raise ValueError(f"fixed power must remain at rank {self.fixed_rank}")


@dataclass(frozen=True, slots=True)
class ProvenanceSource:
    source_id: str
    kind: SourceKind
    uri: str
    revision: str
    retrieved_on: str

    def __post_init__(self) -> None:
        _identifier(self.source_id, "source_id")
        if not isinstance(self.kind, SourceKind):
            raise ValueError("kind must be a SourceKind")
        _identifier(self.uri, "uri")
        _identifier(self.revision, "revision")
        _identifier(self.retrieved_on, "retrieved_on")


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    fields: tuple[str, ...]
    source_id: str
    locator: str
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("field provenance requires at least one field")
        for field in self.fields:
            _identifier(field, "field")
        _identifier(self.source_id, "source_id")
        _identifier(self.locator, "locator")
        if self.note is not None:
            _identifier(self.note, "note")


@dataclass(frozen=True, slots=True)
class ConcreteMapping:
    server_power_token: int | None = None
    server_id_string: str | None = None
    client_binding_key: str | None = None

    def __post_init__(self) -> None:
        if self.server_power_token is not None and (
            isinstance(self.server_power_token, bool)
            or not isinstance(self.server_power_token, int)
        ):
            raise ValueError("server_power_token must be an integer or null")
        for field_name in ("server_id_string", "client_binding_key"):
            value = getattr(self, field_name)
            if value is not None:
                _identifier(value, field_name)


@dataclass(frozen=True, slots=True)
class CompiledActionRecord:
    action_key: str
    display_name: str
    rank: int
    status: CompilationStatus
    mapping: ConcreteMapping
    provenance: tuple[FieldProvenance, ...]
    unresolved: tuple[str, ...]
    action: ActionSpec | None
    progression: PowerProgression | None = None

    def __post_init__(self) -> None:
        _identifier(self.action_key, "action_key")
        _identifier(self.display_name, "display_name")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 0:
            raise ValueError("rank must be a non-negative integer")
        if not isinstance(self.status, CompilationStatus):
            raise ValueError("status must be a CompilationStatus")
        if not isinstance(self.mapping, ConcreteMapping):
            raise ValueError("mapping must be a ConcreteMapping")
        if not self.provenance:
            raise ValueError("records require field provenance")
        if any(not isinstance(item, FieldProvenance) for item in self.provenance):
            raise ValueError("provenance must contain FieldProvenance values")
        for issue in self.unresolved:
            _identifier(issue, "unresolved issue")
        if self.status is CompilationStatus.UNRESOLVED:
            if self.action is not None:
                raise ValueError("unresolved records cannot expose an executable action")
            if not self.unresolved:
                raise ValueError("unresolved records require at least one issue")
        else:
            if self.action is None:
                raise ValueError("compiled records require an executable action")
            if self.action.action_key != self.action_key:
                raise ValueError("record and action keys must match")
        if self.status is CompilationStatus.COMPILED and self.unresolved:
            raise ValueError("fully compiled records cannot contain unresolved issues")
        if self.status is CompilationStatus.COMPILED_WITH_OVERRIDE and not self.unresolved:
            raise ValueError("override records must explain their unresolved differences")
        if self.progression is not None:
            if not isinstance(self.progression, PowerProgression):
                raise ValueError("progression must be a PowerProgression or null")
            self.progression.validate_rank(self.rank)


@dataclass(frozen=True, slots=True)
class CompiledRuleset:
    ruleset_id: str
    sources: tuple[ProvenanceSource, ...]
    records: tuple[CompiledActionRecord, ...]

    def __post_init__(self) -> None:
        _identifier(self.ruleset_id, "ruleset_id")
        source_ids = tuple(source.source_id for source in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source ids must be unique")
        record_keys = tuple(record.action_key for record in self.records)
        if len(record_keys) != len(set(record_keys)):
            raise ValueError("record action keys must be unique")
        known_sources = set(source_ids)
        for record in self.records:
            for provenance in record.provenance:
                if provenance.source_id not in known_sources:
                    raise ValueError(
                        f"{record.action_key} references unknown source {provenance.source_id}"
                    )

    @property
    def catalog(self) -> ActionCatalog:
        return ActionCatalog(
            tuple(record.action for record in self.records if record.action is not None)
        )

    def record(self, action_key: str) -> CompiledActionRecord:
        try:
            return next(record for record in self.records if record.action_key == action_key)
        except StopIteration as exc:
            raise KeyError(f"unknown ruleset action: {action_key}") from exc

    def status_counts(self) -> dict[CompilationStatus, int]:
        return {
            status: sum(record.status is status for record in self.records)
            for status in CompilationStatus
        }

    def action_keys_for(self, build: CharacterBuild) -> tuple[str, ...]:
        if not isinstance(build, CharacterBuild):
            raise ValueError("build must be a CharacterBuild")
        known_power_keys = {
            record.action_key for record in self.records if record.progression is not None
        }
        supplied_power_keys = {key for key, _ in build.power_ranks}
        unknown = supplied_power_keys - known_power_keys
        if unknown:
            raise ValueError(f"build contains unknown power ranks: {', '.join(sorted(unknown))}")
        if build.enabled_power_keys is not None:
            unknown = set(build.enabled_power_keys) - known_power_keys
            if unknown:
                raise ValueError(f"build enables unknown powers: {', '.join(sorted(unknown))}")

        action_keys: list[str] = []
        for record in self.records:
            if record.action is None:
                continue
            if record.progression is None:
                action_keys.append(record.action_key)
                continue
            selected_rank = build.power_rank(record.action_key)
            if selected_rank is not None:
                record.progression.validate_rank(selected_rank)
                if selected_rank != record.rank:
                    raise ValueError(
                        f"{record.action_key} was compiled at rank {record.rank}, "
                        f"not requested rank {selected_rank}"
                    )
            if record.progression.available_to(record.action_key, build):
                action_keys.append(record.action_key)
        return tuple(sorted(action_keys))
