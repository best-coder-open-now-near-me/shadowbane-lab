"""Versioned semantic controller bindings, shared with the owning native runtime."""

from dataclasses import dataclass
from enum import IntEnum


class ControllerAction(IntEnum):
    MOVEMENT = 1
    CAMERA = 2
    CANCEL_MOVEMENT = 3


class ControllerControl(IntEnum):
    LEFT_STICK = 1
    RIGHT_STICK = 2
    A = 3
    B = 4
    X = 5
    Y = 6
    DPAD_UP = 7
    DPAD_DOWN = 8
    DPAD_LEFT = 9
    DPAD_RIGHT = 10
    START = 11
    BACK = 12
    LEFT_THUMB = 13
    RIGHT_THUMB = 14
    LEFT_SHOULDER = 15
    RIGHT_SHOULDER = 16
    LEFT_TRIGGER = 17
    RIGHT_TRIGGER = 18


@dataclass(frozen=True, slots=True)
class ControllerBinding:
    action: ControllerAction
    control: ControllerControl
    modifiers: int = 0

    def encode(self) -> int:
        action, control = ControllerAction(self.action), ControllerControl(self.control)
        if type(self.modifiers) is not int or not 0 <= self.modifiers <= 3:
            raise ValueError("unsupported shoulder combination")
        if (control in (ControllerControl.LEFT_STICK, ControllerControl.RIGHT_STICK)) != (
            action in (ControllerAction.MOVEMENT, ControllerAction.CAMERA)
        ):
            raise ValueError("vector actions require a stick; cancel requires a button or trigger")
        return int(action) | (int(control) << 6) | (self.modifiers << 11)

    @classmethod
    def decode(cls, value: int) -> "ControllerBinding":
        if type(value) is not int or value < 0 or value & ~0x1FFF:
            raise ValueError("unknown binding bits")
        result = cls(
            ControllerAction(value & 63), ControllerControl((value >> 6) & 31), (value >> 11) & 3
        )
        result.encode()
        return result


DEFAULT_CONTROLLER_BINDINGS = (
    ControllerBinding(ControllerAction.MOVEMENT, ControllerControl.LEFT_STICK),
    ControllerBinding(ControllerAction.CAMERA, ControllerControl.RIGHT_STICK),
    ControllerBinding(ControllerAction.CANCEL_MOVEMENT, ControllerControl.B),
)
CONTROLLER_BINDING_CAPACITY = 24


def encode_profile(bindings: tuple[ControllerBinding, ...]) -> tuple[int, ...]:
    if not isinstance(bindings, tuple) or len(bindings) > CONTROLLER_BINDING_CAPACITY:
        raise ValueError("controller profile supports up to 24 bindings")
    encoded = tuple(binding.encode() for binding in bindings)
    pairs = {(binding.control, binding.modifiers) for binding in bindings}
    if len(pairs) != len(bindings):
        raise ValueError("one action per physical control and shoulder combination")
    modifiers = 0
    for binding in bindings:
        modifiers |= binding.modifiers
    if any(
        (binding.control == ControllerControl.LEFT_SHOULDER and modifiers & 1)
        or (binding.control == ControllerControl.RIGHT_SHOULDER and modifiers & 2)
        for binding in bindings
    ):
        raise ValueError("a shoulder modifier cannot also trigger an action")
    for mode in range(4):
        actions = []
        for control in (ControllerControl.LEFT_STICK, ControllerControl.RIGHT_STICK):
            selected = next(
                (b for b in bindings if b.control == control and b.modifiers == mode), None
            )
            if selected is None:
                selected = next(
                    (b for b in bindings if b.control == control and b.modifiers == 0), None
                )
            if selected is not None:
                actions.append(selected.action)
        if len(set(actions)) != len(actions):
            raise ValueError("two sticks cannot drive the same action in one shoulder mode")
    return (1, len(bindings), *encoded, *([0] * (CONTROLLER_BINDING_CAPACITY - len(bindings))))


def decode_profile(values: tuple[int, ...]) -> tuple[ControllerBinding, ...]:
    if len(values) != 26 or values[0] != 1 or not 0 <= values[1] <= CONTROLLER_BINDING_CAPACITY:
        raise ValueError("unsupported controller profile format")
    count = values[1]
    if any(values[2 + count :]):
        raise ValueError("noncanonical unused binding entries")
    result = tuple(ControllerBinding.decode(value) for value in values[2 : 2 + count])
    encode_profile(result)
    return result
