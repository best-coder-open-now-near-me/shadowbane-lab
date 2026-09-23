"""Interactive metadata lookup over installed WorldDef location placements."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, replace
from math import cos, radians, sin
from pathlib import Path

from shadowbane_lab.travel import (
    WorldDestinationCatalog,
    build_world_destination_catalog,
    load_world_destination_overrides,
)
from shadowbane_lab.world_data import WorldDefinition, ZonePlacement, load_world_definition

_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class LocationLookupError(ValueError):
    """Raised when destination and placement metadata cannot be joined safely."""


@dataclass(frozen=True, slots=True)
class LocationMetadata:
    name: str
    aliases: tuple[str, ...]
    world: str
    world_number: int
    zone: str
    parent_zone: str
    zone_path: tuple[str, ...]
    lt: float
    lg: float
    template_id: int | None
    local_center_x: float | None
    local_center_z: float | None
    placement_y_offset: float | None
    cumulative_y_offset: float | None
    world_rotation_degrees: float | None
    major_radius: float | None
    minor_radius: float | None
    peace_zone: bool | None
    zone_load_file: str | None
    arrival_radius: float | None
    attributes: tuple[tuple[str, str], ...]
    source: str
    source_file: str


@dataclass(frozen=True, slots=True)
class LocationMatch:
    score: float
    metadata: LocationMetadata


@dataclass(frozen=True, slots=True)
class _PlacementMetadata:
    zone: str
    parent_zone: str
    zone_path: tuple[str, ...]
    lt: float
    lg: float
    template_id: int
    local_center_x: float
    local_center_z: float
    placement_y_offset: float | None
    cumulative_y_offset: float
    world_rotation_degrees: float
    major_radius: float | None
    minor_radius: float | None
    peace_zone: bool | None
    zone_load_file: str | None
    attributes: tuple[tuple[str, str], ...]


class LocationCatalog:
    """Rich metadata joined to the same fuzzy destination catalog used by ``/go``."""

    def __init__(
        self,
        world: WorldDefinition,
        destinations: WorldDestinationCatalog,
        metadata: tuple[LocationMetadata, ...],
    ) -> None:
        self.world = world
        self.destinations = destinations
        self.metadata = metadata
        self._metadata_by_identity = {
            _destination_identity(
                item.aliases,
                item.template_id,
                item.lt,
                item.lg,
                item.source,
            ): item
            for item in metadata
        }
        if len(self._metadata_by_identity) != len(metadata):
            raise LocationLookupError("location catalog contains duplicate destination identities")

    def search(self, query: str, *, limit: int = 8) -> tuple[LocationMatch, ...]:
        results = self.destinations.search(query, limit=limit)
        matches = []
        for result in results:
            identity = _destination_identity(
                result.aliases,
                result.template_id,
                result.destination.lt,
                result.destination.lg,
                result.source,
            )
            try:
                metadata = self._metadata_by_identity[identity]
            except KeyError as exc:
                raise LocationLookupError(
                    f"destination '{result.canonical_name}' has no placement metadata"
                ) from exc
            matches.append(
                LocationMatch(
                    score=result.score,
                    metadata=replace(metadata, name=result.canonical_name),
                )
            )
        return tuple(matches)


def load_location_catalog(
    world_def: str | Path,
    *,
    overrides: str | Path | None = None,
) -> LocationCatalog:
    """Load world placements and optional confirmed destinations into one search index."""

    world_path = Path(world_def).resolve()
    world = load_world_definition(world_path)
    base_catalog = build_world_destination_catalog(world)
    entries = base_catalog.entries
    if overrides is not None:
        entries += load_world_destination_overrides(overrides, world=world)
    destinations = WorldDestinationCatalog(world, entries)
    placement_index = _index_world_placements(world)
    metadata = []

    for entry in destinations.entries:
        if entry.source == "client_world_definition" and entry.template_id is not None:
            key = _placement_identity(
                entry.template_id,
                entry.destination.lt,
                entry.destination.lg,
            )
            candidates = placement_index.get(key)
            if not candidates:
                raise LocationLookupError(
                    f"destination '{entry.names[0]}' has no matching WorldDef placement"
                )
            placement = candidates.popleft()
            metadata.append(
                LocationMetadata(
                    name=entry.names[0],
                    aliases=entry.names,
                    world=world.name,
                    world_number=world.number,
                    zone=placement.zone,
                    parent_zone=placement.parent_zone,
                    zone_path=placement.zone_path,
                    lt=entry.destination.lt,
                    lg=entry.destination.lg,
                    template_id=entry.template_id,
                    local_center_x=placement.local_center_x,
                    local_center_z=placement.local_center_z,
                    placement_y_offset=placement.placement_y_offset,
                    cumulative_y_offset=placement.cumulative_y_offset,
                    world_rotation_degrees=placement.world_rotation_degrees,
                    major_radius=placement.major_radius,
                    minor_radius=placement.minor_radius,
                    peace_zone=placement.peace_zone,
                    zone_load_file=placement.zone_load_file,
                    arrival_radius=None,
                    attributes=placement.attributes,
                    source=entry.source,
                    source_file=str(world_path),
                )
            )
            continue

        metadata.append(
            LocationMetadata(
                name=entry.names[0],
                aliases=entry.names,
                world=world.name,
                world_number=world.number,
                zone="Confirmed override",
                parent_zone=world.name,
                zone_path=(world.name, "Confirmed override"),
                lt=entry.destination.lt,
                lg=entry.destination.lg,
                template_id=entry.template_id,
                local_center_x=None,
                local_center_z=None,
                placement_y_offset=None,
                cumulative_y_offset=None,
                world_rotation_degrees=None,
                major_radius=None,
                minor_radius=None,
                peace_zone=None,
                zone_load_file=None,
                arrival_radius=entry.destination.arrival_radius,
                attributes=(),
                source=entry.source,
                source_file=str(Path(overrides).resolve()),
            )
        )
    return LocationCatalog(world, destinations, tuple(metadata))


def _index_world_placements(
    world: WorldDefinition,
) -> dict[tuple[int, float, float], deque[_PlacementMetadata]]:
    indexed: dict[tuple[int, float, float], deque[_PlacementMetadata]] = defaultdict(deque)

    def visit(
        placement: ZonePlacement,
        *,
        parent_x: float,
        parent_z: float,
        parent_rotation: float,
        parent_y_offset: float,
        parent_path: tuple[str, ...],
    ) -> None:
        local_x = placement.center_x or 0.0
        local_z = placement.center_z or 0.0
        angle = radians(parent_rotation)
        world_x = parent_x + local_x * cos(angle) + local_z * sin(angle)
        world_z = parent_z - local_x * sin(angle) + local_z * cos(angle)
        world_rotation = parent_rotation + (placement.y_rotation or 0.0)
        world_y_offset = parent_y_offset + (placement.y_offset or 0.0)
        label = _placement_label(placement)
        zone_path = parent_path + (label,)

        if (
            (placement.name or placement.zone_load_file)
            and placement.center_x is not None
            and placement.center_z is not None
        ):
            lt = _clean_coordinate(world_x)
            lg = _clean_coordinate(-world_z)
            key = _placement_identity(placement.template_id, lt, lg)
            indexed[key].append(
                _PlacementMetadata(
                    zone=label,
                    parent_zone=parent_path[-1] if parent_path else world.name,
                    zone_path=zone_path,
                    lt=lt,
                    lg=lg,
                    template_id=placement.template_id,
                    local_center_x=placement.center_x,
                    local_center_z=placement.center_z,
                    placement_y_offset=placement.y_offset,
                    cumulative_y_offset=_clean_coordinate(world_y_offset),
                    world_rotation_degrees=_clean_coordinate(world_rotation),
                    major_radius=placement.major_radius,
                    minor_radius=placement.minor_radius,
                    peace_zone=placement.peace_zone,
                    zone_load_file=placement.zone_load_file,
                    attributes=placement.attributes,
                )
            )
        for child in placement.children:
            visit(
                child,
                parent_x=world_x,
                parent_z=world_z,
                parent_rotation=world_rotation,
                parent_y_offset=world_y_offset,
                parent_path=zone_path,
            )

    for root in world.zones:
        visit(
            root,
            parent_x=0.0,
            parent_z=0.0,
            parent_rotation=0.0,
            parent_y_offset=0.0,
            parent_path=(),
        )
    return indexed


def _placement_label(placement: ZonePlacement) -> str:
    if placement.name:
        return placement.name
    if placement.zone_load_file:
        stem = Path(placement.zone_load_file).stem.replace("_", " ")
        return " ".join(_CAMEL_CASE_BOUNDARY.sub(" ", stem).split())
    return f"Template {placement.template_id}"


def _clean_coordinate(value: float) -> float:
    rounded = round(value)
    return float(rounded) if abs(value - rounded) < 1e-9 else value


def _placement_identity(template_id: int, lt: float, lg: float) -> tuple[int, float, float]:
    return template_id, round(lt, 9), round(lg, 9)


def _destination_identity(
    aliases: tuple[str, ...],
    template_id: int | None,
    lt: float,
    lg: float,
    source: str,
) -> tuple[tuple[str, ...], int | None, float, float, str]:
    return aliases, template_id, round(lt, 9), round(lg, 9), source


def _match_payload(match: LocationMatch) -> dict[str, object]:
    item = match.metadata
    return {
        "MatchScore": round(match.score, 4),
        "Name": item.name,
        "Aliases": list(item.aliases),
        "World": item.world,
        "WorldNumber": item.world_number,
        "Zone": item.zone,
        "ParentZone": item.parent_zone,
        "ZonePath": list(item.zone_path),
        "LT": item.lt,
        "LG": item.lg,
        "TemplateId": item.template_id,
        "LocalCenterX": item.local_center_x,
        "LocalCenterZ": item.local_center_z,
        "PlacementYOffset": item.placement_y_offset,
        "CumulativeYOffset": item.cumulative_y_offset,
        "WorldRotationDegrees": item.world_rotation_degrees,
        "MajorRadius": item.major_radius,
        "MinorRadius": item.minor_radius,
        "PeaceZone": item.peace_zone,
        "ZoneLoadFile": item.zone_load_file,
        "ArrivalRadius": item.arrival_radius,
        "Attributes": dict(item.attributes),
        "Source": item.source,
        "SourceFile": item.source_file,
    }


def _display_value(value: object) -> str:
    if value is None:
        return "(not specified)"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _show_location(match: LocationMatch) -> None:
    item = match.metadata
    print()
    print(item.name)
    print(f"  World:          {item.world} (#{item.world_number})")
    print(f"  Zone:           {item.zone}")
    print(f"  Parent zone:    {item.parent_zone}")
    print(f"  Zone path:      {' > '.join(item.zone_path)}")
    print(f"  LT / LG:        {item.lt:g} / {item.lg:g}")
    print(f"  Template ID:    {_display_value(item.template_id)}")
    print(
        "  Local X / Z:    "
        f"{_display_value(item.local_center_x)} / {_display_value(item.local_center_z)}"
    )
    print(
        f"  Y offset:       {_display_value(item.placement_y_offset)} "
        f"(composed: {_display_value(item.cumulative_y_offset)})"
    )
    print(f"  Rotation:       {_display_value(item.world_rotation_degrees)} degrees")
    print(
        "  Major / minor:  "
        f"{_display_value(item.major_radius)} / {_display_value(item.minor_radius)}"
    )
    print(f"  Peace zone:     {_display_value(item.peace_zone)}")
    print(f"  Zone load file: {_display_value(item.zone_load_file)}")
    if item.arrival_radius is not None:
        print(f"  Arrival radius: {item.arrival_radius:g}")
    if len(item.aliases) > 1:
        print(f"  Aliases:        {', '.join(item.aliases)}")
    if item.attributes:
        print("  Extra fields:")
        for key, value in item.attributes:
            print(f"    {key}={value}")
    print(f"  Source:         {item.source}")


def _show_choices(matches: tuple[LocationMatch, ...]) -> None:
    print()
    print(f"{'#':>2}  {'Name':<34} {'Parent zone':<24} {'LT':>10} {'LG':>10}  Match")
    print("-" * 96)
    for index, match in enumerate(matches, start=1):
        item = match.metadata
        print(
            f"{index:>2}  {item.name[:34]:<34} {item.parent_zone[:24]:<24} "
            f"{item.lt:>10g} {item.lg:>10g}  {match.score:>4.0%}"
        )
    print("Enter a result number for full metadata, or search again.")


def _show_matches(matches: tuple[LocationMatch, ...]) -> None:
    if not matches:
        print("No location matched that name.")
    elif len(matches) == 1 or matches[0].score == 1.0:
        for match in matches:
            _show_location(match)
    else:
        _show_choices(matches)


def _run_interactive(catalog: LocationCatalog, *, limit: int) -> int:
    print(
        f"Loaded {len(catalog.metadata)} named locations for {catalog.world.name}.\n"
        "Type a location name, '?' for help, or 'q' to quit."
    )
    last_matches: tuple[LocationMatch, ...] = ()
    while True:
        try:
            query = input("Location: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if query.casefold() in {"q", "quit", "exit"}:
            return 0
        if query == "?":
            print("Enter a full name, part of a name, or a close spelling.")
            print("After a result list, enter its number to see every metadata field.")
            print("LT/LG are Shadowbane's world latitude/longitude coordinates.")
            continue
        if query.isdigit() and last_matches:
            selected = int(query)
            if 1 <= selected <= len(last_matches):
                _show_location(last_matches[selected - 1])
            else:
                print(f"Choose a result from 1 through {len(last_matches)}.")
            continue
        if not query:
            continue
        last_matches = catalog.search(query, limit=limit)
        _show_matches(last_matches)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world-def", type=Path, required=True)
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--query")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if not 1 <= arguments.limit <= 50:
        print("error: --limit must be between 1 and 50", file=sys.stderr)
        return 2
    if arguments.json and not arguments.query:
        print("error: --json requires --query", file=sys.stderr)
        return 2
    try:
        catalog = load_location_catalog(
            arguments.world_def,
            overrides=arguments.overrides,
        )
        if arguments.query:
            matches = catalog.search(arguments.query, limit=arguments.limit)
            if arguments.json:
                print(json.dumps([_match_payload(item) for item in matches], indent=2))
            else:
                _show_matches(matches)
            return 0
        return _run_interactive(catalog, limit=arguments.limit)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
