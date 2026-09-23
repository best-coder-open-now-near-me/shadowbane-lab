"""Compile semantic decisions into side-effect-free client input plans."""

from __future__ import annotations

from math import hypot
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_input.model import (
    ActionInputMapping,
    CalibrationProfile,
    ClickActivation,
    ClickCommand,
    DragCommand,
    HotkeyActivation,
    HotkeyCommand,
    InputCommand,
    InputPlan,
    KeyActivation,
    KeyPressCommand,
    NormalizedPoint,
    TargetOrder,
    WaitCommand,
)
from shadowbane_lab.protocol import DecisionMessage, TargetKind


class InputCompilationError(ValueError):
    """Raised when a semantic decision cannot be safely mapped to input."""


@runtime_checkable
class BindingPointResolver(Protocol):
    def resolve(self, decision: DecisionMessage) -> NormalizedPoint | None: ...


class StaticBindingPointResolver:
    """Read-only resolver useful for calibrated observations and tests."""

    def __init__(self, entity_points: dict[str, NormalizedPoint] | None = None) -> None:
        self._entity_points = dict(entity_points or {})
        if any(not isinstance(point, NormalizedPoint) for point in self._entity_points.values()):
            raise ValueError("entity points must be NormalizedPoint values")

    def resolve(self, decision: DecisionMessage) -> NormalizedPoint | None:
        target_id = decision.binding.target_entity_id
        return None if target_id is None else self._entity_points.get(target_id)


class DecisionInputCompiler:
    def __init__(
        self,
        profile: CalibrationProfile,
        binding_resolver: BindingPointResolver,
        *,
        movement_resolver: BindingPointResolver | None = None,
    ) -> None:
        if not isinstance(profile, CalibrationProfile):
            raise ValueError("profile must be a CalibrationProfile")
        if not isinstance(binding_resolver, BindingPointResolver):
            raise ValueError("binding_resolver must implement BindingPointResolver")
        self._profile = profile
        if movement_resolver is not None and not isinstance(
            movement_resolver, BindingPointResolver
        ):
            raise ValueError("movement_resolver must implement BindingPointResolver")
        self._movement_resolver = movement_resolver
        self._resolver = binding_resolver
        self._actions = {mapping.action_key: mapping for mapping in profile.actions}

    @property
    def profile(self) -> CalibrationProfile:
        return self._profile

    def compile(self, decision: DecisionMessage) -> InputPlan:
        if not isinstance(decision, DecisionMessage):
            raise InputCompilationError("decision must be a DecisionMessage")
        if decision.action_key == self._profile.movement.action_key:
            return self._compile_movement(decision)
        try:
            mapping = self._actions[decision.action_key]
        except KeyError as exc:
            raise InputCompilationError(
                f"profile has no mapping for {decision.action_key}"
            ) from exc
        return self._compile_action(decision, mapping)

    def compile_camera_drag(
        self,
        *,
        correlation_id: str,
        horizontal: float,
        vertical: float,
    ) -> InputPlan:
        for value, name in ((horizontal, "horizontal"), (vertical, "vertical")):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise InputCompilationError(f"{name} must be numeric")
            if not -1.0 <= value <= 1.0:
                raise InputCompilationError(f"{name} must be in [-1, 1]")
        camera = self._profile.camera
        end = _offset_point(
            camera.anchor,
            float(horizontal) * camera.maximum_horizontal_delta,
            float(vertical) * camera.maximum_vertical_delta,
        )
        return InputPlan(
            correlation_id=correlation_id,
            action_key="client.camera.rotate",
            commands=(
                DragCommand(
                    start=camera.anchor,
                    end=end,
                    duration_ms=camera.duration_ms,
                    button=camera.button,
                ),
            ),
        )

    def compile_movement_stop(self, *, correlation_id: str) -> InputPlan:
        """Click-to-move has no verified immediate-stop input."""
        raise InputCompilationError(
            "instant movement stop is unavailable; "
            "the client may finish its last clicked destination"
        )

    def _compile_movement(self, decision: DecisionMessage) -> InputPlan:
        if decision.binding.target_kind is TargetKind.POSITION:
            if self._movement_resolver is None:
                raise InputCompilationError("movement destination needs a verified live projection")
            point = self._movement_resolver.resolve(decision)
            if not isinstance(point, NormalizedPoint):
                raise InputCompilationError("movement destination could not be projected")
            return InputPlan(
                correlation_id=decision.correlation_id,
                action_key=decision.action_key,
                commands=(ClickCommand(point=point, button=self._profile.movement.button),),
            )
        if decision.binding.target_kind is not TargetKind.DIRECTION:
            raise InputCompilationError("movement requires a direction binding")
        direction = decision.binding.direction
        if direction is None:
            raise InputCompilationError("movement direction is missing")
        length = hypot(direction.x, direction.y)
        if length == 0:
            raise InputCompilationError("movement direction must not be zero")
        movement = self._profile.movement
        point = _offset_point(
            movement.center,
            direction.x / length * movement.horizontal_radius,
            direction.y / length * movement.vertical_radius,
        )
        return InputPlan(
            correlation_id=decision.correlation_id,
            action_key=decision.action_key,
            commands=(ClickCommand(point=point, button=movement.button),),
        )

    def _compile_action(
        self,
        decision: DecisionMessage,
        mapping: ActionInputMapping,
    ) -> InputPlan:
        target_command = self._target_command(decision, mapping.target_order)
        activation = _activation_command(mapping)
        commands: list[InputCommand] = []
        if mapping.target_order is TargetOrder.BEFORE_ACTIVATION:
            if target_command is None:
                raise InputCompilationError("target-before mapping requires a resolved target")
            commands.append(target_command)
        commands.append(activation)
        if mapping.target_order is TargetOrder.AFTER_ACTIVATION:
            if target_command is None:
                raise InputCompilationError("target-after mapping requires a resolved target")
            commands.append(target_command)
        if mapping.post_activation_delay_ms:
            commands.append(WaitCommand(mapping.post_activation_delay_ms))
        return InputPlan(
            correlation_id=decision.correlation_id,
            action_key=decision.action_key,
            commands=tuple(commands),
        )

    def _target_command(
        self,
        decision: DecisionMessage,
        order: TargetOrder,
    ) -> ClickCommand | None:
        if order is TargetOrder.NONE:
            return None
        if decision.binding.target_kind is not TargetKind.ENTITY:
            raise InputCompilationError("targeted input mapping requires an entity binding")
        point = self._resolver.resolve(decision)
        if point is None:
            raise InputCompilationError(
                f"no calibrated client point for {decision.binding.target_entity_id}"
            )
        return ClickCommand(point)


def _activation_command(
    mapping: ActionInputMapping,
) -> ClickCommand | KeyPressCommand | HotkeyCommand:
    activation = mapping.activation
    if isinstance(activation, ClickActivation):
        return ClickCommand(activation.point, activation.button)
    if isinstance(activation, KeyActivation):
        return KeyPressCommand(activation.key)
    if isinstance(activation, HotkeyActivation):
        return HotkeyCommand(activation.keys)
    raise InputCompilationError("unsupported activation type")


def _offset_point(point: NormalizedPoint, delta_x: float, delta_y: float) -> NormalizedPoint:
    x = point.x + delta_x
    y = point.y + delta_y
    if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
        raise InputCompilationError("calibrated input would leave the client bounds")
    return NormalizedPoint(x, y)
