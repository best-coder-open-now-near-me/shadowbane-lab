"""Read-only Windows probes used by the standalone vanilla collector."""

from __future__ import annotations

import ctypes
import os
import socket
import struct
from ctypes import wintypes
from typing import Any

from .model import ProcessIdentity, ProcessSample


def _require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("vanilla Shadowbane diagnostics require Windows")


def _filetime_value(value: wintypes.FILETIME) -> int:
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


class WindowsProcessProbe:
    """Read exact process identity and cumulative resource counters."""

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _PROCESS_VM_READ = 0x0010
    _SYNCHRONIZE = 0x00100000
    _WAIT_OBJECT_0 = 0
    _WAIT_TIMEOUT = 0x102

    def __init__(self) -> None:
        _require_windows()

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
        self._kernel32 = kernel32
        self._psapi = psapi
        self._user32 = user32
        self._memory_type = ProcessMemoryCountersEx
        self._io_type = IoCounters

    def sample(self, process_id: int) -> ProcessSample:
        if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
            raise ValueError("process_id must be positive")
        handle = self._kernel32.OpenProcess(
            self._PROCESS_QUERY_LIMITED_INFORMATION
            | self._PROCESS_VM_READ
            | self._SYNCHRONIZE,
            False,
            process_id,
        )
        if not handle:
            raise OSError(ctypes.get_last_error(), f"OpenProcess failed for PID {process_id}")
        try:
            wait_result = self._kernel32.WaitForSingleObject(handle, 0)
            if wait_result == self._WAIT_OBJECT_0:
                raise ProcessLookupError(f"PID {process_id} has exited")
            if wait_result != self._WAIT_TIMEOUT:
                raise OSError(
                    ctypes.get_last_error(),
                    f"WaitForSingleObject failed for PID {process_id}",
                )
            path_buffer = ctypes.create_unicode_buffer(32_768)
            path_length = wintypes.DWORD(len(path_buffer))
            if not self._kernel32.QueryFullProcessImageNameW(
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
            if not self._kernel32.GetProcessTimes(
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
            identity = ProcessIdentity(process_id, _filetime_value(creation), path_buffer.value)
            memory = self._memory_type()
            memory.cb = ctypes.sizeof(self._memory_type)
            if not self._psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
                raise OSError(
                    ctypes.get_last_error(),
                    f"GetProcessMemoryInfo failed for PID {process_id}",
                )
            handle_count = wintypes.DWORD()
            if not self._kernel32.GetProcessHandleCount(handle, ctypes.byref(handle_count)):
                raise OSError(
                    ctypes.get_last_error(),
                    f"GetProcessHandleCount failed for PID {process_id}",
                )
            io = self._io_type()
            if not self._kernel32.GetProcessIoCounters(handle, ctypes.byref(io)):
                raise OSError(
                    ctypes.get_last_error(),
                    f"GetProcessIoCounters failed for PID {process_id}",
                )
            metrics: dict[str, int | float] = {
                "cpu_kernel_seconds": _filetime_value(kernel_time) / 10_000_000,
                "cpu_user_seconds": _filetime_value(user_time) / 10_000_000,
                "gdi_object_count": int(self._user32.GetGuiResources(handle, 0)),
                "io_other_bytes": int(io.OtherTransferCount),
                "io_other_operations": int(io.OtherOperationCount),
                "io_read_bytes": int(io.ReadTransferCount),
                "io_read_operations": int(io.ReadOperationCount),
                "io_write_bytes": int(io.WriteTransferCount),
                "io_write_operations": int(io.WriteOperationCount),
                "page_fault_count": int(memory.PageFaultCount),
                "process_handle_count": int(handle_count.value),
                "process_peak_private_bytes": int(memory.PeakPagefileUsage),
                "process_peak_working_set_bytes": int(memory.PeakWorkingSetSize),
                "process_private_bytes": int(memory.PrivateUsage),
                "process_working_set_bytes": int(memory.WorkingSetSize),
                "user_object_count": int(self._user32.GetGuiResources(handle, 1)),
            }
            return ProcessSample(identity, metrics)
        finally:
            self._kernel32.CloseHandle(handle)



class WindowsModuleProbe:
    """Enumerate loaded modules for residue rejection without entering the process."""

    _TH32CS_SNAPMODULE = 0x00000008
    _TH32CS_SNAPMODULE32 = 0x00000010
    _ERROR_BAD_LENGTH = 24
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def __init__(self) -> None:
        _require_windows()

        class ModuleEntry32W(ctypes.Structure):
            _fields_ = (
                ("dwSize", wintypes.DWORD),
                ("th32ModuleID", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("GlblcntUsage", wintypes.DWORD),
                ("ProccntUsage", wintypes.DWORD),
                ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
                ("modBaseSize", wintypes.DWORD),
                ("hModule", wintypes.HMODULE),
                ("szModule", wintypes.WCHAR * 256),
                ("szExePath", wintypes.WCHAR * 260),
            )

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Module32FirstW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ModuleEntry32W),
        )
        kernel32.Module32FirstW.restype = wintypes.BOOL
        kernel32.Module32NextW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ModuleEntry32W),
        )
        kernel32.Module32NextW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32 = kernel32
        self._entry_type = ModuleEntry32W

    def list_modules(self, process_id: int) -> list[dict[str, object]]:
        snapshot: int | None = None
        for _ in range(8):
            candidate = self._kernel32.CreateToolhelp32Snapshot(
                self._TH32CS_SNAPMODULE | self._TH32CS_SNAPMODULE32,
                process_id,
            )
            if candidate != self._INVALID_HANDLE_VALUE:
                snapshot = candidate
                break
            if ctypes.get_last_error() != self._ERROR_BAD_LENGTH:
                break
        if snapshot is None:
            raise OSError(ctypes.get_last_error(), f"module snapshot failed for PID {process_id}")
        try:
            entry = self._entry_type()
            entry.dwSize = ctypes.sizeof(entry)
            modules: list[dict[str, object]] = []
            present = self._kernel32.Module32FirstW(snapshot, ctypes.byref(entry))
            while present:
                modules.append(
                    {
                        "name": entry.szModule,
                        "path": entry.szExePath,
                        "image_size": int(entry.modBaseSize),
                    }
                )
                present = self._kernel32.Module32NextW(snapshot, ctypes.byref(entry))
            return modules
        finally:
            self._kernel32.CloseHandle(snapshot)


