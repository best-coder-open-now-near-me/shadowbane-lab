"""Read-only Windows process resource counters for one exact game PID."""

from __future__ import annotations

import os


def inspect_windows_process_metrics(process_id: int) -> dict[str, float]:
    if os.name != "nt":
        raise RuntimeError("runtime process metrics require Windows")
    if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
        raise ValueError("process_id must be a positive integer")

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

    process_query_information = 0x0400
    process_vm_read = 0x0010
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessHandleCount.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetProcessHandleCount.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCountersEx),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    process = kernel32.OpenProcess(
        process_query_information | process_vm_read,
        False,
        process_id,
    )
    if not process:
        raise OSError(ctypes.get_last_error(), "OpenProcess failed")
    try:
        memory = ProcessMemoryCountersEx()
        memory.cb = ctypes.sizeof(ProcessMemoryCountersEx)
        if not psapi.GetProcessMemoryInfo(process, ctypes.byref(memory), memory.cb):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        handle_count = wintypes.DWORD()
        if not kernel32.GetProcessHandleCount(process, ctypes.byref(handle_count)):
            raise OSError(ctypes.get_last_error(), "GetProcessHandleCount failed")
        return {
            "process_handle_count": float(handle_count.value),
            "process_private_bytes": float(memory.PrivateUsage),
            "process_working_set_bytes": float(memory.WorkingSetSize),
        }
    finally:
        kernel32.CloseHandle(process)


__all__ = ["inspect_windows_process_metrics"]
