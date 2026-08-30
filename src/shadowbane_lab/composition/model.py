"""Immutable composition contracts for builds, scenarios, and simulation cases.

The simulator consumes resolved mechanics. Race, class, promotion, discipline,
item, and consumable names remain construction provenance rather than runtime
branch conditions. Scenario affiliation data is carried opaquely so the group
resolver can own its meaning independently.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from typing import Any


class CompositionError(ValueError):
    """Raised when a composition contract is malformed."""


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CompositionError(f"{field_name} must be a non-empty string")


def _optional_identifier(value: str | None, field_name: str) -> None:
    if value is not None:
        _identifier(value, field_name)


def _unique_strings(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise CompositionError(f"{field_name} must not contain duplicates")
    for value in values:
        _identifier(value, field_name)


def _finite(value: float, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise CompositionError(f"{field_name} must be a finite number")


def _positive(value: float, field_name: str) -> None:
    _finite(value, field_name)
    if value <= 0:
        raise CompositionError(f"{field_name} must be positive")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CompositionError(f"{field_name} must be a non-negative integer")


def _validate_number_pairs(
    values: tuple[tuple[str, float], ...],
    field_name: str,
) -> None:
    keys = tuple(key for key, _ in values)
    _unique_strings(keys, f"{field_name} keys")
    for key, value in values:
        _finite(value, f"{field_name}.{key}")


def _validate_string_pairs(
    values: tuple[tuple[str, str], ...],
    field_name: str,
) -> None:
    keys = tuple(key for key, _ in values)
    _unique_strings(keys, f"{field_name} keys")
    for key, value in values:
        _identifier(value, f"{field_name}.{key}")


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _number_mapping(values: tuple[tuple[str, float], ...]) -> dict[str, float]:
    return {key: float(value) for key, value in sorted(values)}


def _string_mapping(values: tuple[tuple[str, str], ...]) -> dict[str, str]:
    return {key: value for key, value in sorted(values)}


class SourcePackageKind(StrEnum):
    BODY = "body"
    RACE = "race"
    BASE_CLASS = "base_class"
    PROMOTION = "promotion"
    DISCIPLINE = "discipline"
    STAT_RUNE = "stat_rune"
    EQUIPMENT = "equipment"
    CONSUMABLE = "consumable"
    EXPERIMENTAL = "experimental"


@dataclass(frozen=True, slots=True)
class BodyValues:
    health: float = 500.0
    mana: float = 300.0
    stamina: float = 200.0
    move_speed: float = 15.0

    def __post_init__(self) -> None:
        for value, name in (
            (self.health, "health"),
            (self.mana, "mana"),
            (self.stamina, "stamina"),
            (self.move_speed, "move_speed"),
        ):
            _positive(value, name)

    def as_dict(self) -> dict[str, float]:
        return {
            "health": float(self.health),
            "mana": float(self.mana),
            "stamina": float(self.stamina),
            "move_speed": float(self.move_speed),
        }


@dataclass(frozen=True, slots=True)
class BodyDelta:
    health: float = 0.0
    mana: float = 0.0
    stamina: float = 0.0
    move_speed: float = 0.0

    def __post_init__(self) -> None:
        for value, name in (
            (self.health, "health"),
            (self.mana, "mana"),
            (self.stamina, "stamina"),
            (self.move_speed, "move_speed"),
        ):
            _finite(value, name)

    def as_dict(self) -> dict[str, float]:
        return {
            "health": float(self.health),
            "mana": float(self.mana),
            "stamina": float(self.stamina),
            "move_speed": float(self.move_speed),
        }


@dataclass(frozen=True, slots=True)
class SourcePackage:
    """One reusable source of primitive-derived mechanics and constraints."""

    package_id: str
    display_name: str
    kind: SourcePackageKind
    selection_slot: str | None = None
    action_keys: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    persistent_trigger_keys: tuple[str, ...] = ()
    training_access_keys: tuple[str, ...] = ()
    body_delta: BodyDelta = field(default_factory=BodyDelta)
    scalar_deltas: tuple[tuple[str, float], ...] = ()
    attribute_deltas: tuple[tuple[str, float], ...] = ()
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.package_id, "package_id")
        _identifier(self.display_name, "display_name")
        if not isinstance(self.kind, SourcePackageKind):
            raise CompositionError("kind must be a SourcePackageKind")
        _optional_identifier(self.selection_slot, "selection_slot")
        for values, name in (
            (self.action_keys, "action_keys"),
            (self.tags, "tags"),
            (self.persistent_trigger_keys, "persistent_trigger_keys"),
            (self.training_access_keys, "training_access_keys"),
            (self.requires, "requires"),
            (self.conflicts, "conflicts"),
        ):
            _unique_strings(values, name)
        if self.package_id in self.requires:
            raise CompositionError("a package cannot require itself")
        if self.package_id in self.conflicts:
            raise CompositionError("a package cannot conflict with itself")
        if set(self.requires) & set(self.conflicts):
            raise CompositionError("a package cannot both require and conflict with a package")
        if not isinstance(self.body_delta, BodyDelta):
            raise CompositionError("body_delta must be a BodyDelta")
        _validate_number_pairs(self.scalar_deltas, "scalar_deltas")
        _validate_number_pairs(self.attribute_deltas, "attribute_deltas")
        _validate_string_pairs(self.metadata, "metadata")

    def as_dict(self) -> dict[str, object]:
        return {
            "package_id": self.package_id,
            "display_name": self.display_name,
            "kind": self.kind.value,
            "selection_slot": self.selection_slot,
            "action_keys": list(self.action_keys),
            "tags": list(self.tags),
            "persistent_trigger_keys": list(self.persistent_trigger_keys),
            "training_access_keys": list(self.training_access_keys),
            "body_delta": self.body_delta.as_dict(),
            "scalar_deltas": _number_mapping(self.scalar_deltas),
            "attribute_deltas": _number_mapping(self.attribute_deltas),
            "requires": list(self.requires),
            "conflicts": list(self.conflicts),
            "metadata": _string_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SourcePackageCatalog:
    catalog_id: str
    packages: tuple[SourcePackage, ...] = ()
    slot_limits: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.catalog_id, "catalog_id")
        package_ids = tuple(package.package_id for package in self.packages)
        _unique_strings(package_ids, "package ids")
        slot_keys = tuple(key for key, _ in self.slot_limits)
        _unique_strings(slot_keys, "slot limit keys")
        for key, limit in self.slot_limits:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise CompositionError(f"slot limit {key} must be a positive integer")
        known = set(package_ids)
        for package in self.packages:
            unknown = (set(package.requires) | set(package.conflicts)) - known
            if unknown:
                raise CompositionError(
                    f"{package.package_id} references unknown packages: "
                    + ", ".join(sorted(unknown))
                )
            if package.selection_slot is not None and package.selection_slot not in slot_keys:
                raise CompositionError(
                    f"{package.package_id} uses undeclared selection slot "
                    f"{package.selection_slot}"
                )

    @property
    def by_id(self) -> dict[str, SourcePackage]:
        return {package.package_id: package for package in self.packages}

    @property
    def limits_by_slot(self) -> dict[str, int]:
        return dict(self.slot_limits)


@dataclass(frozen=True, slots=True)
class BuildBlueprint:
    """Construction request before package closure and mechanical resolution."""

    blueprint_id: str
    display_name: str
    requested_package_ids: tuple[str, ...] = ()
    base_body: BodyValues = field(default_factory=BodyValues)
    direct_action_keys: tuple[str, ...] = ()
    direct_tags: tuple[str, ...] = ()
    direct_persistent_trigger_keys: tuple[str, ...] = ()
    base_scalars: tuple[tuple[str, float], ...] = ()
    attributes: tuple[tuple[str, float], ...] = ()
    training: tuple[tuple[str, float], ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.blueprint_id, "blueprint_id")
        _identifier(self.display_name, "display_name")
        for values, name in (
            (self.requested_package_ids, "requested_package_ids"),
            (self.direct_action_keys, "direct_action_keys"),
            (self.direct_tags, "direct_tags"),
            (self.direct_persistent_trigger_keys, "direct_persistent_trigger_keys"),
            (self.notes, "notes"),
        ):
            _unique_strings(values, name)
        if not isinstance(self.base_body, BodyValues):
            raise CompositionError("base_body must be BodyValues")
        _validate_number_pairs(self.base_scalars, "base_scalars")
        _validate_number_pairs(self.attributes, "attributes")
        _validate_number_pairs(self.training, "training")
        _validate_string_pairs(self.metadata, "metadata")


@dataclass(frozen=True, slots=True)
class GrantSource:
    grant_kind: str
    grant_key: str
    source_package_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.grant_kind, "grant_kind")
        _identifier(self.grant_key, "grant_key")
        _unique_strings(self.source_package_ids, "source_package_ids")
        if not self.source_package_ids:
            raise CompositionError("grant source requires at least one source id")

    def as_dict(self) -> dict[str, object]:
        return {
            "grant_kind": self.grant_kind,
            "grant_key": self.grant_key,
            "source_package_ids": list(self.source_package_ids),
        }


@dataclass(frozen=True, slots=True)
class ResolvedBuildView:
    """Immutable mechanical materialization of one build permutation."""

    build_id: str
    display_name: str
    catalog_id: str
    body: BodyValues
    requested_package_ids: tuple[str, ...]
    selected_package_ids: tuple[str, ...]
    auto_added_requirement_ids: tuple[str, ...]
    executable_action_keys: tuple[str, ...]
    omitted_action_keys: tuple[str, ...]
    tags: tuple[str, ...]
    executable_persistent_trigger_keys: tuple[str, ...]
    omitted_persistent_trigger_keys: tuple[str, ...]
    scalars: tuple[tuple[str, float], ...]
    attributes: tuple[tuple[str, float], ...]
    training: tuple[tuple[str, float], ...]
    unresolved_training_keys: tuple[str, ...]
    grant_sources: tuple[GrantSource, ...]
    metadata: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.build_id, "build_id"),
            (self.display_name, "display_name"),
            (self.catalog_id, "catalog_id"),
        ):
            _identifier(value, name)
        if not isinstance(self.body, BodyValues):
            raise CompositionError("body must be BodyValues")
        for values, name in (
            (self.requested_package_ids, "requested_package_ids"),
            (self.selected_package_ids, "selected_package_ids"),
            (self.auto_added_requirement_ids, "auto_added_requirement_ids"),
            (self.executable_action_keys, "executable_action_keys"),
            (self.omitted_action_keys, "omitted_action_keys"),
            (self.tags, "tags"),
            (
                self.executable_persistent_trigger_keys,
                "executable_persistent_trigger_keys",
            ),
            (self.omitted_persistent_trigger_keys, "omitted_persistent_trigger_keys"),
            (self.unresolved_training_keys, "unresolved_training_keys"),
            (self.notes, "notes"),
        ):
            _unique_strings(values, name)
        if set(self.executable_action_keys) & set(self.omitted_action_keys):
            raise CompositionError("an action cannot be both executable and omitted")
        if set(self.executable_persistent_trigger_keys) & set(
            self.omitted_persistent_trigger_keys
        ):
            raise CompositionError("a trigger cannot be both executable and omitted")
        _validate_number_pairs(self.scalars, "scalars")
        _validate_number_pairs(self.attributes, "attributes")
        _validate_number_pairs(self.training, "training")
        _validate_string_pairs(self.metadata, "metadata")

    @property
    def coverage_fraction(self) -> float:
        requested = (
            len(self.executable_action_keys)
            + len(self.omitted_action_keys)
            + len(self.executable_persistent_trigger_keys)
            + len(self.omitted_persistent_trigger_keys)
        )
        executable = len(self.executable_action_keys) + len(
            self.executable_persistent_trigger_keys
        )
        return 1.0 if requested == 0 else executable / requested

    def mechanical_payload(self) -> dict[str, object]:
        return {
            "body": self.body.as_dict(),
            "action_keys": sorted(self.executable_action_keys),
            "tags": sorted(self.tags),
            "persistent_trigger_keys": sorted(
                self.executable_persistent_trigger_keys
            ),
            "scalars": _number_mapping(self.scalars),
            "attributes": _number_mapping(self.attributes),
            "training": _number_mapping(self.training),
        }

    @property
    def mechanical_signature(self) -> str:
        return _canonical_digest(self.mechanical_payload())

    def construction_payload(self) -> dict[str, object]:
        return {
            "catalog_id": self.catalog_id,
            "requested_package_ids": sorted(self.requested_package_ids),
            "selected_package_ids": sorted(self.selected_package_ids),
            "auto_added_requirement_ids": sorted(self.auto_added_requirement_ids),
            "omitted_action_keys": sorted(self.omitted_action_keys),
            "omitted_persistent_trigger_keys": sorted(
                self.omitted_persistent_trigger_keys
            ),
            "unresolved_training_keys": sorted(self.unresolved_training_keys),
            "mechanical_signature": self.mechanical_signature,
        }

    @property
    def construction_signature(self) -> str:
        return _canonical_digest(self.construction_payload())

    def as_dict(self) -> dict[str, object]:
        return {
            "build_id": self.build_id,
            "display_name": self.display_name,
            "catalog_id": self.catalog_id,
            "body": self.body.as_dict(),
            "requested_package_ids": list(self.requested_package_ids),
            "selected_package_ids": list(self.selected_package_ids),
            "auto_added_requirement_ids": list(self.auto_added_requirement_ids),
            "executable_action_keys": list(self.executable_action_keys),
            "omitted_action_keys": list(self.omitted_action_keys),
            "tags": list(self.tags),
            "executable_persistent_trigger_keys": list(
                self.executable_persistent_trigger_keys
            ),
            "omitted_persistent_trigger_keys": list(
                self.omitted_persistent_trigger_keys
            ),
            "scalars": _number_mapping(self.scalars),
            "attributes": _number_mapping(self.attributes),
            "training": _number_mapping(self.training),
            "unresolved_training_keys": list(self.unresolved_training_keys),
            "grant_sources": [source.as_dict() for source in self.grant_sources],
            "metadata": _string_mapping(self.metadata),
            "notes": list(self.notes),
            "coverage_fraction": self.coverage_fraction,
            "mechanical_signature": self.mechanical_signature,
            "construction_signature": self.construction_signature,
        }


@dataclass(frozen=True, slots=True)
class ScenarioOverlay:
    """Initial mutable-state overlay applied to one scenario slot."""

    overlay_id: str
    position: tuple[float, float] = (0.0, 0.0)
    resource_fractions: tuple[tuple[str, float], ...] = ()
    scalar_overrides: tuple[tuple[str, float], ...] = ()
    added_tags: tuple[str, ...] = ()
    removed_tags: tuple[str, ...] = ()
    initial_effect_keys: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.overlay_id, "overlay_id")
        if not isinstance(self.position, tuple) or len(self.position) != 2:
            raise CompositionError("position must be an (x, y) tuple")
        _finite(self.position[0], "position.x")
        _finite(self.position[1], "position.y")
        _validate_number_pairs(self.resource_fractions, "resource_fractions")
        for key, value in self.resource_fractions:
            if value < 0.0 or value > 1.0:
                raise CompositionError(
                    f"resource_fractions.{key} must be between zero and one"
                )
        _validate_number_pairs(self.scalar_overrides, "scalar_overrides")
        for values, name in (
            (self.added_tags, "added_tags"),
            (self.removed_tags, "removed_tags"),
            (self.initial_effect_keys, "initial_effect_keys"),
        ):
            _unique_strings(values, name)
        if set(self.added_tags) & set(self.removed_tags):
            raise CompositionError("an overlay cannot both add and remove a tag")
        _validate_string_pairs(self.metadata, "metadata")

    def mechanical_payload(self) -> dict[str, object]:
        return {
            "position": [float(self.position[0]), float(self.position[1])],
            "resource_fractions": _number_mapping(self.resource_fractions),
            "scalar_overrides": _number_mapping(self.scalar_overrides),
            "added_tags": sorted(self.added_tags),
            "removed_tags": sorted(self.removed_tags),
            "initial_effect_keys": sorted(self.initial_effect_keys),
        }

    @property
    def mechanical_signature(self) -> str:
        return _canonical_digest(self.mechanical_payload())

    def as_dict(self) -> dict[str, object]:
        return {
            "overlay_id": self.overlay_id,
            **self.mechanical_payload(),
            "metadata": _string_mapping(self.metadata),
            "mechanical_signature": self.mechanical_signature,
        }


@dataclass(frozen=True, slots=True)
class ScenarioSlotView:
    """Scenario-owned identity and initial state, independent of a build."""

    slot_id: str
    entity_id: str
    overlay: ScenarioOverlay
    entity_kind: str = "actor"
    legacy_team_id: str | None = None
    affiliation_entity_id: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.slot_id, "slot_id")
        _identifier(self.entity_id, "entity_id")
        _identifier(self.entity_kind, "entity_kind")
        if not isinstance(self.overlay, ScenarioOverlay):
            raise CompositionError("overlay must be a ScenarioOverlay")
        _optional_identifier(self.legacy_team_id, "legacy_team_id")
        _optional_identifier(self.affiliation_entity_id, "affiliation_entity_id")
        _validate_string_pairs(self.metadata, "metadata")

    def mechanical_payload(self) -> dict[str, object]:
        return {
            "slot_id": self.slot_id,
            "entity_id": self.entity_id,
            "entity_kind": self.entity_kind,
            "legacy_team_id": self.legacy_team_id,
            "affiliation_entity_id": self.affiliation_entity_id,
            "overlay_signature": self.overlay.mechanical_signature,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.mechanical_payload(),
            "overlay": self.overlay.as_dict(),
            "metadata": _string_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ResolvedScenarioView:
    """Immutable scenario layout; affiliation semantics remain external."""

    scenario_id: str
    ruleset_revision: str
    environment_profile_id: str
    slots: tuple[ScenarioSlotView, ...]
    affiliation_snapshot_id: str | None = None
    affiliation_snapshot_digest: str | None = None
    affiliation_revision: int = 0
    duration_limit_ms: int | None = None
    tick_ms: int | None = None
    environment_tags: tuple[str, ...] = ()
    environment_scalars: tuple[tuple[str, float], ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.scenario_id, "scenario_id"),
            (self.ruleset_revision, "ruleset_revision"),
            (self.environment_profile_id, "environment_profile_id"),
        ):
            _identifier(value, name)
        if not self.slots:
            raise CompositionError("a scenario requires at least one slot")
        _unique_strings(tuple(slot.slot_id for slot in self.slots), "slot ids")
        _unique_strings(tuple(slot.entity_id for slot in self.slots), "entity ids")
        _optional_identifier(self.affiliation_snapshot_id, "affiliation_snapshot_id")
        _optional_identifier(
            self.affiliation_snapshot_digest,
            "affiliation_snapshot_digest",
        )
        _non_negative_integer(self.affiliation_revision, "affiliation_revision")
        for value, name in (
            (self.duration_limit_ms, "duration_limit_ms"),
            (self.tick_ms, "tick_ms"),
        ):
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise CompositionError(f"{name} must be a positive integer or null")
        _unique_strings(self.environment_tags, "environment_tags")
        _validate_number_pairs(self.environment_scalars, "environment_scalars")
        _validate_string_pairs(self.metadata, "metadata")

    def mechanical_payload(self) -> dict[str, object]:
        return {
            "ruleset_revision": self.ruleset_revision,
            "environment_profile_id": self.environment_profile_id,
            "slots": [
                slot.mechanical_payload()
                for slot in sorted(self.slots, key=lambda value: value.slot_id)
            ],
            "affiliation_snapshot_id": self.affiliation_snapshot_id,
            "affiliation_snapshot_digest": self.affiliation_snapshot_digest,
            "affiliation_revision": self.affiliation_revision,
            "duration_limit_ms": self.duration_limit_ms,
            "tick_ms": self.tick_ms,
            "environment_tags": sorted(self.environment_tags),
            "environment_scalars": _number_mapping(self.environment_scalars),
        }

    @property
    def scenario_signature(self) -> str:
        return _canonical_digest(self.mechanical_payload())

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            **self.mechanical_payload(),
            "slots": [slot.as_dict() for slot in self.slots],
            "metadata": _string_mapping(self.metadata),
            "scenario_signature": self.scenario_signature,
        }


@dataclass(frozen=True, slots=True)
class SimulationParticipantView:
    slot_id: str
    build: ResolvedBuildView
    policy_key: str
    policy_parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.slot_id, "slot_id")
        if not isinstance(self.build, ResolvedBuildView):
            raise CompositionError("build must be a ResolvedBuildView")
        _identifier(self.policy_key, "policy_key")
        _validate_string_pairs(self.policy_parameters, "policy_parameters")

    def mechanical_payload(self) -> dict[str, object]:
        return {
            "slot_id": self.slot_id,
            "build_mechanical_signature": self.build.mechanical_signature,
            "policy_key": self.policy_key,
            "policy_parameters": _string_mapping(self.policy_parameters),
        }

    @property
    def participant_signature(self) -> str:
        return _canonical_digest(self.mechanical_payload())

    def as_dict(self) -> dict[str, object]:
        return {
            **self.mechanical_payload(),
            "build": self.build.as_dict(),
            "participant_signature": self.participant_signature,
        }


@dataclass(frozen=True, slots=True)
class SimulationCaseView:
    """One fully selected build/policy/scenario permutation and seed."""

    case_id: str
    scenario: ResolvedScenarioView
    participants: tuple[SimulationParticipantView, ...]
    seed: int
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.case_id, "case_id")
        if not isinstance(self.scenario, ResolvedScenarioView):
            raise CompositionError("scenario must be a ResolvedScenarioView")
        if not self.participants:
            raise CompositionError("a simulation case requires participants")
        _unique_strings(
            tuple(participant.slot_id for participant in self.participants),
            "participant slot ids",
        )
        scenario_slots = {slot.slot_id for slot in self.scenario.slots}
        participant_slots = {participant.slot_id for participant in self.participants}
        if scenario_slots != participant_slots:
            missing = scenario_slots - participant_slots
            unknown = participant_slots - scenario_slots
            details: list[str] = []
            if missing:
                details.append("missing: " + ", ".join(sorted(missing)))
            if unknown:
                details.append("unknown: " + ", ".join(sorted(unknown)))
            raise CompositionError("participant slots do not match scenario slots (" + "; ".join(details) + ")")
        _non_negative_integer(self.seed, "seed")
        _validate_string_pairs(self.metadata, "metadata")

    def mechanical_payload(self) -> dict[str, object]:
        return {
            "scenario_signature": self.scenario.scenario_signature,
            "participants": [
                participant.mechanical_payload()
                for participant in sorted(
                    self.participants,
                    key=lambda value: value.slot_id,
                )
            ],
            "seed": self.seed,
        }

    @property
    def case_signature(self) -> str:
        return _canonical_digest(self.mechanical_payload())

    def construction_payload(self) -> dict[str, object]:
        return {
            **self.mechanical_payload(),
            "build_construction_signatures": {
                participant.slot_id: participant.build.construction_signature
                for participant in sorted(
                    self.participants,
                    key=lambda value: value.slot_id,
                )
            },
        }

    @property
    def construction_signature(self) -> str:
        return _canonical_digest(self.construction_payload())

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "scenario": self.scenario.as_dict(),
            "participants": [participant.as_dict() for participant in self.participants],
            "seed": self.seed,
            "metadata": _string_mapping(self.metadata),
            "case_signature": self.case_signature,
            "construction_signature": self.construction_signature,
        }


def canonical_json(value: Any) -> str:
    """Return deterministic JSON for an artifact or signature payload."""

    if hasattr(value, "as_dict"):
        value = value.as_dict()
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
