"""Parse the client's plaintext nested ``WorldDef`` placement tree."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_BEGIN_ZONE = re.compile(r"^<BEGINZONE>\s+(?P<template_id>\d+)\s*$", re.IGNORECASE)
_END_ZONE = re.compile(r"^<ENDZONE>\s*$", re.IGNORECASE)
_ASSIGNMENT = re.compile(r"^(?P<key>[A-Z_]+)\s*=\s*(?P<value>.*?)\s*$", re.IGNORECASE)


class WorldDefinitionFormatError(ValueError):
    """Raised when a WorldDef file has invalid nesting or required fields."""


@dataclass(frozen=True, slots=True)
class ZonePlacement:
    template_id: int
    center_x: float | None
    center_z: float | None
    y_offset: float | None
    y_rotation: float | None
    major_radius: float | None
    minor_radius: float | None
    zone_load_file: str | None
    peace_zone: bool | None
    attributes: tuple[tuple[str, str], ...]
    children: tuple[ZonePlacement, ...]

    def walk(self) -> tuple[ZonePlacement, ...]:
        descendants = [self]
        for child in self.children:
            descendants.extend(child.walk())
        return tuple(descendants)


@dataclass(frozen=True, slots=True)
class WorldDefinition:
    name: str
    number: int
    width: float
    length: float
    attributes: tuple[tuple[str, str], ...]
    zones: tuple[ZonePlacement, ...]

    def walk_zones(self) -> tuple[ZonePlacement, ...]:
        result = []
        for zone in self.zones:
            result.extend(zone.walk())
        return tuple(result)


@dataclass(slots=True)
class _ZoneBuilder:
    template_id: int
    values: dict[str, str] = field(default_factory=dict)
    children: list[_ZoneBuilder] = field(default_factory=list)


def load_world_definition(path: str | Path) -> WorldDefinition:
    return parse_world_definition(Path(path).read_text(encoding="utf-8-sig"))


def parse_world_definition(text: str) -> WorldDefinition:
    world_values: dict[str, str] = {}
    roots: list[_ZoneBuilder] = []
    stack: list[_ZoneBuilder] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        begin = _BEGIN_ZONE.fullmatch(line)
        if begin:
            builder = _ZoneBuilder(int(begin.group("template_id")))
            if stack:
                stack[-1].children.append(builder)
            else:
                roots.append(builder)
            stack.append(builder)
            continue
        if _END_ZONE.fullmatch(line):
            if not stack:
                raise WorldDefinitionFormatError(
                    f"line {line_number}: ENDZONE has no matching BEGINZONE"
                )
            stack.pop()
            continue
        assignment = _ASSIGNMENT.fullmatch(line)
        if assignment:
            key = assignment.group("key").upper()
            value = assignment.group("value").strip().strip('"')
            destination = stack[-1].values if stack else world_values
            if key in destination:
                raise WorldDefinitionFormatError(f"line {line_number}: duplicate {key} assignment")
            destination[key] = value
            continue
        raise WorldDefinitionFormatError(f"line {line_number}: unsupported WorldDef syntax")

    if stack:
        raise WorldDefinitionFormatError("WorldDef ended before every zone was closed")
    try:
        name = world_values.pop("WORLDNAME")
        number = int(world_values.pop("WORLDNUM"))
        width = float(world_values.pop("WIDTH"))
        length = float(world_values.pop("LENGTH"))
    except (KeyError, ValueError) as exc:
        raise WorldDefinitionFormatError("WorldDef has invalid required world fields") from exc
    return WorldDefinition(
        name=name,
        number=number,
        width=width,
        length=length,
        attributes=tuple(sorted(world_values.items())),
        zones=tuple(_freeze_zone(zone) for zone in roots),
    )


def _freeze_zone(builder: _ZoneBuilder) -> ZonePlacement:
    values = dict(builder.values)
    return ZonePlacement(
        template_id=builder.template_id,
        center_x=_optional_float(values.pop("CENTX", None)),
        center_z=_optional_float(values.pop("CENTZ", None)),
        y_offset=_optional_float(values.pop("YOFFSET", None)),
        y_rotation=_optional_float(values.pop("YROT", None)),
        major_radius=_optional_float(values.pop("MAJORRAD", None)),
        minor_radius=_optional_float(values.pop("MINORRAD", None)),
        zone_load_file=values.pop("ZONELOADFILE", None),
        peace_zone=_optional_bool(values.pop("PEACEZONE", None)),
        attributes=tuple(sorted(values.items())),
        children=tuple(_freeze_zone(child) for child in builder.children),
    )


def _optional_float(value: str | None) -> float | None:
    return None if value is None else float(value)


def _optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.upper()
    if normalized == "TRUE":
        return True
    if normalized == "FALSE":
        return False
    raise WorldDefinitionFormatError(f"invalid boolean value: {value}")
