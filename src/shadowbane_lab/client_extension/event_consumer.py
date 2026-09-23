"""Single-consumer ownership for one exact native extension event channel."""

from __future__ import annotations

import os
import threading
from typing import Protocol, runtime_checkable

from .events import (
    EXTENSION_EVENT_CHANNEL_SIZE,
    ExtensionEventChannelSnapshot,
    ExtensionEventError,
    ExtensionWorldMapDestinationEvent,
    extension_event_consumer_mutex_name,
    extension_event_mapping_name,
    extension_event_signal_name,
    parse_extension_event_channel,
)

_LOCAL_CONSUMER_LEASE_LOCK = threading.Lock()
_LOCAL_CONSUMER_LEASES: set[str] = set()


class ExtensionEventConsumerError(RuntimeError):
    """Raised when a channel cannot preserve exact single-consumer ownership."""


@runtime_checkable
class ExtensionEventTransport(Protocol):
    def claim(self) -> bool: ...

    def renew(self) -> bool: ...

    def read(self) -> bytes: ...

    def advance(self, expected_sequence: int, sequence: int) -> bool: ...

    def wait(self, timeout_seconds: float) -> None: ...

    def close(self) -> None: ...


class ExtensionEventConsumer:
    """Validate, lease, and acknowledge a channel without skipping an event."""

    def __init__(
        self,
        process_id: int,
        process_creation_filetime_utc: int,
        transport: ExtensionEventTransport,
    ) -> None:
        for value, field_name, maximum in (
            (process_id, "process_id", 0xFFFFFFFF),
            (
                process_creation_filetime_utc,
                "process_creation_filetime_utc",
                0xFFFFFFFFFFFFFFFF,
            ),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
                raise ValueError(f"{field_name} must be a bounded positive integer")
        if not isinstance(transport, ExtensionEventTransport):
            raise ValueError("transport must implement ExtensionEventTransport")
        self._process_id = process_id
        self._process_creation_filetime_utc = process_creation_filetime_utc
        self._transport = transport
        self._lock = threading.RLock()
        self._closed = False
        self._acknowledged_sequence = 0
        self._last_observed_write_sequence = 0
        if not transport.claim():
            transport.close()
            self._closed = True
            raise ExtensionEventConsumerError(
                "extension event channel already has an active consumer"
            )
        try:
            initial = self._parse(transport.read())
            self._acknowledged_sequence = initial.header.read_sequence
            self._last_observed_write_sequence = initial.header.write_sequence
            snapshot = self.snapshot()
        except BaseException:
            self.close()
            raise
        self._last_observed_write_sequence = snapshot.header.write_sequence

    @property
    def process_id(self) -> int:
        return self._process_id

    @property
    def process_creation_filetime_utc(self) -> int:
        return self._process_creation_filetime_utc

    @property
    def process_identity(self) -> tuple[int, int]:
        return self._process_id, self._process_creation_filetime_utc

    def snapshot(self) -> ExtensionEventChannelSnapshot:
        with self._lock:
            self._require_open()
            if not self._transport.renew():
                raise ExtensionEventConsumerError("extension event consumer lease was lost")
            last_error: ExtensionEventError | None = None
            for _ in range(3):
                first_payload = self._transport.read()
                second_payload = self._transport.read()
                try:
                    first = self._parse(first_payload)
                    second = self._parse(second_payload)
                except ExtensionEventError as exc:
                    last_error = exc
                    continue
                if first == second:
                    if first.header.read_sequence != self._acknowledged_sequence:
                        raise ExtensionEventConsumerError(
                            "extension event read sequence changed outside this consumer"
                        )
                    self._last_observed_write_sequence = first.header.write_sequence
                    return first
            detail = "extension event channel changed during every coherent read"
            if last_error is not None:
                detail = str(last_error)
            raise ExtensionEventConsumerError(detail)

    def pending(self) -> tuple[ExtensionWorldMapDestinationEvent, ...]:
        return self.snapshot().events

    def acknowledge(self, event: ExtensionWorldMapDestinationEvent) -> None:
        if not isinstance(event, ExtensionWorldMapDestinationEvent):
            raise ValueError("event must be ExtensionWorldMapDestinationEvent")
        with self._lock:
            self._require_open()
            if event.process_identity != self.process_identity:
                raise ExtensionEventConsumerError(
                    "cannot acknowledge an event from another process lifetime"
                )
            expected = self._acknowledged_sequence + 1
            if event.sequence != expected:
                raise ExtensionEventConsumerError(
                    "extension events must be acknowledged contiguously"
                )
            if event.sequence > self._last_observed_write_sequence:
                raise ExtensionEventConsumerError(
                    "cannot acknowledge an event that was not observed"
                )
            if not self._transport.advance(self._acknowledged_sequence, event.sequence):
                raise ExtensionEventConsumerError(
                    "extension event acknowledgement lost single-consumer ownership"
                )
            self._acknowledged_sequence = event.sequence

    def wait(self, timeout_seconds: float) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 <= timeout_seconds <= 0.5
        ):
            raise ValueError("timeout_seconds must be in [0, 0.5]")
        with self._lock:
            self._require_open()
            if not self._transport.renew():
                raise ExtensionEventConsumerError("extension event consumer lease was lost")
            self._transport.wait(float(timeout_seconds))
            if not self._transport.renew():
                raise ExtensionEventConsumerError("extension event consumer lease was lost")

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._transport.close()
                self._closed = True

    def __enter__(self) -> ExtensionEventConsumer:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _parse(self, payload: bytes) -> ExtensionEventChannelSnapshot:
        return parse_extension_event_channel(
            payload,
            expected_process_id=self._process_id,
            expected_process_creation_filetime_utc=(self._process_creation_filetime_utc),
        )

    def _require_open(self) -> None:
        if self._closed:
            raise ExtensionEventConsumerError("extension event consumer is closed")


