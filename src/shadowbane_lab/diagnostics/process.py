"""Exact Windows process identity and read-only resource sampling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    process_id: int
    process_creation_filetime_utc: int
    executable_path: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.process_id, bool)
            or not isinstance(self.process_id, int)
            or self.process_id <= 0
        ):
            raise ValueError("process_id must be positive")
        if (
            isinstance(self.process_creation_filetime_utc, bool)
            or not isinstance(self.process_creation_filetime_utc, int)
            or self.process_creation_filetime_utc <= 0
        ):
            raise ValueError("process_creation_filetime_utc must be positive")
        if (
            not isinstance(self.executable_path, str)
            or not self.executable_path
            or "\0" in self.executable_path
        ):
            raise ValueError("executable_path must be non-empty text")

    @property
    def exact_key(self) -> tuple[int, int]:
        return self.process_id, self.process_creation_filetime_utc

    def as_dict(self) -> dict[str, object]:
        return {
            "process_id": self.process_id,
            "process_creation_filetime_utc": self.process_creation_filetime_utc,
            "executable_path": self.executable_path,
            "executable_name": Path(self.executable_path).name,
        }


@dataclass(frozen=True, slots=True)
class ProcessSample:
    identity: ProcessIdentity
    metrics: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        names = tuple(name for name, _ in self.metrics)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("process metrics must use unique canonical names")


@runtime_checkable
class ProcessProbe(Protocol):
    def sample(self, process_id: int) -> ProcessSample: ...


class WindowsProcessProbe:
    """Reads identity and counters through one live process handle per sample."""

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _PROCESS_VM_READ = 0x0010
    _SYNCHRONIZE = 0x00100000
    _WAIT_OBJECT_0 = 0
    _WAIT_TIMEOUT = 0x102

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows process diagnostics require Windows")

        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCountersEx(ctypes.Structure):
            _fields_ = (
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            )

        class IoCounters(ctypes.Structure):
            _fields_ = (
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            )

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        )
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.GetProcessHandleCount.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.GetProcessHandleCount.restype = wintypes.BOOL
        kernel32.GetProcessIoCounters.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(IoCounters),
        )
        kernel32.GetProcessIoCounters.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCountersEx),
            wintypes.DWORD,
        )
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        user32.GetGuiResources.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        user32.GetGuiResources.restype = wintypes.DWORD
        self._ctypes = ctypes
        self._wintypes = wintypes
        self._kernel32 = kernel32
        self._psapi = psapi
        self._user32 = user32
        self._memory_type = ProcessMemoryCountersEx
        self._io_type = IoCounters

    def sample(self, process_id: int) -> ProcessSample:
        if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
            raise ValueError("process_id must be positive")
        ctypes = self._ctypes
        wintypes = self._wintypes
        kernel32 = self._kernel32
        handle = kernel32.OpenProcess(
            self._PROCESS_QUERY_LIMITED_INFORMATION
            | self._PROCESS_VM_READ
            | self._SYNCHRONIZE,
            False,
            process_id,
        )
        if not handle:
            raise OSError(ctypes.get_last_error(), f"OpenProcess failed for PID {process_id}")
        try:
            wait_result = kernel32.WaitForSingleObject(handle, 0)
            if wait_result == self._WAIT_OBJECT_0:
                raise ProcessLookupError(f"PID {process_id} has exited")
            if wait_result != self._WAIT_TIMEOUT:
                raise OSError(
                    ctypes.get_last_error(),
                    f"WaitForSingleObject failed for PID {process_id}",
                )
            path_buffer = ctypes.create_unicode_buffer(32_768)
            path_length = wintypes.DWORD(len(path_buffer))
            if not kernel32.QueryFullProcessImageNameW(
                handle,
                0,
                path_buffer,
                ctypes.byref(path_length),
            ):
                raise OSError(
                    ctypes.get_last_error(),
                    f"QueryFullProcessImageNameW failed for PID {process_id}",
                )
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                raise OSError(
                    ctypes.get_last_error(),
                    f"GetProcessTimes failed for PID {process_id}",
                )
            creation_value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            identity = ProcessIdentity(process_id, creation_value, path_buffer.value)
            memory = self._memory_type()
            memory.cb = ctypes.sizeof(self._memory_type)
            if not self._psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
                raise OSError(
                    ctypes.get_last_error(),
                    f"GetProcessMemoryInfo failed for PID {process_id}",
                )
            handle_count = wintypes.DWORD()
            if not kernel32.GetProcessHandleCount(handle, ctypes.byref(handle_count)):
                raise OSError(
                    ctypes.get_last_error(),
                    f"GetProcessHandleCount failed for PID {process_id}",
                )
            io = self._io_type()
            if not kernel32.GetProcessIoCounters(handle, ctypes.byref(io)):
                raise OSError(
                    ctypes.get_last_error(),
                    f"GetProcessIoCounters failed for PID {process_id}",
                )
            metrics = {
                "cpu_kernel_seconds": _filetime_seconds(kernel_time),
                "cpu_user_seconds": _filetime_seconds(user_time),
                "gdi_object_count": float(self._user32.GetGuiResources(handle, 0)),
                "io_other_bytes": float(io.OtherTransferCount),
                "io_other_operations": float(io.OtherOperationCount),
                "io_read_bytes": float(io.ReadTransferCount),
                "io_read_operations": float(io.ReadOperationCount),
                "io_write_bytes": float(io.WriteTransferCount),
                "io_write_operations": float(io.WriteOperationCount),
                "page_fault_count": float(memory.PageFaultCount),
                "process_handle_count": float(handle_count.value),
                "process_peak_private_bytes": float(memory.PeakPagefileUsage),
                "process_peak_working_set_bytes": float(memory.PeakWorkingSetSize),
                "process_private_bytes": float(memory.PrivateUsage),
                "process_working_set_bytes": float(memory.WorkingSetSize),
                "user_object_count": float(self._user32.GetGuiResources(handle, 1)),
            }
            return ProcessSample(identity, tuple(sorted(metrics.items())))
        finally:
            kernel32.CloseHandle(handle)


def _filetime_seconds(value: Any) -> float:
    high = value.dwHighDateTime
    low = value.dwLowDateTime
    return float(((high << 32) | low) / 10_000_000)


__all__ = [
    "ProcessIdentity",
    "ProcessProbe",
    "ProcessSample",
    "WindowsProcessProbe",
]
