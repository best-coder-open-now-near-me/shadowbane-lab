"""Read-only discovery of exact Windows process lifetimes by executable name."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from .model import ProcessIdentity
from .windows import WindowsProcessProbe


class WindowsProcessDiscovery:
    """Discover process IDs with Toolhelp, then bind each through the exact process probe."""

    _TH32CS_SNAPPROCESS = 0x00000002
    _ERROR_NO_MORE_FILES = 18
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("process discovery requires Windows")

        class ProcessEntry32W(ctypes.Structure):
            _fields_ = (
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            )

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessEntry32W),
        )
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessEntry32W),
        )
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32 = kernel32
        self._entry_type = ProcessEntry32W
        self._process_probe = WindowsProcessProbe()

    def find(self, executable_name: str) -> list[ProcessIdentity]:
        if not executable_name or "\0" in executable_name:
            raise ValueError("executable_name must be non-empty text")
        snapshot = self._kernel32.CreateToolhelp32Snapshot(self._TH32CS_SNAPPROCESS, 0)
        if snapshot == self._INVALID_HANDLE_VALUE:
            raise OSError(ctypes.get_last_error(), "process snapshot failed")
        process_ids: list[int] = []
        try:
            entry = self._entry_type()
            entry.dwSize = ctypes.sizeof(entry)
            present = self._kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while present:
                if entry.szExeFile.casefold() == executable_name.casefold():
                    process_ids.append(int(entry.th32ProcessID))
                present = self._kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            error = ctypes.get_last_error()
            if error not in (0, self._ERROR_NO_MORE_FILES):
                raise OSError(error, "process snapshot enumeration failed")
        finally:
            self._kernel32.CloseHandle(snapshot)

        identities: list[ProcessIdentity] = []
        for process_id in sorted(set(process_ids)):
            try:
                identities.append(self._process_probe.sample(process_id).identity)
            except (OSError, ProcessLookupError):
                continue
        return identities


__all__ = ["WindowsProcessDiscovery"]
