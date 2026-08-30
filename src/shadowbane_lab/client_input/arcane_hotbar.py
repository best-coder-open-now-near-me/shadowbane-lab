"""Read Shadowbane's character hotbar without changing it."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from shadowbane_lab.client_input.model import KeyActivation


class ArcaneHotbarLoadError(ValueError):
    """Raised when a SCREEN_GAME hotbar table is missing or malformed."""


class ArcaneClientPower(StrEnum):
    """Verified legacy power IDs recovered from the installed WonderBane client."""

    SHADOW_TOUCH = "ASS-013"


_HOTBAR_SLOT_COUNT = 12
_HBI_PATTERN = re.compile(r"^BEGINHBI\s+(?P<slot_index>\d+)\s+(?P<item_type>\S+)$")
_PROPERTY_PATTERN = re.compile(r"^(?P<name>[A-Z][A-Z0-9_]*)=\s*(?P<value>.*)$")
_CURRENT_SET_PATTERN = re.compile(r"^CURRENTSET=\s*(?P<set_index>\d+)$")


@dataclass(frozen=True, slots=True)
class ArcaneHotbarSlot:
    """One F1-F12 slot from a character hotbar set."""

    slot_index: int
    item_type: str
    properties: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.slot_index, bool) or not 0 <= self.slot_index < _HOTBAR_SLOT_COUNT:
            raise ValueError("hotbar slot_index must be in [0, 11]")
        if not isinstance(self.item_type, str) or not self.item_type:
            raise ValueError("hotbar item_type must be a non-empty string")
        names = tuple(name for name, _ in self.properties)
        if any(not name or not isinstance(value, str) for name, value in self.properties):
            raise ValueError("hotbar properties must contain non-empty names and text values")
        if len(names) != len(set(names)):
            raise ValueError("hotbar slot properties must have unique names")
        if self.item_type == "EMPTY" and self.properties:
            raise ValueError("empty hotbar slots cannot contain properties")
        if self.item_type == "PowerHotButtonInfo" and not self.power_name:
            raise ValueError("power hotbar slots require POWERNAME")

    @property
    def activation_key(self) -> str:
        return f"f{self.slot_index + 1}"

    @property
    def activation(self) -> KeyActivation:
        return KeyActivation(self.activation_key)

    @property
    def occupied(self) -> bool:
        return self.item_type != "EMPTY"

    @property
    def power_name(self) -> str | None:
        if self.item_type != "PowerHotButtonInfo":
            return None
        return dict(self.properties).get("POWERNAME")


@dataclass(frozen=True, slots=True)
class ArcaneHotbarSet:
    """One complete twelve-slot character hotbar set."""

    set_index: int
    slots: tuple[ArcaneHotbarSlot, ...]

    def __post_init__(self) -> None:
        if isinstance(self.set_index, bool) or self.set_index < 0:
            raise ValueError("hotbar set_index must be a non-negative integer")
        slot_indices = tuple(slot.slot_index for slot in self.slots)
        if slot_indices != tuple(range(_HOTBAR_SLOT_COUNT)):
            raise ValueError("each hotbar set must contain ordered slots 0 through 11")

    def slots_for_power(self, power_name: str) -> tuple[ArcaneHotbarSlot, ...]:
        if not isinstance(power_name, str) or not power_name:
            raise ValueError("power_name must be a non-empty string")
        return tuple(slot for slot in self.slots if slot.power_name == power_name)


@dataclass(frozen=True, slots=True)
class ArcaneHotbarTable:
    """All character hotbar sets and the currently active set."""

    current_set_index: int
    sets: tuple[ArcaneHotbarSet, ...]

    def __post_init__(self) -> None:
        if not self.sets:
            raise ValueError("hotbar must contain at least one set")
        set_indices = tuple(item.set_index for item in self.sets)
        if set_indices != tuple(range(len(self.sets))):
            raise ValueError("hotbar set indices must be contiguous and ordered")
        if isinstance(self.current_set_index, bool) or not 0 <= self.current_set_index < len(
            self.sets
        ):
            raise ValueError("CURRENTSET does not identify an available hotbar set")

    @property
    def current_set(self) -> ArcaneHotbarSet:
        return self.sets[self.current_set_index]

    def current_slots_for_power(self, power_name: str) -> tuple[ArcaneHotbarSlot, ...]:
        return self.current_set.slots_for_power(power_name)


def load_arcane_hotbar(path: str | Path) -> ArcaneHotbarTable:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ArcaneHotbarLoadError(f"could not read SCREEN_GAME hotbar: {exc}") from exc
    return load_arcane_hotbar_text(text)


def load_arcane_hotbar_text(text: str) -> ArcaneHotbarTable:
    if not isinstance(text, str):
        raise ArcaneHotbarLoadError("SCREEN_GAME content must be text")

    found = False
    inside_hotbar = False
    current_set_index: int | None = None
    sets: list[ArcaneHotbarSet] = []
    set_slots: list[ArcaneHotbarSlot] | None = None
    slot_index: int | None = None
    slot_item_type: str | None = None
    slot_properties: list[tuple[str, str]] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not inside_hotbar:
            if stripped == "BEGINHOTBAR":
                if found:
                    raise ArcaneHotbarLoadError("SCREEN_GAME must contain exactly one hotbar table")
                found = True
                inside_hotbar = True
            continue

        if slot_index is not None:
            if stripped == "ENDHBI":
                assert slot_item_type is not None
                try:
                    assert set_slots is not None
                    set_slots.append(
                        ArcaneHotbarSlot(
                            slot_index=slot_index,
                            item_type=slot_item_type,
                            properties=tuple(slot_properties),
                        )
                    )
                except ValueError as exc:
                    raise ArcaneHotbarLoadError(
                        f"invalid hotbar slot ending at line {line_number}: {exc}"
                    ) from exc
                slot_index = None
                slot_item_type = None
                slot_properties = []
                continue
            match = _PROPERTY_PATTERN.fullmatch(stripped)
            if match is None:
                raise ArcaneHotbarLoadError(f"malformed hotbar slot property at line {line_number}")
            slot_properties.append(
                (match.group("name"), _decode_property(match.group("value"), line_number))
            )
            continue

        if set_slots is not None:
            if stripped == "ENDSET":
                try:
                    sets.append(ArcaneHotbarSet(len(sets), tuple(set_slots)))
                except ValueError as exc:
                    raise ArcaneHotbarLoadError(
                        f"invalid hotbar set ending at line {line_number}: {exc}"
                    ) from exc
                set_slots = None
                continue
            match = _HBI_PATTERN.fullmatch(stripped)
            if match is None:
                raise ArcaneHotbarLoadError(f"malformed hotbar slot header at line {line_number}")
            slot_index = int(match.group("slot_index"))
            slot_item_type = match.group("item_type")
            slot_properties = []
            continue

        if stripped == "ENDHOTBAR":
            inside_hotbar = False
            continue
        if stripped == "BEGINSET":
            set_slots = []
            continue
        match = _CURRENT_SET_PATTERN.fullmatch(stripped)
        if match is not None:
            if current_set_index is not None:
                raise ArcaneHotbarLoadError("hotbar must contain exactly one CURRENTSET")
            current_set_index = int(match.group("set_index"))
            continue
        raise ArcaneHotbarLoadError(f"malformed hotbar record at line {line_number}")

    if not found:
        raise ArcaneHotbarLoadError("SCREEN_GAME does not contain BEGINHOTBAR")
    if inside_hotbar:
        raise ArcaneHotbarLoadError("SCREEN_GAME hotbar table is not terminated")
    if current_set_index is None:
        raise ArcaneHotbarLoadError("hotbar does not contain CURRENTSET")
    try:
        return ArcaneHotbarTable(current_set_index, tuple(sets))
    except ValueError as exc:
        raise ArcaneHotbarLoadError(str(exc)) from exc


def _decode_property(raw_value: str, line_number: int) -> str:
    if not raw_value.startswith('"'):
        return raw_value
    if len(raw_value) < 2 or not raw_value.endswith('"'):
        raise ArcaneHotbarLoadError(f"unterminated quoted hotbar property at line {line_number}")
    return raw_value[1:-1]