class WindowsExtensionEventTransport:
    """Persistent read/write mapping with one renewable process-owned lease."""

    _FILE_MAP_WRITE = 0x0002
    _FILE_MAP_READ = 0x0004
    _SYNCHRONIZE = 0x00100000
    _WAIT_FAILED = 0xFFFFFFFF
    _WAIT_OBJECT_0 = 0
    _WAIT_ABANDONED = 0x00000080
    _WAIT_TIMEOUT = 0x00000102
    _CONSUMER_PROCESS_ID_OFFSET = 68
    _CONSUMER_HEARTBEAT_TICK_OFFSET = 72
    _READ_SEQUENCE_OFFSET = 48

    def __init__(
        self,
        process_id: int,
        process_creation_filetime_utc: int,
    ) -> None:
        if os.name != "nt":
            raise RuntimeError("extension event channels require Windows")
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.OpenFileMappingW.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        self._kernel32.OpenFileMappingW.restype = wintypes.HANDLE
        self._kernel32.MapViewOfFile.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_size_t,
        )
        self._kernel32.MapViewOfFile.restype = ctypes.c_void_p
        self._kernel32.OpenEventW.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        self._kernel32.OpenEventW.restype = wintypes.HANDLE
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise RuntimeError("extension event consumers require 64-bit Python")
        self._kernel32.CreateMutexW.argtypes = (
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        self._kernel32.CreateMutexW.restype = wintypes.HANDLE
        self._kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        self._kernel32.ReleaseMutex.restype = wintypes.BOOL
        self._kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        self._kernel32.GetCurrentProcessId.restype = wintypes.DWORD
        self._kernel32.WaitForSingleObject.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
        )
        self._kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self._kernel32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
        self._kernel32.UnmapViewOfFile.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._kernel32.CloseHandle.restype = wintypes.BOOL

        access = self._FILE_MAP_READ | self._FILE_MAP_WRITE
        mapping_name = extension_event_mapping_name(
            process_id,
            process_creation_filetime_utc,
        )
        signal_name = extension_event_signal_name(
            process_id,
            process_creation_filetime_utc,
        )
        consumer_mutex_name = extension_event_consumer_mutex_name(
            process_id,
            process_creation_filetime_utc,
        )
        self._consumer_mutex_name = consumer_mutex_name
        self._mapping = self._kernel32.OpenFileMappingW(access, False, mapping_name)
        if not self._mapping:
            raise OSError(ctypes.get_last_error(), "OpenFileMappingW failed")
        self._view = self._kernel32.MapViewOfFile(
            self._mapping,
            access,
            0,
            0,
            EXTENSION_EVENT_CHANNEL_SIZE,
        )
        if not self._view:
            error = ctypes.get_last_error()
            self._kernel32.CloseHandle(self._mapping)
            self._mapping = None
            raise OSError(error, "MapViewOfFile failed")
        self._signal = self._kernel32.OpenEventW(
            self._SYNCHRONIZE,
            False,
            signal_name,
        )
        if not self._signal:
            error = ctypes.get_last_error()
            self._kernel32.UnmapViewOfFile(self._view)
            self._kernel32.CloseHandle(self._mapping)
            self._view = None
            self._mapping = None
            raise OSError(error, "OpenEventW failed")
        self._consumer_mutex = self._kernel32.CreateMutexW(
            None,
            False,
            consumer_mutex_name,
        )
        if not self._consumer_mutex:
            error = ctypes.get_last_error()
            self._kernel32.CloseHandle(self._signal)
            self._kernel32.UnmapViewOfFile(self._view)
            self._kernel32.CloseHandle(self._mapping)
            self._signal = None
            self._view = None
            self._mapping = None
            raise OSError(error, "CreateMutexW failed")
        self._consumer_process_id = int(self._kernel32.GetCurrentProcessId())
        self._mutex_owned = False
        self._local_lease_owned = False
        self._claim_thread_id: int | None = None
        self._claimed = False
        self._closed = False

    def claim(self) -> bool:
        self._require_open()
        with _LOCAL_CONSUMER_LEASE_LOCK:
            if self._consumer_mutex_name in _LOCAL_CONSUMER_LEASES:
                return False
            _LOCAL_CONSUMER_LEASES.add(self._consumer_mutex_name)
            self._local_lease_owned = True
        result = self._kernel32.WaitForSingleObject(self._consumer_mutex, 0)
        if result == self._WAIT_TIMEOUT:
            self._release_local_lease()
            return False
        if result == self._WAIT_FAILED:
            self._release_local_lease()
            raise OSError(self._ctypes.get_last_error(), "consumer mutex wait failed")
        if result not in {self._WAIT_OBJECT_0, self._WAIT_ABANDONED}:
            self._release_local_lease()
            raise ExtensionEventConsumerError("consumer mutex returned an invalid wait state")
        self._mutex_owned = True
        self._claim_thread_id = threading.get_ident()
        self._uint32_at(self._CONSUMER_PROCESS_ID_OFFSET).value = self._consumer_process_id
        self._claimed = True
        return self.renew()

    def renew(self) -> bool:
        self._require_open()
        if not self._claimed:
            return False
        self._require_claim_thread()
        owner = self._uint32_at(self._CONSUMER_PROCESS_ID_OFFSET).value
        if owner != self._consumer_process_id:
            self._claimed = False
            return False
        self._uint64_at(self._CONSUMER_HEARTBEAT_TICK_OFFSET).value = int(
            self._kernel32.GetTickCount64()
        )
        return True

    def read(self) -> bytes:
        self._require_open()
        return self._ctypes.string_at(self._view, EXTENSION_EVENT_CHANNEL_SIZE)

    def advance(self, expected_sequence: int, sequence: int) -> bool:
        self._require_open()
        self._require_claim_thread()
        field = self._uint64_at(self._READ_SEQUENCE_OFFSET)
        if field.value != expected_sequence:
            return False
        field.value = sequence
        return True

    def wait(self, timeout_seconds: float) -> None:
        self._require_open()
        timeout_ms = min(500, max(0, round(timeout_seconds * 1000)))
        result = self._kernel32.WaitForSingleObject(self._signal, timeout_ms)
        if result == self._WAIT_FAILED:
            raise OSError(self._ctypes.get_last_error(), "WaitForSingleObject failed")

    def close(self) -> None:
        if self._closed:
            return
        release_error: OSError | None = None
        if self._claimed and self._view:
            self._require_claim_thread()
            if self._uint32_at(self._CONSUMER_PROCESS_ID_OFFSET).value == self._consumer_process_id:
                self._uint64_at(self._CONSUMER_HEARTBEAT_TICK_OFFSET).value = 0
                self._uint32_at(self._CONSUMER_PROCESS_ID_OFFSET).value = 0
            self._claimed = False
        if self._mutex_owned:
            if not self._kernel32.ReleaseMutex(self._consumer_mutex):
                release_error = OSError(self._ctypes.get_last_error(), "ReleaseMutex failed")
            self._mutex_owned = False
            self._claim_thread_id = None
        self._release_local_lease()
        if self._consumer_mutex:
            self._kernel32.CloseHandle(self._consumer_mutex)
            self._consumer_mutex = None
        if self._signal:
            self._kernel32.CloseHandle(self._signal)
            self._signal = None
        if self._view:
            self._kernel32.UnmapViewOfFile(self._view)
            self._view = None
        if self._mapping:
            self._kernel32.CloseHandle(self._mapping)
            self._mapping = None
        self._closed = True
        if release_error is not None:
            raise release_error

    def _uint32_at(self, offset: int):
        return self._ctypes.c_uint32.from_address(self._view + offset)

    def _uint64_at(self, offset: int):
        return self._ctypes.c_uint64.from_address(self._view + offset)

    def _require_open(self) -> None:
        if self._closed or not self._view:
            raise ExtensionEventConsumerError("extension event transport is closed")

    def _require_claim_thread(self) -> None:
        if self._claim_thread_id != threading.get_ident():
            raise ExtensionEventConsumerError(
                "extension event consumer lease must remain on its claiming thread"
            )

    def _release_local_lease(self) -> None:
        if not self._local_lease_owned:
            return
        with _LOCAL_CONSUMER_LEASE_LOCK:
            _LOCAL_CONSUMER_LEASES.discard(self._consumer_mutex_name)
        self._local_lease_owned = False


def open_windows_extension_event_consumer(
    process_id: int,
    process_creation_filetime_utc: int,
) -> ExtensionEventConsumer:
    return ExtensionEventConsumer(
        process_id,
        process_creation_filetime_utc,
        WindowsExtensionEventTransport(
            process_id,
            process_creation_filetime_utc,
        ),
    )


__all__ = [
    "ExtensionEventConsumer",
    "ExtensionEventConsumerError",
    "ExtensionEventTransport",
    "WindowsExtensionEventTransport",
    "open_windows_extension_event_consumer",
]
