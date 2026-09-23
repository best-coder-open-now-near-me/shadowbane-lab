"""Read-only snapshots from one exact client performance mapping."""

from __future__ import annotations

from .event_reader import SharedMemorySnapshotReader, WindowsSharedMemorySnapshotReader
from .performance import (
    PERFORMANCE_TELEMETRY_SIZE,
    PerformanceTelemetryError,
    PerformanceTelemetrySnapshot,
    parse_performance_telemetry,
    performance_telemetry_mapping_name,
)


class PerformanceTelemetryReadError(RuntimeError):
    """Raised when a stable snapshot cannot be read from the exact mapping."""


class PerformanceTelemetryReader:
    def __init__(
        self,
        process_id: int,
        process_creation_filetime_utc: int,
        memory: SharedMemorySnapshotReader,
        *,
        maximum_attempts: int = 5,
    ) -> None:
        self._mapping_name = performance_telemetry_mapping_name(
            process_id,
            process_creation_filetime_utc,
        )
        if not isinstance(memory, SharedMemorySnapshotReader):
            raise ValueError("memory must implement SharedMemorySnapshotReader")
        if (
            isinstance(maximum_attempts, bool)
            or not isinstance(maximum_attempts, int)
            or not 1 <= maximum_attempts <= 20
        ):
            raise ValueError("maximum_attempts must be in [1, 20]")
        self._process_id = process_id
        self._creation = process_creation_filetime_utc
        self._memory = memory
        self._maximum_attempts = maximum_attempts

    @property
    def mapping_name(self) -> str:
        return self._mapping_name

    def snapshot(self) -> PerformanceTelemetrySnapshot:
        last_error: Exception | None = None
        for _ in range(self._maximum_attempts):
            try:
                payload = self._memory.read(self._mapping_name, PERFORMANCE_TELEMETRY_SIZE)
            except Exception as exc:
                raise PerformanceTelemetryReadError(
                    f"could not read the exact performance mapping: {type(exc).__name__}"
                ) from exc
            try:
                return parse_performance_telemetry(
                    payload,
                    expected_process_id=self._process_id,
                    expected_process_creation_filetime_utc=self._creation,
                )
            except PerformanceTelemetryError as exc:
                last_error = exc
        raise PerformanceTelemetryReadError(
            f"could not obtain a coherent performance snapshot: {last_error}"
        ) from last_error


def open_windows_performance_telemetry_reader(
    process_id: int,
    process_creation_filetime_utc: int,
) -> PerformanceTelemetryReader:
    return PerformanceTelemetryReader(
        process_id,
        process_creation_filetime_utc,
        WindowsSharedMemorySnapshotReader(),
    )


__all__ = [
    "PerformanceTelemetryReadError",
    "PerformanceTelemetryReader",
    "open_windows_performance_telemetry_reader",
]
