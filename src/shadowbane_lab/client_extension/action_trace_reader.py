"""Read coherent snapshots from one exact native action-trace mapping."""

from __future__ import annotations

import time
from collections.abc import Callable

from .action_trace import (
    CLIENT_ACTION_TRACE_SIZE,
    ClientActionTraceError,
    ClientActionTraceSnapshot,
    client_action_trace_mapping_name,
    parse_client_action_trace,
)
from .event_reader import SharedMemorySnapshotReader, WindowsSharedMemorySnapshotReader


class ClientActionTraceReadError(RuntimeError):
    """Raised when an exact action-trace mapping cannot provide a coherent snapshot."""


class ClientActionTraceNotArmed(ClientActionTraceReadError):
    """Raised when capture is requested before a reviewed native probe is armed."""


class ClientActionTraceReader:
    def __init__(
        self,
        process_id: int,
        process_creation_filetime_utc: int,
        memory: SharedMemorySnapshotReader,
        *,
        maximum_attempts: int = 5,
    ) -> None:
        self._mapping_name = client_action_trace_mapping_name(
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

    def snapshot(self) -> ClientActionTraceSnapshot:
        last_error: Exception | None = None
        for _ in range(self._maximum_attempts):
            try:
                payload = self._memory.read(
                    self._mapping_name,
                    CLIENT_ACTION_TRACE_SIZE,
                )
            except Exception as exc:
                raise ClientActionTraceReadError(
                    f"could not read the exact action-trace mapping: {type(exc).__name__}"
                ) from exc
            try:
                return parse_client_action_trace(
                    payload,
                    expected_process_id=self._process_id,
                    expected_process_creation_filetime_utc=self._creation,
                )
            except ClientActionTraceError as exc:
                last_error = exc
        raise ClientActionTraceReadError(
            f"could not obtain a coherent action-trace snapshot: {last_error}"
        ) from last_error

    def wait_for_records(
        self,
        *,
        after_sequence: int = 0,
        minimum_records: int = 1,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.05,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> ClientActionTraceSnapshot:
        if (
            isinstance(after_sequence, bool)
            or not isinstance(after_sequence, int)
            or after_sequence < 0
        ):
            raise ValueError("after_sequence must be a non-negative integer")
        if (
            isinstance(minimum_records, bool)
            or not isinstance(minimum_records, int)
            or minimum_records <= 0
        ):
            raise ValueError("minimum_records must be a positive integer")
        for value, name in (
            (timeout_seconds, "timeout_seconds"),
            (poll_interval_seconds, "poll_interval_seconds"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value <= 0
            ):
                raise ValueError(f"{name} must be positive")
        if not callable(clock) or not callable(sleeper):
            raise ValueError("clock and sleeper must be callable")

        deadline = clock() + float(timeout_seconds)
        while True:
            snapshot = self.snapshot()
            if not snapshot.header.ready_for_capture:
                raise ClientActionTraceNotArmed(
                    "action-188 trace transport is present, but the reviewed "
                    "callsite profile is not armed"
                )
            new_records = tuple(
                record
                for record in snapshot.records
                if record.sequence > after_sequence
            )
            if len(new_records) >= minimum_records:
                return ClientActionTraceSnapshot(
                    header=snapshot.header,
                    records=new_records,
                )
            remaining = deadline - clock()
            if remaining <= 0:
                raise ClientActionTraceReadError(
                    "timed out waiting for action-188 trace records"
                )
            sleeper(min(float(poll_interval_seconds), remaining))


def open_windows_client_action_trace_reader(
    process_id: int,
    process_creation_filetime_utc: int,
) -> ClientActionTraceReader:
    return ClientActionTraceReader(
        process_id,
        process_creation_filetime_utc,
        WindowsSharedMemorySnapshotReader(),
    )


__all__ = [
    "ClientActionTraceNotArmed",
    "ClientActionTraceReadError",
    "ClientActionTraceReader",
    "open_windows_client_action_trace_reader",
]
