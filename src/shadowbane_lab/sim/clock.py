"""Virtual simulation clock that never consults wall time."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClockSnapshot:
    tick_duration_ms: int
    tick: int
    now_ms: int

    def __post_init__(self) -> None:
        if self.tick_duration_ms <= 0:
            raise ValueError("tick_duration_ms must be positive")
        if self.tick < 0:
            raise ValueError("tick must not be negative")
        if self.now_ms < 0:
            raise ValueError("now_ms must not be negative")


class SimulationClock:
    """A manually advanced clock suitable for repeatable, faster-than-real-time worlds."""

    def __init__(self, tick_duration_ms: int = 200) -> None:
        if isinstance(tick_duration_ms, bool) or not isinstance(tick_duration_ms, int):
            raise ValueError("tick_duration_ms must be an integer")
        if tick_duration_ms <= 0:
            raise ValueError("tick_duration_ms must be positive")
        self._tick_duration_ms = tick_duration_ms
        self._tick = 0
        self._now_ms = 0

    @property
    def tick_duration_ms(self) -> int:
        return self._tick_duration_ms

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def now_ms(self) -> int:
        return self._now_ms

    def advance(self, ticks: int = 1) -> int:
        if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks <= 0:
            raise ValueError("ticks must be a positive integer")
        self._tick += ticks
        self._now_ms += ticks * self._tick_duration_ms
        return self._now_ms

    def snapshot(self) -> ClockSnapshot:
        return ClockSnapshot(
            tick_duration_ms=self._tick_duration_ms,
            tick=self._tick,
            now_ms=self._now_ms,
        )

    def restore(self, snapshot: ClockSnapshot) -> None:
        if snapshot.tick_duration_ms != self._tick_duration_ms:
            raise ValueError("snapshot tick duration does not match the clock")
        self._tick = snapshot.tick
        self._now_ms = snapshot.now_ms
