"""Read Shadowbane's native ArcanePref hotkey table without changing it."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from shadowbane_lab.client_input.model import HotkeyActivation, KeyActivation


class ArcaneHotkeyLoadError(ValueError):
    """Raised when an ArcanePref hotkey table is missing or malformed."""


class ArcaneClientAction(IntEnum):
    """Verified native message IDs exposed by the installed WonderBane UI."""

    WORLD_MAP = 48
    CLEAR_TARGET = 102
    TARGET_SELF = 182
    TARGET_NEXT_ALLY = 184
    TARGET_PREVIOUS_ALLY = 185
    TARGET_NEXT_PLAYER = 186
    TARGET_PREVIOUS_PLAYER = 187
    TARGET_NEXT_MOB = 188
    TARGET_PREVIOUS_MOB = 189


_KEY_PATTERN = re.compile(
    r'^\s*KEY=\s*"(?P<key>[^"]+)"\s+'
    r"(?P<shift>TRUE|FALSE)\s+"
    r"(?P<control>TRUE|FALSE)\s+"
    r"(?P<alt>TRUE|FALSE)\s+"
    r"(?P<action>-?\d+)\s+"
    r"(?P<parameter_one>-?\d+)\s+"
    r"(?P<parameter_two>-?\d+)\s+"
    r'"(?P<argument>[^"]*)"\s*$'
)

_PYAUTOGUI_KEYS = {
    "Apostrophe": "'",
    "BackSlash": "\\",
    "Backspace": "backspace",
    "Comma": ",",
    "Delete": "delete",
    "Down Arrow": "down",
    "End": "end",
    "Enter": "enter",
    "Escape": "esc",
    "ForwardSlash": "/",
    "Home": "home",
    "Insert": "insert",
    "Keypad Add": "add",
    "Keypad Decimal": "decimal",
    "Keypad Divide": "divide",
    "Keypad Multiply": "multiply",
    "Keypad Subtract": "subtract",
    "LBracket": "[",
    "Left Arrow": "left",
    "Page Down": "pagedown",
    "Page Up": "pageup",
    "Period": ".",
    "RBracket": "]",
    "Right Arrow": "right",
    "SemiColon": ";",
    "Space": "space",
    "Tab": "tab",
    "Up Arrow": "up",
}


@dataclass(frozen=True, slots=True)
class ArcaneHotkeyBinding:
    """One lossless KEY record from ArcanePref.cfg."""

    key: str
    shift: bool
    control: bool
    alt: bool
    action_code: int
    parameter_one: int
    parameter_two: int
    argument: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("key must be a non-empty string")
        for value, field_name in (
            (self.shift, "shift"),
            (self.control, "control"),
            (self.alt, "alt"),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{field_name} must be a boolean")
        for value, field_name in (
            (self.action_code, "action_code"),
            (self.parameter_one, "parameter_one"),
            (self.parameter_two, "parameter_two"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
        if not isinstance(self.argument, str):
            raise ValueError("argument must be a string")

    @property
    def input_keys(self) -> tuple[str, ...]:
        """Return the binding in the key vocabulary used by the input backend."""

        modifiers = tuple(
            key
            for enabled, key in (
                (self.shift, "shift"),
                (self.control, "ctrl"),
                (self.alt, "alt"),
            )
            if enabled
        )
        return (*modifiers, _pyautogui_key(self.key))

    @property
    def activation(self) -> KeyActivation | HotkeyActivation:
        keys = self.input_keys
        if len(keys) == 1:
            return KeyActivation(keys[0])
        return HotkeyActivation(keys)


@dataclass(frozen=True, slots=True)
class ArcaneHotkeyTable:
    """An immutable native hotkey table with action-oriented lookup."""

    bindings: tuple[ArcaneHotkeyBinding, ...]

    def __post_init__(self) -> None:
        if any(not isinstance(item, ArcaneHotkeyBinding) for item in self.bindings):
            raise ValueError("bindings must contain ArcaneHotkeyBinding values")
        chords = tuple(item.input_keys for item in self.bindings)
        if len(chords) != len(set(chords)):
            raise ValueError("ArcanePref cannot assign one key chord more than once")

    def bindings_for(
        self,
        action: int | ArcaneClientAction,
    ) -> tuple[ArcaneHotkeyBinding, ...]:
        if isinstance(action, bool) or not isinstance(action, int):
            raise ValueError("action must be an integer action code")
        return tuple(item for item in self.bindings if item.action_code == int(action))

    def bindings_for_argument(self, argument: str) -> tuple[ArcaneHotkeyBinding, ...]:
        """Return bindings selected by the native action's string discriminator."""

        if not isinstance(argument, str) or not argument.strip():
            raise ValueError("argument must be a non-empty string")
        normalized = argument.casefold()
        return tuple(item for item in self.bindings if item.argument.casefold() == normalized)


def load_arcane_hotkeys(path: str | Path) -> ArcaneHotkeyTable:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ArcaneHotkeyLoadError(f"could not read ArcanePref hotkeys: {exc}") from exc
    return load_arcane_hotkeys_text(text)


def load_arcane_hotkeys_text(text: str) -> ArcaneHotkeyTable:
    if not isinstance(text, str):
        raise ArcaneHotkeyLoadError("ArcanePref content must be text")
    inside = False
    found = False
    bindings: list[ArcaneHotkeyBinding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped == "BEGINHOTKEYS":
            if inside or found:
                raise ArcaneHotkeyLoadError("ArcanePref must contain exactly one hotkey table")
            inside = True
            found = True
            continue
        if stripped == "ENDHOTKEYS":
            if not inside:
                raise ArcaneHotkeyLoadError(f"unexpected ENDHOTKEYS at line {line_number}")
            inside = False
            continue
        if not inside:
            continue
        match = _KEY_PATTERN.fullmatch(line)
        if match is None:
            raise ArcaneHotkeyLoadError(f"malformed hotkey record at line {line_number}")
        values = match.groupdict()
        bindings.append(
            ArcaneHotkeyBinding(
                key=values["key"],
                shift=values["shift"] == "TRUE",
                control=values["control"] == "TRUE",
                alt=values["alt"] == "TRUE",
                action_code=int(values["action"]),
                parameter_one=int(values["parameter_one"]),
                parameter_two=int(values["parameter_two"]),
                argument=values["argument"],
            )
        )
    if not found:
        raise ArcaneHotkeyLoadError("ArcanePref does not contain BEGINHOTKEYS")
    if inside:
        raise ArcaneHotkeyLoadError("ArcanePref hotkey table is not terminated")
    try:
        return ArcaneHotkeyTable(tuple(bindings))
    except ValueError as exc:
        raise ArcaneHotkeyLoadError(str(exc)) from exc


def _pyautogui_key(key: str) -> str:
    mapped = _PYAUTOGUI_KEYS.get(key)
    if mapped is not None:
        return mapped
    if len(key) == 1 or re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", key):
        return key.lower()
    keypad = re.fullmatch(r"Keypad ([0-9])", key)
    if keypad is not None:
        return keypad.group(1)
    raise ArcaneHotkeyLoadError(f"unsupported ArcanePref key name: {key}")
