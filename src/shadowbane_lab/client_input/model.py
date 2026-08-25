"""Typed client-input plans and versioned calibration records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

CLIENT_PROFILE_SCHEMA_VERSION = 1


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} must be finite")


class MouseButton(StrEnum):
    LEFT = "left"
    MIDDLE = "middle"
    RIGHT = "right"


class TargetOrder(StrEnum):
    NONE = "none"
    BEFORE_ACTIVATION = "before_activation"
    AFTER_ACTIVATION = "after_activation"


@dataclass(frozen=True, slots=True)
class NormalizedPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        _finite(self.x, "x")
        _finite(self.y, "y")
        if not 0.0 <= self.x <= 1.0 or not 0.0 <= self.y <= 1.0:
            raise ValueError("normalized coordinates must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class WindowBounds:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if isinstance(self.left, bool) or not isinstance(self.left, int):
            raise ValueError("left must be an integer")
        if isinstance(self.top, bool) or not isinstance(self.top, int):
            raise ValueError("top must be an integer")
        _positive_integer(self.width, "width")
        _positive_integer(self.height, "height")

    def resolve(self, point: NormalizedPoint) -> AbsolutePoint:
        if not isinstance(point, NormalizedPoint):
            raise ValueError("point must be a NormalizedPoint")
        x = self.left + round(point.x * (self.width - 1))
        y = self.top + round(point.y * (self.height - 1))
        return AbsolutePoint(x=x, y=y)

    def contains(self, point: AbsolutePoint) -> bool:
        return (
            self.left <= point.x < self.left + self.width
            and self.top <= point.y < self.top + self.height
        )


@dataclass(frozen=True, slots=True)
class AbsolutePoint:
    x: int
    y: int

    def __post_init__(self) -> None:
        if isinstance(self.x, bool) or not isinstance(self.x, int):
            raise ValueError("x must be an integer")
        if isinstance(self.y, bool) or not isinstance(self.y, int):
            raise ValueError("y must be an integer")


@dataclass(frozen=True, slots=True)
class ClickCommand:
    point: NormalizedPoint
    button: MouseButton = MouseButton.LEFT
    clicks: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.point, NormalizedPoint):
            raise ValueError("point must be a NormalizedPoint")
        if not isinstance(self.button, MouseButton):
            raise ValueError("button must be a MouseButton")
        _positive_integer(self.clicks, "clicks")


@dataclass(frozen=True, slots=True)
class DragCommand:
    start: NormalizedPoint
    end: NormalizedPoint
    duration_ms: int
    button: MouseButton = MouseButton.LEFT

    def __post_init__(self) -> None:
        if not isinstance(self.start, NormalizedPoint) or not isinstance(self.end, NormalizedPoint):
            raise ValueError("drag points must be NormalizedPoint values")
        _non_negative_integer(self.duration_ms, "duration_ms")
        if not isinstance(self.button, MouseButton):
            raise ValueError("button must be a MouseButton")


@dataclass(frozen=True, slots=True)
class KeyPressCommand:
    key: str

    def __post_init__(self) -> None:
        _identifier(self.key, "key")


@dataclass(frozen=True, slots=True)
class HotkeyCommand:
    keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.keys:
            raise ValueError("hotkey requires at least one key")
        if len(self.keys) != len(set(self.keys)):
            raise ValueError("hotkey keys must be unique")
        for key in self.keys:
            _identifier(key, "hotkey key")


@dataclass(frozen=True, slots=True)
class WaitCommand:
    duration_ms: int

    def __post_init__(self) -> None:
        _non_negative_integer(self.duration_ms, "duration_ms")
        if self.duration_ms == 0:
            raise ValueError("wait duration must be positive")


InputCommand = ClickCommand | DragCommand | KeyPressCommand | HotkeyCommand | WaitCommand

_INPUT_COMMAND_TYPES = (
    ClickCommand,
    DragCommand,
    KeyPressCommand,
    HotkeyCommand,
    WaitCommand,
)


@dataclass(frozen=True, slots=True)
class InputPlan:
    correlation_id: str
    action_key: str
    commands: tuple[InputCommand, ...]

    def __post_init__(self) -> None:
        _identifier(self.correlation_id, "correlation_id")
        _identifier(self.action_key, "action_key")
        if not self.commands:
            raise ValueError("an input plan requires at least one command")
        if any(not isinstance(command, _INPUT_COMMAND_TYPES) for command in self.commands):
            raise ValueError("commands must contain typed input commands")


@dataclass(frozen=True, slots=True)
class ClickActivation:
    point: NormalizedPoint
    button: MouseButton = MouseButton.LEFT

    def __post_init__(self) -> None:
        if not isinstance(self.point, NormalizedPoint):
            raise ValueError("point must be a NormalizedPoint")
        if not isinstance(self.button, MouseButton):
            raise ValueError("button must be a MouseButton")


@dataclass(frozen=True, slots=True)
class KeyActivation:
    key: str

    def __post_init__(self) -> None:
        _identifier(self.key, "key")


@dataclass(frozen=True, slots=True)
class HotkeyActivation:
    keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.keys:
            raise ValueError("hotkey activation requires at least one key")
        if len(self.keys) != len(set(self.keys)):
            raise ValueError("hotkey activation keys must be unique")
        for key in self.keys:
            _identifier(key, "hotkey activation key")


Activation = ClickActivation | KeyActivation | HotkeyActivation


@dataclass(frozen=True, slots=True)
class ActionInputMapping:
    action_key: str
    activation: Activation
    target_order: TargetOrder = TargetOrder.NONE
    post_activation_delay_ms: int = 0

    def __post_init__(self) -> None:
        _identifier(self.action_key, "action_key")
        if not isinstance(self.activation, (ClickActivation, KeyActivation, HotkeyActivation)):
            raise ValueError("activation must be a typed activation")
        if not isinstance(self.target_order, TargetOrder):
            raise ValueError("target_order must be a TargetOrder")
        _non_negative_integer(self.post_activation_delay_ms, "post_activation_delay_ms")


@dataclass(frozen=True, slots=True)
class DirectionalClickMapping:
    action_key: str
    center: NormalizedPoint
    horizontal_radius: float
    vertical_radius: float
    button: MouseButton = MouseButton.LEFT

    def __post_init__(self) -> None:
        _identifier(self.action_key, "action_key")
        if not isinstance(self.center, NormalizedPoint):
            raise ValueError("center must be a NormalizedPoint")
        for value, field_name in (
            (self.horizontal_radius, "horizontal_radius"),
            (self.vertical_radius, "vertical_radius"),
        ):
            _finite(value, field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if not (
            0.0 <= self.center.x - self.horizontal_radius
            and self.center.x + self.horizontal_radius <= 1.0
            and 0.0 <= self.center.y - self.vertical_radius
            and self.center.y + self.vertical_radius <= 1.0
        ):
            raise ValueError("movement radius must remain inside normalized client bounds")
        if not isinstance(self.button, MouseButton):
            raise ValueError("button must be a MouseButton")


@dataclass(frozen=True, slots=True)
class CameraDragMapping:
    anchor: NormalizedPoint
    maximum_horizontal_delta: float
    maximum_vertical_delta: float
    duration_ms: int
    button: MouseButton = MouseButton.LEFT

    def __post_init__(self) -> None:
        if not isinstance(self.anchor, NormalizedPoint):
            raise ValueError("anchor must be a NormalizedPoint")
        for value, field_name in (
            (self.maximum_horizontal_delta, "maximum_horizontal_delta"),
            (self.maximum_vertical_delta, "maximum_vertical_delta"),
        ):
            _finite(value, field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
        if not (
            0.0 <= self.anchor.x - self.maximum_horizontal_delta
            and self.anchor.x + self.maximum_horizontal_delta <= 1.0
            and 0.0 <= self.anchor.y - self.maximum_vertical_delta
            and self.anchor.y + self.maximum_vertical_delta <= 1.0
        ):
            raise ValueError("camera drag range must remain inside normalized client bounds")
        _positive_integer(self.duration_ms, "duration_ms")
        if not isinstance(self.button, MouseButton):
            raise ValueError("button must be a MouseButton")


@dataclass(frozen=True, slots=True)
class ClientTarget:
    executable_names: tuple[str, ...]
    title_pattern: str
    reference_width: int
    reference_height: int
    dpi_scale: float
    size_tolerance_px: int = 0
    dpi_tolerance: float = 0.01

    def __post_init__(self) -> None:
        if not self.executable_names:
            raise ValueError("at least one executable name is required")
        lowered = tuple(name.lower() for name in self.executable_names)
        if len(lowered) != len(set(lowered)):
            raise ValueError("executable names must be unique ignoring case")
        for name in self.executable_names:
            _identifier(name, "executable name")
        _identifier(self.title_pattern, "title_pattern")
        _positive_integer(self.reference_width, "reference_width")
        _positive_integer(self.reference_height, "reference_height")
        _finite(self.dpi_scale, "dpi_scale")
        if self.dpi_scale <= 0:
            raise ValueError("dpi_scale must be positive")
        _non_negative_integer(self.size_tolerance_px, "size_tolerance_px")
        _finite(self.dpi_tolerance, "dpi_tolerance")
        if self.dpi_tolerance < 0:
            raise ValueError("dpi_tolerance must not be negative")


@dataclass(frozen=True, slots=True)
class CalibrationProfile:
    profile_id: str
    target: ClientTarget
    actions: tuple[ActionInputMapping, ...]
    movement: DirectionalClickMapping
    camera: CameraDragMapping
    schema_version: int = CLIENT_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.profile_id, "profile_id")
        if self.schema_version != CLIENT_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported calibration profile version")
        if not isinstance(self.target, ClientTarget):
            raise ValueError("target must be a ClientTarget")
        if any(not isinstance(action, ActionInputMapping) for action in self.actions):
            raise ValueError("actions must contain ActionInputMapping values")
        action_keys = tuple(action.action_key for action in self.actions)
        if len(action_keys) != len(set(action_keys)):
            raise ValueError("action input mappings must have unique keys")
        if not isinstance(self.movement, DirectionalClickMapping):
            raise ValueError("movement must be a DirectionalClickMapping")
        if self.movement.action_key in set(action_keys):
            raise ValueError("movement action must not also have an activation mapping")
        if not isinstance(self.camera, CameraDragMapping):
            raise ValueError("camera must be a CameraDragMapping")
