"""Resolve installed WorldDef placement names into exact LT/LG travel destinations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import get_close_matches
from math import cos, radians, sin
from pathlib import Path

from shadowbane_lab.client_observation import NativePlayerPositionObservation
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
    template_id: int
    destination: TravelDestination

    def __post_init__(self) -> None:
        if not self.names or any(not item.strip() for item in self.names):
            raise ValueError("world destination names must be non-empty")
        if isinstance(self.template_id, bool) or not isinstance(self.template_id, int):
            raise ValueError("world destination template_id must be an integer")
        if self.template_id < 0:
            raise ValueError("world destination template_id must be non-negative")
        if not isinstance(self.destination, TravelDestination):
            raise ValueError("world destination must be TravelDestination")


@dataclass(frozen=True, slots=True)
class ResolvedNamedDestination:
    query: str
    matched_name: str
    candidate_count: int
    template_id: int
    destination: TravelDestination


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
        )


def parse_named_go_command(command: str) -> str:
    if not isinstance(command, str):
        raise NamedTravelDestinationError("go command must be a string")
    match = _NAMED_GO_PATTERN.fullmatch(command)
    if match is None:
        raise NamedTravelDestinationError("named go command must use: go NAME")
    return " ".join(match.group("name").split())


def load_world_destination_catalog(path: str | Path) -> WorldDestinationCatalog:
    return build_world_destination_catalog(load_world_definition(path))


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


def _clean_coordinate(value: float) -> float:
    rounded = round(value)
    return float(rounded) if abs(value - rounded) < 1e-9 else value
