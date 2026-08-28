"""Resolve installed WorldDef placement names into exact LT/LG travel destinations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import get_close_matches
from math import cos, isfinite, radians, sin
from pathlib import Path

from shadowbane_lab.client_observation import (
    NativePlayerPositionObservation,
    NativeRunegateRegistryObservation,
)
from shadowbane_lab.travel.model import TravelDestination
from shadowbane_lab.world_data import WorldDefinition, ZonePlacement, load_world_definition

_NAMED_GO_PATTERN = re.compile(
    r"^\s*/?go\s+(?P<name>[a-z][a-z0-9 '\-_]*?)\s*$",
    re.IGNORECASE,
)
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_NAME_CHARACTER = re.compile(r"[^a-z0-9]+")


class NamedTravelDestinationError(ValueError):
    """Raised when a named destination cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class WorldDestinationEntry:
    names: tuple[str, ...]
    template_id: int | None
    destination: TravelDestination
    source: str = "client_world_definition"

    def __post_init__(self) -> None:
        if not self.names or any(not item.strip() for item in self.names):
            raise ValueError("world destination names must be non-empty")
        if self.template_id is not None and (
            isinstance(self.template_id, bool) or not isinstance(self.template_id, int)
        ):
            raise ValueError("world destination template_id must be an integer when present")
        if self.template_id is not None and self.template_id < 0:
            raise ValueError("world destination template_id must be non-negative")
        if not isinstance(self.destination, TravelDestination):
            raise ValueError("world destination must be TravelDestination")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("world destination source must be non-empty")


@dataclass(frozen=True, slots=True)
class ResolvedNamedDestination:
    query: str
    matched_name: str
    candidate_count: int
    template_id: int | None
    destination: TravelDestination
    source: str


class WorldDestinationCatalog:
    """Exact-name index over composed WorldDef placements."""

    _ALIASES = {
        "death gate": "runegate",
        "doomgate": "runegate",
        "nearest runegate": "runegate",
        "oblivion": "runegate",
        "oblivion gate": "runegate",
    }

    def __init__(self, world: WorldDefinition, entries: tuple[WorldDestinationEntry, ...]) -> None:
        if not isinstance(world, WorldDefinition):
            raise ValueError("world must be WorldDefinition")
        if not entries:
            raise NamedTravelDestinationError("WorldDef contains no named placements")
        if any(not isinstance(item, WorldDestinationEntry) for item in entries):
            raise ValueError("entries must contain WorldDestinationEntry values")
        self._world = world
        self._entries = entries
        index: dict[str, list[WorldDestinationEntry]] = {}
        for entry in entries:
            for name in entry.names:
                bucket = index.setdefault(_normalize_name(name), [])
                if entry not in bucket:
                    bucket.append(entry)
        runegates = [
            entry
            for entry in entries
            if any(
                name == "runegate" or name.startswith("runegate ")
                for name in (_normalize_name(item) for item in entry.names)
            )
        ]
        if runegates:
            index["runegate"] = list(dict.fromkeys(runegates))
        self._index = {key: tuple(value) for key, value in index.items()}

    @property
    def world_name(self) -> str:
        return self._world.name

    @property
    def entries(self) -> tuple[WorldDestinationEntry, ...]:
        return self._entries

    def with_authoritative_runegates(
        self,
        observation: NativeRunegateRegistryObservation,
    ) -> WorldDestinationCatalog:
        """Replace baked runegates with the active server registry.

        Emulator-confirmed overrides replace CityData records with the same normalized
        name or coordinates. This lets a verified correction win over an emulator record
        whose label is right but whose stored placement is not.
        """

        if not isinstance(observation, NativeRunegateRegistryObservation):
            raise ValueError("observation must be NativeRunegateRegistryObservation")
        retained = tuple(
            entry
            for entry in self._entries
            if not _is_runegate_entry(entry)
        )
        confirmed = tuple(
            entry
            for entry in self._entries
            if _is_runegate_entry(entry)
            and entry.source == "wonderbane_server_confirmed"
        )
        confirmed_names = {
            _normalize_name(name)
            for entry in confirmed
            for name in entry.names
        }
        confirmed_coordinates = {
            (round(entry.destination.lt, 3), round(entry.destination.lg, 3))
            for entry in confirmed
        }
        authoritative = tuple(
            entry
            for entry in runegate_destination_entries(observation)
            if not confirmed_names.intersection(
                _normalize_name(name) for name in entry.names
            )
            and (
                round(entry.destination.lt, 3),
                round(entry.destination.lg, 3),
            )
            not in confirmed_coordinates
        )
        return WorldDestinationCatalog(self._world, retained + confirmed + authoritative)

    def resolve(
        self,
        query: str,
        *,
        origin: NativePlayerPositionObservation,
        arrival_radius: float = 75.0,
    ) -> ResolvedNamedDestination:
        if not isinstance(query, str) or not query.strip():
            raise NamedTravelDestinationError("named destination must be non-empty")
        if not isinstance(origin, NativePlayerPositionObservation):
            raise ValueError("origin must be NativePlayerPositionObservation")
        normalized_query = _normalize_name(query)
        lookup_name = self._ALIASES.get(normalized_query, normalized_query)
        candidates = self._index.get(lookup_name, ())
        if not candidates:
            suggestions = get_close_matches(lookup_name, self._index, n=3, cutoff=0.6)
            detail = f"; try: {', '.join(suggestions)}" if suggestions else ""
            raise NamedTravelDestinationError(
                f"unknown named destination '{query.strip()}'{detail}"
            )
        selected = min(
            candidates,
            key=lambda item: item.destination.distance_from(origin),
        )
        destination = TravelDestination(
            selected.destination.lt,
            selected.destination.lg,
            arrival_radius,
        )
        matched_name = next(
            (name for name in selected.names if _normalize_name(name) == lookup_name),
            selected.names[0],
        )
        return ResolvedNamedDestination(
            query=query.strip(),
            matched_name=matched_name,
            candidate_count=len(candidates),
            template_id=selected.template_id,
            destination=destination,
            source=selected.source,
        )