class WindowsWindowInputProbe:
    """Capture exact-process window state and non-content input timing."""

    def __init__(self) -> None:
        _require_windows()

        class LastInputInfo(ctypes.Structure):
            _fields_ = (("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD))

        enum_callback = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.EnumWindows.argtypes = (enum_callback, wintypes.LPARAM)
        user32.EnumWindows.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsWindowVisible.argtypes = (wintypes.HWND,)
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = (wintypes.HWND,)
        user32.IsIconic.restype = wintypes.BOOL
        user32.IsZoomed.argtypes = (wintypes.HWND,)
        user32.IsZoomed.restype = wintypes.BOOL
        user32.IsHungAppWindow.argtypes = (wintypes.HWND,)
        user32.IsHungAppWindow.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        user32.GetClientRect.restype = wintypes.BOOL
        user32.GetForegroundWindow.argtypes = ()
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetLastInputInfo.argtypes = (ctypes.POINTER(LastInputInfo),)
        user32.GetLastInputInfo.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
        user32.GetCursorPos.restype = wintypes.BOOL
        self._user32 = user32
        self._last_input_type = LastInputInfo
        self._enum_callback_type = enum_callback

    def sample(self, process_id: int) -> dict[str, object]:
        windows: list[dict[str, object]] = []

        @self._enum_callback_type
        def visit(handle: wintypes.HWND, _parameter: wintypes.LPARAM) -> bool:
            owner = wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
            if owner.value != process_id:
                return True
            rectangle = wintypes.RECT()
            client = wintypes.RECT()
            rectangle_ok = bool(self._user32.GetWindowRect(handle, ctypes.byref(rectangle)))
            client_ok = bool(self._user32.GetClientRect(handle, ctypes.byref(client)))
            windows.append(
                {
                    "handle": int(handle),
                    "visible": bool(self._user32.IsWindowVisible(handle)),
                    "minimized": bool(self._user32.IsIconic(handle)),
                    "maximized": bool(self._user32.IsZoomed(handle)),
                    "reported_hung": bool(self._user32.IsHungAppWindow(handle)),
                    "rect": (
                        [rectangle.left, rectangle.top, rectangle.right, rectangle.bottom]
                        if rectangle_ok
                        else None
                    ),
                    "client_size": (
                        [client.right - client.left, client.bottom - client.top]
                        if client_ok
                        else None
                    ),
                }
            )
            return True

        if not self._user32.EnumWindows(visit, 0):
            error = ctypes.get_last_error()
            if error:
                raise OSError(error, "EnumWindows failed")
        foreground = self._user32.GetForegroundWindow()
        foreground_process = wintypes.DWORD()
        if foreground:
            self._user32.GetWindowThreadProcessId(foreground, ctypes.byref(foreground_process))
        last_input = self._last_input_type()
        last_input.cbSize = ctypes.sizeof(last_input)
        if not self._user32.GetLastInputInfo(ctypes.byref(last_input)):
            raise OSError(ctypes.get_last_error(), "GetLastInputInfo failed")
        cursor = wintypes.POINT()
        cursor_ok = bool(self._user32.GetCursorPos(ctypes.byref(cursor)))
        tick_now = self._tick_count64()
        input_age = max(0, tick_now - int(last_input.dwTime))
        return {
            "windows": sorted(windows, key=lambda item: int(item["handle"])),
            "foreground_window_handle": int(foreground or 0),
            "foreground_process_id": int(foreground_process.value),
            "target_is_foreground": foreground_process.value == process_id,
            "last_input_age_ms": input_age,
            "cursor_position": [cursor.x, cursor.y] if cursor_ok else None,
            "input_content_captured": False,
        }

    @staticmethod
    def _tick_count64() -> int:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetTickCount64.argtypes = ()
        kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        return int(kernel32.GetTickCount64())


class WindowsDwmFrameProbe:
    """Read compositor timing counters as an explicitly non-app-specific frame proxy."""

    def __init__(self) -> None:
        _require_windows()

        class UnsignedRatio(ctypes.Structure):
            _fields_ = (("uiNumerator", wintypes.UINT), ("uiDenominator", wintypes.UINT))

        class DwmTimingInfo(ctypes.Structure):
            _fields_ = (
                ("cbSize", wintypes.UINT),
                ("rateRefresh", UnsignedRatio),
                ("qpcRefreshPeriod", ctypes.c_longlong),
                ("rateCompose", UnsignedRatio),
                ("qpcVBlank", ctypes.c_longlong),
                ("cRefresh", ctypes.c_ulonglong),
                ("cDXRefresh", wintypes.UINT),
                ("qpcCompose", ctypes.c_longlong),
                ("cFrame", ctypes.c_ulonglong),
                ("cDXPresent", wintypes.UINT),
                ("cRefreshFrame", ctypes.c_ulonglong),
                ("cFrameSubmitted", ctypes.c_ulonglong),
                ("cDXPresentSubmitted", wintypes.UINT),
                ("cFrameConfirmed", ctypes.c_ulonglong),
                ("cDXPresentConfirmed", wintypes.UINT),
                ("cRefreshConfirmed", ctypes.c_ulonglong),
                ("cDXRefreshConfirmed", wintypes.UINT),
                ("cFramesLate", ctypes.c_ulonglong),
                ("cFramesOutstanding", wintypes.UINT),
                ("cFrameDisplayed", ctypes.c_ulonglong),
                ("qpcFrameDisplayed", ctypes.c_longlong),
                ("cRefreshFrameDisplayed", ctypes.c_ulonglong),
                ("cFrameComplete", ctypes.c_ulonglong),
                ("qpcFrameComplete", ctypes.c_longlong),
                ("cFramePending", ctypes.c_ulonglong),
                ("qpcFramePending", ctypes.c_longlong),
                ("cFramesDisplayed", ctypes.c_ulonglong),
                ("cFramesComplete", ctypes.c_ulonglong),
                ("cFramesPending", ctypes.c_ulonglong),
                ("cFramesAvailable", ctypes.c_ulonglong),
                ("cFramesDropped", ctypes.c_ulonglong),
                ("cFramesMissed", ctypes.c_ulonglong),
                ("cRefreshNextDisplayed", ctypes.c_ulonglong),
                ("cRefreshNextPresented", ctypes.c_ulonglong),
                ("cRefreshesDisplayed", ctypes.c_ulonglong),
                ("cRefreshesPresented", ctypes.c_ulonglong),
                ("cRefreshStarted", ctypes.c_ulonglong),
                ("cPixelsReceived", ctypes.c_ulonglong),
                ("cPixelsDrawn", ctypes.c_ulonglong),
                ("cBuffersEmpty", ctypes.c_ulonglong),
            )

        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        dwmapi.DwmGetCompositionTimingInfo.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(DwmTimingInfo),
        )
        dwmapi.DwmGetCompositionTimingInfo.restype = ctypes.c_long
        self._dwmapi = dwmapi
        self._timing_type = DwmTimingInfo

    def sample(self, window_handle: int) -> dict[str, object]:
        timing = self._timing_type()
        timing.cbSize = ctypes.sizeof(timing)
        result = self._dwmapi.DwmGetCompositionTimingInfo(window_handle, ctypes.byref(timing))
        if result != 0:
            raise OSError(result & 0xFFFFFFFF, "DwmGetCompositionTimingInfo failed")
        denominator = timing.rateRefresh.uiDenominator
        refresh_hz = (
            timing.rateRefresh.uiNumerator / denominator if denominator else None
        )
        return {
            "scope": "DWM compositor for the target window's monitor; not exact app presents",
            "target_window_handle": window_handle,
            "refresh_hz": refresh_hz,
            "qpc_refresh_period": int(timing.qpcRefreshPeriod),
            "qpc_vblank": int(timing.qpcVBlank),
            "composition_frame": int(timing.cFrame),
            "composition_refresh": int(timing.cRefresh),
            "dx_present": int(timing.cDXPresent),
            "frames_displayed": int(timing.cFramesDisplayed),
            "frames_complete": int(timing.cFramesComplete),
            "frames_pending": int(timing.cFramesPending),
            "frames_available": int(timing.cFramesAvailable),
            "frames_dropped": int(timing.cFramesDropped),
            "frames_missed": int(timing.cFramesMissed),
            "frames_late": int(timing.cFramesLate),
            "frames_outstanding": int(timing.cFramesOutstanding),
        }


class WindowsNetworkProbe:
    """Read exact-process TCP/UDP endpoint metadata without packet payloads."""

    _TCP_TABLE_OWNER_PID_ALL = 5
    _UDP_TABLE_OWNER_PID = 1
    _ERROR_INSUFFICIENT_BUFFER = 122

    def __init__(self) -> None:
        _require_windows()
        iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
        iphlpapi.GetExtendedTcpTable.argtypes = (
            wintypes.LPVOID,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.BOOL,
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.ULONG,
        )
        iphlpapi.GetExtendedTcpTable.restype = wintypes.DWORD
        iphlpapi.GetExtendedUdpTable.argtypes = (
            wintypes.LPVOID,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.BOOL,
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.ULONG,
        )
        iphlpapi.GetExtendedUdpTable.restype = wintypes.DWORD
        self._iphlpapi = iphlpapi

    def sample(self, process_id: int) -> dict[str, object]:
        endpoints: list[dict[str, object]] = []
        endpoints.extend(self._tcp4(process_id))
        endpoints.extend(self._tcp6(process_id))
        endpoints.extend(self._udp4(process_id))
        endpoints.extend(self._udp6(process_id))
        endpoints.sort(
            key=lambda item: (
                str(item["protocol"]),
                str(item["local_address"]),
                int(item["local_port"]),
                str(item.get("remote_address", "")),
                int(item.get("remote_port", 0)),
            )
        )
        return {"payload_captured": False, "endpoints": endpoints}

    def _table(self, function: Any, family: int, table_class: int) -> bytes:
        size = wintypes.DWORD()
        result = function(None, ctypes.byref(size), True, family, table_class, 0)
        if result != self._ERROR_INSUFFICIENT_BUFFER:
            raise OSError(result, "IP Helper table size query failed")
        buffer = ctypes.create_string_buffer(size.value)
        result = function(buffer, ctypes.byref(size), True, family, table_class, 0)
        if result != 0:
            raise OSError(result, "IP Helper table query failed")
        return buffer.raw[: size.value]

    @staticmethod
    def _rows(data: bytes, row_type: type[ctypes.Structure]) -> list[ctypes.Structure]:
        if len(data) < 4:
            raise ValueError("IP Helper table is truncated")
        count = struct.unpack_from("<I", data, 0)[0]
        row_size = ctypes.sizeof(row_type)
        if 4 + count * row_size > len(data):
            raise ValueError("IP Helper table row count exceeds its buffer")
        return [row_type.from_buffer_copy(data, 4 + index * row_size) for index in range(count)]

    def _tcp4(self, process_id: int) -> list[dict[str, object]]:
        class Row(ctypes.Structure):
            _fields_ = (
                ("state", wintypes.DWORD),
                ("local_address", wintypes.DWORD),
                ("local_port", wintypes.DWORD),
                ("remote_address", wintypes.DWORD),
                ("remote_port", wintypes.DWORD),
                ("process_id", wintypes.DWORD),
            )

        data = self._table(
            self._iphlpapi.GetExtendedTcpTable,
            socket.AF_INET,
            self._TCP_TABLE_OWNER_PID_ALL,
        )
        return [
            {
                "protocol": "tcp4",
                "state": int(row.state),
                "local_address": socket.inet_ntoa(struct.pack("<I", row.local_address)),
                "local_port": socket.ntohs(row.local_port & 0xFFFF),
                "remote_address": socket.inet_ntoa(struct.pack("<I", row.remote_address)),
                "remote_port": socket.ntohs(row.remote_port & 0xFFFF),
            }
            for row in self._rows(data, Row)
            if row.process_id == process_id
        ]

    def _tcp6(self, process_id: int) -> list[dict[str, object]]:
        class Row(ctypes.Structure):
            _fields_ = (
                ("local_address", ctypes.c_ubyte * 16),
                ("local_scope_id", wintypes.DWORD),
                ("local_port", wintypes.DWORD),
                ("remote_address", ctypes.c_ubyte * 16),
                ("remote_scope_id", wintypes.DWORD),
                ("remote_port", wintypes.DWORD),
                ("state", wintypes.DWORD),
                ("process_id", wintypes.DWORD),
            )

        data = self._table(
            self._iphlpapi.GetExtendedTcpTable,
            socket.AF_INET6,
            self._TCP_TABLE_OWNER_PID_ALL,
        )
        return [
            {
                "protocol": "tcp6",
                "state": int(row.state),
                "local_address": socket.inet_ntop(socket.AF_INET6, bytes(row.local_address)),
                "local_scope_id": int(row.local_scope_id),
                "local_port": socket.ntohs(row.local_port & 0xFFFF),
                "remote_address": socket.inet_ntop(socket.AF_INET6, bytes(row.remote_address)),
                "remote_scope_id": int(row.remote_scope_id),
                "remote_port": socket.ntohs(row.remote_port & 0xFFFF),
            }
            for row in self._rows(data, Row)
            if row.process_id == process_id
        ]

    def _udp4(self, process_id: int) -> list[dict[str, object]]:
        class Row(ctypes.Structure):
            _fields_ = (
                ("local_address", wintypes.DWORD),
                ("local_port", wintypes.DWORD),
                ("process_id", wintypes.DWORD),
            )

        data = self._table(
            self._iphlpapi.GetExtendedUdpTable,
            socket.AF_INET,
            self._UDP_TABLE_OWNER_PID,
        )
        return [
            {
                "protocol": "udp4",
                "local_address": socket.inet_ntoa(struct.pack("<I", row.local_address)),
                "local_port": socket.ntohs(row.local_port & 0xFFFF),
            }
            for row in self._rows(data, Row)
            if row.process_id == process_id
        ]

    def _udp6(self, process_id: int) -> list[dict[str, object]]:
        class Row(ctypes.Structure):
            _fields_ = (
                ("local_address", ctypes.c_ubyte * 16),
                ("local_scope_id", wintypes.DWORD),
                ("local_port", wintypes.DWORD),
                ("process_id", wintypes.DWORD),
            )

        data = self._table(
            self._iphlpapi.GetExtendedUdpTable,
            socket.AF_INET6,
            self._UDP_TABLE_OWNER_PID,
        )
        return [
            {
                "protocol": "udp6",
                "local_address": socket.inet_ntop(socket.AF_INET6, bytes(row.local_address)),
                "local_scope_id": int(row.local_scope_id),
                "local_port": socket.ntohs(row.local_port & 0xFFFF),
            }
            for row in self._rows(data, Row)
            if row.process_id == process_id
        ]


def select_primary_window(window_sample: dict[str, object]) -> int:
    candidates = [
        item
        for item in window_sample.get("windows", [])
        if isinstance(item, dict) and item.get("visible") and not item.get("minimized")
    ]
    if not candidates:
        return 0
    candidates.sort(
        key=lambda item: (
            -_window_area(item.get("rect")),
            int(item.get("handle", 0)),
        )
    )
    return int(candidates[0].get("handle", 0))


def _window_area(value: object) -> int:
    if not isinstance(value, list) or len(value) != 4:
        return 0
    left, top, right, bottom = value
    if not all(isinstance(item, int) for item in value):
        return 0
    return max(0, right - left) * max(0, bottom - top)


__all__ = [
    "WindowsDwmFrameProbe",
    "WindowsModuleProbe",
    "WindowsNetworkProbe",
    "WindowsProcessProbe",
    "WindowsWindowInputProbe",
    "select_primary_window",
]
