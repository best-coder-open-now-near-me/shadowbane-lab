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
