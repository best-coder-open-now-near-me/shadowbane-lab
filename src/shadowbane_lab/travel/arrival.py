"""Observe stationary arrival independently of input dispatch/controller intent."""

import time
from dataclasses import dataclass
from math import hypot

from shadowbane_lab.client_observation import NativePlayerPositionObservation


@dataclass(frozen=True, slots=True)
class ArrivalResult:
    confirmed: bool
    position: NativePlayerPositionObservation | None
    reason: str | None


class ArrivalTracker:
    """Accept fresh observations from the owning loop, including coherent PvE frames."""

    def __init__(self, destination, started_at):
        self.destination = destination
        self.started_at = started_at
        self.anchor = None
        self.quiet_since = None

    def observe(self, position, now):
        if not isinstance(position, NativePlayerPositionObservation):
            return ArrivalResult(False, None, "arrival_position_unavailable")
        if now - self.started_at > 4.0:
            return ArrivalResult(False, position, "arrival_not_settled")
        if self.destination.distance_from(position) > self.destination.arrival_radius:
            self.anchor = None
            self.quiet_since = None
        elif (
            self.anchor is None
            or hypot(position.lt - self.anchor.lt, position.lg - self.anchor.lg) > 0.25
        ):
            self.anchor, self.quiet_since = position, now
        elif now - self.quiet_since >= 0.6 - 1e-9:
            return ArrivalResult(True, position, None)
        return None


def observe_arrival(
    position_reader,
    destination,
    *,
    stop_signal,
    observer=None,
    clock=time.monotonic,
    sleeper=time.sleep,
):
    """Require 600 ms within a 0.25-unit horizontal envelope and destination radius.

    Four seconds bounds settling; no input is issued. Altitude is excluded because
    animation changes measured height while the player is stationary. The observer
    receives every fresh sample, including continued motion after candidate arrival.
    """
    tracker = ArrivalTracker(destination, clock())
    last = None
    while True:
        if stop_signal.is_set():
            return ArrivalResult(False, last, "emergency_stop")
        try:
            position = position_reader.observe()
            if not isinstance(position, NativePlayerPositionObservation):
                raise ValueError("invalid native position")
            last = position
        except Exception as error:
            return ArrivalResult(False, last, f"arrival_observation_failure:{type(error).__name__}")
        if observer is not None:
            try:
                observer(last)
            except Exception:
                pass
        result = tracker.observe(last, clock())
        if result is not None:
            return result
        sleeper(0.2)
