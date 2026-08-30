"""Native-verified action contract for one world-map destination click."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Protocol, runtime_checkable
from uuid import uuid4

from shadowbane_lab.client_extension import (
    EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION,
    ExtensionEventChannelSnapshot,
    ExtensionPointerButton,
)
from shadowbane_lab.client_input import (
    AbsolutePoint,
    ClickCommand,
    ForegroundWindowGuard,
    InputExecutionResult,
    InputPlan,
    MouseButton,
)
from shadowbane_lab.client_observation import NativeWorldMapObservation

from .model import (
    ClientActionCheckpoint,
    ClientActionEffectObservation,
    ClientActionSpec,
    ClientActionVerification,
)

WORLD_MAP_DESTINATION_CLICK_ACTION_KEY = "client.world_map.destination_click"


class WorldMapDestinationClickError(RuntimeError):
    """Raised when a destination click crosses or violates an action boundary."""


@runtime_checkable
class WorldMapObservationSource(Protocol):
    @property
    def process_id(self) -> int: ...

    def observe(self) -> NativeWorldMapObservation: ...


@runtime_checkable
class ExtensionEventSnapshotSource(Protocol):
    @property
    def process_id(self) -> int: ...

    @property
    def process_creation_filetime_utc(self) -> int: ...

    def snapshot(self) -> ExtensionEventChannelSnapshot: ...


@runtime_checkable
class InputPlanExecutor(Protocol):
    def execute(self, plan: InputPlan) -> InputExecutionResult: ...


@dataclass(frozen=True, slots=True)
class _PreparedWorldMapClick:
    process_id: int
    process_creation_filetime_utc: int
    window_handle: int
    screen_point: AbsolutePoint
    client_x: int
    client_y: int
    normalized_x: float
    normalized_y: float
    expected_lt: float
    expected_lg: float
    world_map_snapshot_token: str
    baseline_write_sequence: int
    baseline_dropped_event_count: int


class WorldMapDestinationClickAction:
    """Dispatch one guarded right click and require one exact extension event."""

    def __init__(
        self,
        *,
        window_guard: ForegroundWindowGuard,
        world_map: WorldMapObservationSource,
        events: ExtensionEventSnapshotSource,
        executor: InputPlanExecutor,
        map_x_fraction: float,
        map_y_fraction: float,
        action_id: str | None = None,
        timeout_ms: int = 2_000,
        poll_interval_ms: int = 25,
        world_coordinate_tolerance: float = 0.25,
    ) -> None:
        if not isinstance(window_guard, ForegroundWindowGuard):
            raise ValueError("window_guard must be ForegroundWindowGuard")
        if not isinstance(world_map, WorldMapObservationSource):
            raise ValueError("world_map must implement WorldMapObservationSource")
        if not isinstance(events, ExtensionEventSnapshotSource):
            raise ValueError("events must implement ExtensionEventSnapshotSource")
        if not isinstance(executor, InputPlanExecutor):
            raise ValueError("executor must implement InputPlanExecutor")
        for value, field_name in (
            (map_x_fraction, "map_x_fraction"),
            (map_y_fraction, "map_y_fraction"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field_name} must be numeric")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be in [0, 1]")
        if (
            isinstance(world_coordinate_tolerance, bool)
            or not isinstance(world_coordinate_tolerance, (int, float))
            or world_coordinate_tolerance < 0
        ):
            raise ValueError("world_coordinate_tolerance must be non-negative")
        resolved_action_id = action_id or f"world-map-click:{uuid4().hex}"
        if not isinstance(resolved_action_id, str) or not resolved_action_id.strip():
            raise ValueError("action_id must be a non-empty string")
        self._action_id = resolved_action_id
        self._spec = ClientActionSpec(
            key=WORLD_MAP_DESTINATION_CLICK_ACTION_KEY,
            verification=ClientActionVerification.NATIVE_VERIFIED,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
        )
        self._window_guard = window_guard
        self._world_map = world_map
        self._events = events
        self._executor = executor
        self._map_x_fraction = float(map_x_fraction)
        self._map_y_fraction = float(map_y_fraction)
        self._world_coordinate_tolerance = float(world_coordinate_tolerance)
        self._prepared: _PreparedWorldMapClick | None = None

    @property
    def action_id(self) -> str:
        return self._action_id

    @property
    def spec(self) -> ClientActionSpec:
        return self._spec

    def prepare(self) -> ClientActionCheckpoint:
        if self._prepared is not None:
            raise WorldMapDestinationClickError("action was already prepared")
        window = self._window_guard.require_target()
        if (
            window.process_id is None
            or window.process_started_at_100ns is None
            or window.window_handle is None
        ):
            raise WorldMapDestinationClickError(
                "foreground client lacks an exact process/window lifetime"
            )
        process_identity = window.process_id, window.process_started_at_100ns
        if self._world_map.process_id != window.process_id:
            raise WorldMapDestinationClickError(
                "world-map observer belongs to another process"
            )
        if (
            self._events.process_id,
            self._events.process_creation_filetime_utc,
        ) != process_identity:
            raise WorldMapDestinationClickError(
                "extension event channel belongs to another process lifetime"
            )

        channel = self._events.snapshot()
        self._require_healthy_channel(channel)
        observation = self._world_map.observe()
        if not observation.is_open:
            raise WorldMapDestinationClickError("world map is not open")
        width = observation.right - observation.left
        height = observation.bottom - observation.top
        screen_point = AbsolutePoint(
            observation.left + round(self._map_x_fraction * (width - 1)),
            observation.top + round(self._map_y_fraction * (height - 1)),
        )
        destination = observation.resolve_screen_point(screen_point.x, screen_point.y)
        try:
            normalized = window.client_bounds.normalize(screen_point)
        except ValueError as exc:
            raise WorldMapDestinationClickError(
                "world-map click point lies outside the guarded client"
            ) from exc
        self._prepared = _PreparedWorldMapClick(
            process_id=window.process_id,
            process_creation_filetime_utc=window.process_started_at_100ns,
            window_handle=window.window_handle,
            screen_point=screen_point,
            client_x=screen_point.x - window.client_bounds.left,
            client_y=screen_point.y - window.client_bounds.top,
            normalized_x=normalized.x,
            normalized_y=normalized.y,
            expected_lt=destination.lt,
            expected_lg=destination.lg,
            world_map_snapshot_token=observation.snapshot_token,
            baseline_write_sequence=channel.header.write_sequence,
            baseline_dropped_event_count=channel.header.dropped_event_count,
        )
        return ClientActionCheckpoint(
            "exact foreground map and extension channel are ready",
            {
                "process_id": window.process_id,
                "window_handle": window.window_handle,
                "screen_x": screen_point.x,
                "screen_y": screen_point.y,
                "expected_lt": destination.lt,
                "expected_lg": destination.lg,
                "baseline_sequence": channel.header.write_sequence,
            },
        )

    def dispatch(self) -> ClientActionCheckpoint:
        prepared = self._require_prepared()
        window = self._window_guard.require_target()
        if (
            window.process_id,
            window.process_started_at_100ns,
            window.window_handle,
        ) != (
            prepared.process_id,
            prepared.process_creation_filetime_utc,
            prepared.window_handle,
        ):
            raise WorldMapDestinationClickError(
                "foreground client identity changed after precondition"
            )
        observation = self._world_map.observe()
        if observation.snapshot_token != prepared.world_map_snapshot_token:
            raise WorldMapDestinationClickError(
                "world-map projection changed after precondition"
            )
        channel = self._events.snapshot()
        self._require_healthy_channel(channel)
        if channel.header.write_sequence != prepared.baseline_write_sequence:
            raise WorldMapDestinationClickError(
                "extension channel changed before action dispatch"
            )
        result = self._executor.execute(
            InputPlan(
                correlation_id=self._action_id,
                action_key=self._spec.key,
                commands=(
                    ClickCommand(
                        point=window.client_bounds.normalize(prepared.screen_point),
                        button=MouseButton.RIGHT,
                    ),
                ),
            )
        )
        return ClientActionCheckpoint(
            "one guarded right click was dispatched",
            {
                "commands_completed": result.commands_completed,
                "screen_x": prepared.screen_point.x,
                "screen_y": prepared.screen_point.y,
            },
        )

    def observe_effect(self) -> ClientActionEffectObservation:
        prepared = self._require_prepared()
        channel = self._events.snapshot()
        self._require_healthy_channel(channel)
        if channel.header.dropped_event_count != prepared.baseline_dropped_event_count:
            raise WorldMapDestinationClickError(
                "extension event loss changed during the action"
            )
        if channel.header.write_sequence <= prepared.baseline_write_sequence:
            return ClientActionEffectObservation(
                False,
                ClientActionCheckpoint(
                    "waiting for the extension destination event",
                    {"last_sequence": channel.header.write_sequence},
                ),
            )
        expected_sequence = prepared.baseline_write_sequence + 1
        if channel.header.write_sequence != expected_sequence:
            raise WorldMapDestinationClickError(
                "more than one extension event followed a single action input"
            )
        matches = tuple(event for event in channel.events if event.sequence == expected_sequence)
        if len(matches) != 1:
            raise WorldMapDestinationClickError(
                "the expected extension event was consumed or unavailable"
            )
        event = matches[0]
        mismatches: list[str] = []
        if event.process_identity != (
            prepared.process_id,
            prepared.process_creation_filetime_utc,
        ):
            mismatches.append("process lifetime")
        if event.window_handle != prepared.window_handle:
            mismatches.append("window handle")
        if event.button is not ExtensionPointerButton.RIGHT:
            mismatches.append("pointer button")
        if (event.desktop_screen_x, event.desktop_screen_y) != (
            prepared.screen_point.x,
            prepared.screen_point.y,
        ):
            mismatches.append("desktop pixel")
        if (event.client_x, event.client_y) != (prepared.client_x, prepared.client_y):
            mismatches.append("client pixel")
        if not isclose(
            event.lt,
            prepared.expected_lt,
            rel_tol=0.0,
            abs_tol=self._world_coordinate_tolerance,
        ):
            mismatches.append("LT projection")
        if not isclose(
            event.lg,
            prepared.expected_lg,
            rel_tol=0.0,
            abs_tol=self._world_coordinate_tolerance,
        ):
            mismatches.append("LG projection")
        if mismatches:
            raise WorldMapDestinationClickError(
                "extension destination event mismatched: " + ", ".join(mismatches)
            )
        return ClientActionEffectObservation(
            True,
            ClientActionCheckpoint(
                "extension emitted the exact world-map destination",
                {
                    "event_sequence": event.sequence,
                    "screen_x": event.desktop_screen_x,
                    "screen_y": event.desktop_screen_y,
                    "lt": event.lt,
                    "lg": event.lg,
                    "snapshot_token": event.snapshot_token,
                },
            ),
        )

    def cleanup(self) -> ClientActionCheckpoint:
        return ClientActionCheckpoint(
            "destination-capture action owns no downstream movement",
            {"cleanup_input_dispatched": False},
        )

    def _require_prepared(self) -> _PreparedWorldMapClick:
        if self._prepared is None:
            raise WorldMapDestinationClickError("action has not passed preconditions")
        return self._prepared

    @staticmethod
    def _require_healthy_channel(channel: ExtensionEventChannelSnapshot) -> None:
        if not (
            channel.header.capability_flags
            & EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION
        ):
            raise WorldMapDestinationClickError(
                "extension does not expose world-map destinations"
            )
        if channel.header.producer_error != 0:
            raise WorldMapDestinationClickError(
                f"extension event producer error {channel.header.producer_error}"
            )


__all__ = [
    "WORLD_MAP_DESTINATION_CLICK_ACTION_KEY",
    "ExtensionEventSnapshotSource",
    "InputPlanExecutor",
    "WorldMapDestinationClickAction",
    "WorldMapDestinationClickError",
    "WorldMapObservationSource",
]
