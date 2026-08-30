"""Ephemeral, non-activating Windows overlay for fuzzy zone-search results."""

from __future__ import annotations

import os
import queue
import threading
from collections.abc import Sequence

from shadowbane_lab.travel.named import ZoneSearchResult


def format_zone_search_overlay(
    query: str,
    results: Sequence[ZoneSearchResult],
) -> str:
    """Format compact results whose displayed names can be copied into ``/go``."""

    if not isinstance(query, str) or not query.strip():
        raise ValueError("zone search query must be non-empty")
    if any(not isinstance(item, ZoneSearchResult) for item in results):
        raise ValueError("zone search results must contain ZoneSearchResult values")
    lines = [f'Zone search: "{query.strip()}"']
    if not results:
        lines.extend(("No matching zones.", "Try a shorter name or a different spelling."))
        return "\n".join(lines)
    for index, result in enumerate(results, start=1):
        destination = result.destination
        lines.append(
            f"{index}. {result.canonical_name}  [LT {destination.lt:g}, LG {destination.lg:g}]"
        )
        lines.append(f"   /go {result.canonical_name}")
    return "\n".join(lines)


class WindowsZoneSearchOverlay:
    """Show search results above the game without taking focus or mouse input."""

    _WM_APP_SHOW = 0x8001

    def __init__(self, *, visible_ms: int = 15_000) -> None:
        if isinstance(visible_ms, bool) or not isinstance(visible_ms, int):
            raise ValueError("visible_ms must be an integer")
        if not 1_000 <= visible_ms <= 120_000:
            raise ValueError("visible_ms must be between 1000 and 120000")
        self._visible_ms = visible_ms
        self._messages: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._window_handle: int | None = None
        self._startup_error: BaseException | None = None
        self._closed = False

    def show(self, query: str, results: Sequence[ZoneSearchResult]) -> None:
        text = format_zone_search_overlay(query, results)
        self._start()
        self._messages.put(text)
        window_handle = self._window_handle
        if window_handle is None:
            raise RuntimeError("zone-search overlay did not create a window")
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        from ctypes import wintypes

        user32.PostMessageW.argtypes = (
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.PostMessageW.restype = wintypes.BOOL
        if not user32.PostMessageW(
            window_handle,
            self._WM_APP_SHOW,
            0,
            0,
        ):
            raise OSError(ctypes.get_last_error(), "could not update zone-search overlay")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            thread = self._thread
            window_handle = self._window_handle
        if window_handle is not None and os.name == "nt":
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostMessageW.argtypes = (
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            )
            user32.PostMessageW(window_handle, 0x0010, 0, 0)
        if thread is not None:
            thread.join(timeout=2.0)

    def __enter__(self) -> WindowsZoneSearchOverlay:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("zone-search overlay requires Windows")
        with self._lock:
            if self._closed:
                raise RuntimeError("zone-search overlay is closed")
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run,
                    name="shadowbane-zone-search-overlay",
                    daemon=True,
                )
                self._thread.start()
        if not self._ready.wait(timeout=5.0):
            raise RuntimeError("zone-search overlay did not initialize")
        if self._startup_error is not None:
            raise RuntimeError(
                f"zone-search overlay failed: {self._startup_error}"
            ) from self._startup_error

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        lresult = ctypes.c_ssize_t
        window_procedure_type = ctypes.WINFUNCTYPE(
            lresult,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        class WindowClass(ctypes.Structure):
            _fields_ = (
                ("style", wintypes.UINT),
                ("window_procedure", window_procedure_type),
                ("class_extra", ctypes.c_int),
                ("window_extra", ctypes.c_int),
                ("instance", wintypes.HINSTANCE),
                ("icon", wintypes.HICON),
                ("cursor", wintypes.HANDLE),
                ("background", wintypes.HBRUSH),
                ("menu_name", wintypes.LPCWSTR),
                ("class_name", wintypes.LPCWSTR),
            )

        class PaintStruct(ctypes.Structure):
            _fields_ = (
                ("device", wintypes.HDC),
                ("erase", wintypes.BOOL),
                ("paint", wintypes.RECT),
                ("restore", wintypes.BOOL),
                ("incremental_update", wintypes.BOOL),
                ("reserved", ctypes.c_byte * 32),
            )

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        user32.RegisterClassW.argtypes = (ctypes.POINTER(WindowClass),)
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = (
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        )
        user32.DefWindowProcW.argtypes = (
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.DefWindowProcW.restype = lresult
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.SetLayeredWindowAttributes.argtypes = (
            wintypes.HWND,
            wintypes.COLORREF,
            wintypes.BYTE,
            wintypes.DWORD,
        )
        user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = (
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        )
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.SetTimer.argtypes = (
            wintypes.HWND,
            ctypes.c_size_t,
            wintypes.UINT,
            wintypes.LPVOID,
        )
        user32.KillTimer.argtypes = (wintypes.HWND, ctypes.c_size_t)
        user32.InvalidateRect.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
            wintypes.BOOL,
        )
        user32.BeginPaint.argtypes = (wintypes.HWND, ctypes.POINTER(PaintStruct))
        user32.BeginPaint.restype = wintypes.HDC
        user32.EndPaint.argtypes = (wintypes.HWND, ctypes.POINTER(PaintStruct))
        user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        user32.FillRect.argtypes = (
            wintypes.HDC,
            ctypes.POINTER(wintypes.RECT),
            wintypes.HBRUSH,
        )
        user32.DrawTextW.argtypes = (
            wintypes.HDC,
            wintypes.LPCWSTR,
            ctypes.c_int,
            ctypes.POINTER(wintypes.RECT),
            wintypes.UINT,
        )
        user32.GetMessageW.argtypes = (
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        )
        user32.GetMessageW.restype = ctypes.c_int
        user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
        user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
        user32.DispatchMessageW.restype = lresult
        user32.DestroyWindow.argtypes = (wintypes.HWND,)
        user32.IsWindow.argtypes = (wintypes.HWND,)
        user32.UnregisterClassW.argtypes = (wintypes.LPCWSTR, wintypes.HINSTANCE)
        gdi32.CreateSolidBrush.argtypes = (wintypes.COLORREF,)
        gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
        gdi32.SetBkMode.argtypes = (wintypes.HDC, ctypes.c_int)
        gdi32.SetTextColor.argtypes = (wintypes.HDC, wintypes.COLORREF)
        module = kernel32.GetModuleHandleW(None)
        class_name = f"ShadowbaneLabZoneSearchOverlay{os.getpid()}"
        background = gdi32.CreateSolidBrush(0x00181818)
        current_text = ""

        @window_procedure_type
        def window_procedure(
            window: int,
            message: int,
            word_parameter: int,
            long_parameter: int,
        ) -> int:
            nonlocal current_text
            if message == self._WM_APP_SHOW:
                try:
                    while True:
                        current_text = self._messages.get_nowait()
                except queue.Empty:
                    pass
                lines = current_text.splitlines() or [""]
                width = min(980, max(520, max(len(line) for line in lines) * 10 + 36))
                height = min(500, max(82, len(lines) * 24 + 28))
                user32.KillTimer(window, 1)
                user32.SetWindowPos(
                    window,
                    wintypes.HWND(-1),
                    22,
                    54,
                    width,
                    height,
                    0x0010 | 0x0040,
                )
                user32.InvalidateRect(window, None, True)
                user32.SetTimer(window, 1, self._visible_ms, None)
                return 0
            if message == 0x0113:
                user32.KillTimer(window, 1)
                user32.ShowWindow(window, 0)
                return 0
            if message == 0x000F:
                paint = PaintStruct()
                device = user32.BeginPaint(window, ctypes.byref(paint))
                rectangle = wintypes.RECT()
                user32.GetClientRect(window, ctypes.byref(rectangle))
                user32.FillRect(device, ctypes.byref(rectangle), background)
                gdi32.SetBkMode(device, 1)
                gdi32.SetTextColor(device, 0x00F2F2F2)
                rectangle.left += 16
                rectangle.top += 12
                rectangle.right -= 16
                rectangle.bottom -= 12
                user32.DrawTextW(
                    device,
                    current_text,
                    -1,
                    ctypes.byref(rectangle),
                    0x0000 | 0x0004 | 0x0800,
                )
                user32.EndPaint(window, ctypes.byref(paint))
                return 0
            if message == 0x0014:
                return 1
            if message == 0x0010:
                user32.DestroyWindow(window)
                return 0
            if message == 0x0002:
                user32.PostQuitMessage(0)
                return 0
            return int(
                user32.DefWindowProcW(
                    window,
                    message,
                    word_parameter,
                    long_parameter,
                )
            )

        window_class = WindowClass(
            style=0,
            window_procedure=window_procedure,
            class_extra=0,
            window_extra=0,
            instance=module,
            icon=None,
            cursor=None,
            background=background,
            menu_name=None,
            class_name=class_name,
        )
        atom = 0
        window: int | None = None
        try:
            atom = user32.RegisterClassW(ctypes.byref(window_class))
            if not atom:
                raise OSError(ctypes.get_last_error(), "could not register overlay window")
            window = user32.CreateWindowExW(
                0x00000008 | 0x00000020 | 0x00000080 | 0x00080000 | 0x08000000,
                class_name,
                "Shadowbane zone search",
                0x80000000,
                22,
                54,
                520,
                82,
                None,
                None,
                module,
                None,
            )
            if not window:
                raise OSError(ctypes.get_last_error(), "could not create overlay window")
            self._window_handle = int(window)
            if not user32.SetLayeredWindowAttributes(window, 0, 224, 0x00000002):
                raise OSError(ctypes.get_last_error(), "could not configure overlay opacity")
            self._ready.set()
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
        finally:
            self._window_handle = None
            if window and user32.IsWindow(window):
                user32.DestroyWindow(window)
            if atom:
                user32.UnregisterClassW(class_name, module)
            if background:
                gdi32.DeleteObject(background)