def parse_named_go_command(command: str) -> str:
    if not isinstance(command, str):
        raise NamedTravelDestinationError("go command must be a string")
    match = _NAMED_GO_PATTERN.fullmatch(command)
    if match is None:
        raise NamedTravelDestinationError("named go command must use: go NAME")
    return " ".join(match.group("name").split())


def load_world_destination_catalog(
    path: str | Path,
    *,
    overrides_path: str | Path | None = None,
) -> WorldDestinationCatalog:
    world = load_world_definition(path)
    catalog = build_world_destination_catalog(world)
    if overrides_path is None:
        return catalog
    overrides = load_world_destination_overrides(overrides_path, world=world)
    return WorldDestinationCatalog(world, catalog.entries + overrides)


def load_world_destination_overrides(
    path: str | Path,
    *,
    world: WorldDefinition,
) -> tuple[WorldDestinationEntry, ...]:
    """Load emulator-confirmed destinations layered over client WorldDef candidates."""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NamedTravelDestinationError(
            f"could not load named-destination overrides: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise NamedTravelDestinationError("named-destination overrides must be an object")
    if payload.get("schema_version") != 1:
        raise NamedTravelDestinationError(
            "named-destination overrides require schema_version 1"
        )
    if payload.get("world_name") != world.name:
        raise NamedTravelDestinationError(
            "named-destination overrides target a different world"
        )
    raw_destinations = payload.get("destinations")
    if not isinstance(raw_destinations, list):
        raise NamedTravelDestinationError(
            "named-destination overrides require a destinations array"
        )

    entries: list[WorldDestinationEntry] = []
    for index, raw in enumerate(raw_destinations):
        label = f"named-destination override {index}"
        if not isinstance(raw, dict):
            raise NamedTravelDestinationError(f"{label} must be an object")
        raw_names = raw.get("names")
        if (
            not isinstance(raw_names, list)
            or not raw_names
            or any(not isinstance(item, str) or not item.strip() for item in raw_names)
        ):
            raise NamedTravelDestinationError(f"{label} requires non-empty names")
        names = tuple(dict.fromkeys(" ".join(item.split()) for item in raw_names))
        lt = _override_coordinate(raw.get("lt"), label=label, axis="LT")
        lg = _override_coordinate(raw.get("lg"), label=label, axis="LG")
        if not 0.0 <= lt <= world.length * 256.0:
            raise NamedTravelDestinationError(f"{label} has LT outside world bounds")
        if not 0.0 <= lg <= world.width * 256.0:
            raise NamedTravelDestinationError(f"{label} has LG outside world bounds")
        arrival_radius = raw.get("arrival_radius", 75.0)
        if (
            isinstance(arrival_radius, bool)
            or not isinstance(arrival_radius, (int, float))
            or not isfinite(float(arrival_radius))
            or float(arrival_radius) <= 0
        ):
            raise NamedTravelDestinationError(
                f"{label} arrival_radius must be a positive finite number"
            )
        source = raw.get("source")
        if not isinstance(source, str) or not source.strip():
            raise NamedTravelDestinationError(f"{label} requires a non-empty source")
        entries.append(
            WorldDestinationEntry(
                names=names,
                template_id=None,
                destination=TravelDestination(lt, lg, float(arrival_radius)),
                source=source.strip(),
            )
        )
    return tuple(entries)


def runegate_destination_entries(
    observation: NativeRunegateRegistryObservation,
) -> tuple[WorldDestinationEntry, ...]:
    """Convert the active server registry into named travel destinations."""

    if not isinstance(observation, NativeRunegateRegistryObservation):
        raise ValueError("observation must be NativeRunegateRegistryObservation")
    entries = []
    for runegate in observation.runegates:
        label = " ".join(runegate.zone_name.split())
        discriminator = label or str(runegate.object_uuid)
        names = (
            f"Runegate {discriminator}",
            f"{discriminator} Runegate",
        )
        entries.append(
            WorldDestinationEntry(
                names=names,
                template_id=None,
                destination=TravelDestination(runegate.lt, runegate.lg),
                source="server_citydata_runegate_registry",
            )
        )
    return tuple(entries)


def build_world_destination_catalog(world: WorldDefinition) -> WorldDestinationCatalog:
    if not isinstance(world, WorldDefinition):
        raise ValueError("world must be WorldDefinition")
    entries: list[WorldDestinationEntry] = []

    def visit(
        placement: ZonePlacement,
        *,
        parent_x: float,
        parent_z: float,
        parent_rotation: float,
    ) -> None:
        local_x = 0.0 if placement.center_x is None else placement.center_x
        local_z = 0.0 if placement.center_z is None else placement.center_z
        angle = radians(parent_rotation)
        world_x = parent_x + local_x * cos(angle) + local_z * sin(angle)
        world_z = parent_z - local_x * sin(angle) + local_z * cos(angle)
        world_rotation = parent_rotation + (
            0.0 if placement.y_rotation is None else placement.y_rotation
        )

        names = _placement_names(placement)
        if names and placement.center_x is not None and placement.center_z is not None:
            lt = _clean_coordinate(world_x)
            lg = _clean_coordinate(-world_z)
            if not 0.0 <= lt <= world.length * 256.0:
                raise NamedTravelDestinationError(
                    f"named placement '{names[0]}' has LT outside world bounds"
                )
            if not 0.0 <= lg <= world.width * 256.0:
                raise NamedTravelDestinationError(
                    f"named placement '{names[0]}' has LG outside world bounds"
                )
            entries.append(
                WorldDestinationEntry(
                    names=names,
                    template_id=placement.template_id,
                    destination=TravelDestination(lt, lg),
                )
            )
        for child in placement.children:
            visit(
                child,
                parent_x=world_x,
                parent_z=world_z,
                parent_rotation=world_rotation,
            )

    for root in world.zones:
        visit(root, parent_x=0.0, parent_z=0.0, parent_rotation=0.0)
    return WorldDestinationCatalog(world, tuple(entries))


def _placement_names(placement: ZonePlacement) -> tuple[str, ...]:
    names: list[str] = []
    if placement.name is not None:
        names.append(placement.name)
    if placement.zone_load_file is not None:
        stem = Path(placement.zone_load_file).stem.replace("_", " ")
        humanized = _CAMEL_CASE_BOUNDARY.sub(" ", stem)
        if _normalize_name(humanized) not in {_normalize_name(item) for item in names}:
            names.append(humanized)
    return tuple(names)


def _normalize_name(value: str) -> str:
    without_apostrophes = value.casefold().replace("'", "")
    return " ".join(_NON_NAME_CHARACTER.sub(" ", without_apostrophes).split())


def _is_runegate_entry(entry: WorldDestinationEntry) -> bool:
    return any("runegate" in _normalize_name(name).split() for name in entry.names)


def _clean_coordinate(value: float) -> float:
    rounded = round(value)
    return float(rounded) if abs(value - rounded) < 1e-9 else value


def _override_coordinate(value: object, *, label: str, axis: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
    ):
        raise NamedTravelDestinationError(f"{label} {axis} must be a finite number")
    return float(value)
