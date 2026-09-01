"""Read-only access to one exact extension event-channel mapping."""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from .events import (
    EXTENSION_EVENT_CHANNEL_SIZE,
    ExtensionEventChannelSnapshot,
    ExtensionEventError,
    extension_event_mapping_name,
    parse_extension_event_channel,
)


class ExtensionEventChannelReadError(RuntimeError):
    """Raised when the exact shared-memory event channel cannot be read coherently."""


@runtime_checkable
class SharedMemorySnapshotReader(Protocol):
    def read(self, name: str, size: int) -> bytes: ...


class ExtensionEventChannelReader:
    """Validate snapshots from the channel owned by one exact process lifetime."""

    def __init__(
        self,
        process_id: int,
        process_creation_filetime_utc: int,
        memory: SharedMemorySnapshotReader,
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
        if not isinstance(memory, SharedMemorySnapshotReader):
            raise ValueError("memory must implement SharedMemorySnapshotReader")
        self._process_id = process_id
        self._process_creation_filetime_utc = process_creation_filetime_utc
        self._memory = memory
        self._mapping_name = extension_event_mapping_name(
            process_id,
            process_creation_filetime_utc,
        )

    @property
    def process_id(self) -> int:
        return self._process_id

    @property
    def process_creation_filetime_utc(self) -> int:
        return self._process_creation_filetime_utc

    @property
    def process_identity(self) -> tuple[int, int]:
        return self._process_id, self._process_creation_filetime_utc

    @property
    def mapping_name(self) -> str:
        return self._mapping_name

    def snapshot(self) -> ExtensionEventChannelSnapshot:
        try:
            payload = self._memory.read(self._mapping_name, EXTENSION_EVENT_CHANNEL_SIZE)
        except Exception as exc:
            raise ExtensionEventChannelReadError(
                f"could not read the exact extension event channel: {type(exc).__name__}"
            ) from exc
        try:
            return parse_extension_event_channel(
                payload,
                expected_process_id=self._process_id,
                expected_process_creation_filetime_utc=(
                    self._process_creation_filetime_utc
                ),
            )
        except ExtensionEventError as exc:
            raise ExtensionEventChannelReadError(str(exc)) from exc


class WindowsSharedMemorySnapshotReader:
    """Open an existing named mapping without creating or mutating it."""

    _FILE_MAP_READ = 0x0004

    def __init__(self) -> None:
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
        self._kernel32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
        self._kernel32.UnmapViewOfFile.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._kernel32.CloseHandle.restype = wintypes.BOOL

    def read(self, name: str, size: int) -> bytes:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("mapping name must be a non-empty string")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError("mapping size must be a positive integer")
        mapping = self._kernel32.OpenFileMappingW(self._FILE_MAP_READ, False, name)
        if not mapping:
            raise OSError(self._ctypes.get_last_error(), "OpenFileMappingW failed")
        view = None
        try:
            view = self._kernel32.MapViewOfFile(
                mapping,
                self._FILE_MAP_READ,
                0,
                0,
                size,
            )
            if not view:
                raise OSError(self._ctypes.get_last_error(), "MapViewOfFile failed")
            return self._ctypes.string_at(view, size)
        finally:
            if view:
                self._kernel32.UnmapViewOfFile(view)
            self._kernel32.CloseHandle(mapping)


def open_windows_extension_event_channel_reader(
    process_id: int,
    process_creation_filetime_utc: int,
) -> ExtensionEventChannelReader:
    return ExtensionEventChannelReader(
        process_id,
        process_creation_filetime_utc,
        WindowsSharedMemorySnapshotReader(),
    )


__all__ = [
    "ExtensionEventChannelReadError",
    "ExtensionEventChannelReader",
    "SharedMemorySnapshotReader",
    "WindowsSharedMemorySnapshotReader",
    "open_windows_extension_event_channel_reader",
]
