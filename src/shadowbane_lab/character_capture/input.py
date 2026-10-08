"""Foreground-game-only Windows input observation, with no input injection."""

from __future__ import annotations

import ctypes
import queue
import threading
import time
from ctypes import wintypes


class WindowsGameInput:
    def __init__(self, pid, creation):
        self.pid, self.creation = pid, creation
        self.events = queue.Queue(maxsize=8192)
        self.enabled = threading.Event()
        self.ready = threading.Event()
        self.thread = None
        self.thread_id = 0
        self.error = None
        self.dropped = 0
        self.last_move = 0

    def start(self):
        self.thread = threading.Thread(target=self._run, name="game-input-observer", daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError("Windows input observer did not start.")
        if self.error:
            raise RuntimeError(self.error)

    def stop(self):
        self.enabled.clear()
        if self.thread_id:
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.PostThreadMessageW.argtypes = (
                wintypes.DWORD,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            )
            user.PostThreadMessageW(self.thread_id, 0x12, 0, 0)
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise RuntimeError("Windows input observer did not stop.")

    def _put(self, payload):
        try:
            self.events.put_nowait((time.monotonic_ns(), payload))
        except queue.Full:
            self.dropped += 1

    def _run(self):
        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        class Keyboard(ctypes.Structure):
            _fields_ = [
                ("vk", wintypes.DWORD),
                ("scan", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("extra", ctypes.c_size_t),
            ]

        class Mouse(ctypes.Structure):
            _fields_ = [
                ("point", wintypes.POINT),
                ("data", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("extra", ctypes.c_size_t),
            ]

        user.SetWindowsHookExW.argtypes = (
            ctypes.c_int,
            callback_type,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        )
        user.SetWindowsHookExW.restype = wintypes.HANDLE
        user.CallNextHookEx.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user.CallNextHookEx.restype = ctypes.c_ssize_t
        user.UnhookWindowsHookEx.argtypes = (wintypes.HANDLE,)
        user.GetForegroundWindow.restype = wintypes.HWND
        user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        user.ScreenToClient.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
        user.GetMessageW.argtypes = (
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        )
        user.PeekMessageW.argtypes = (*user.GetMessageW.argtypes, wintypes.UINT)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            *([ctypes.POINTER(wintypes.FILETIME)] * 4),
        )
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        hooks, handle = [], None
        try:
            handle = kernel.OpenProcess(0x1000 | 0x100000, False, self.pid)
            times = [wintypes.FILETIME() for _ in range(4)]
            if not handle or not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                raise OSError("Cannot bind input to the game process lifetime.")
            created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            if created != self.creation:
                raise OSError("Input process lifetime differs from the character.")

            def window():
                if not self.enabled.is_set() or kernel.WaitForSingleObject(handle, 0) != 0x102:
                    return None
                hwnd = user.GetForegroundWindow()
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                return hwnd if hwnd and pid.value == self.pid else None

            @callback_type
            def keyboard(code, message, data):
                try:
                    if code >= 0 and window() and message in (0x100, 0x101, 0x104, 0x105):
                        value = ctypes.cast(data, ctypes.POINTER(Keyboard)).contents
                        self._put(
                            {
                                "device": "keyboard",
                                "vk": value.vk,
                                "scan": value.scan,
                                "edge": "up" if message in (0x101, 0x105) else "down",
                                "injected": bool(value.flags & 0x10),
                                "extended": bool(value.flags & 1),
                            }
                        )
                except Exception as exc:
                    self.error = str(exc)
                    self.enabled.clear()
                return user.CallNextHookEx(None, code, message, data)

            @callback_type
            def mouse(code, message, data):
                try:
                    hwnd = window() if code >= 0 else None
                    now = time.monotonic_ns()
                    if hwnd and (message != 0x200 or now - self.last_move >= 50_000_000):
                        value = ctypes.cast(data, ctypes.POINTER(Mouse)).contents
                        point = wintypes.POINT(value.point.x, value.point.y)
                        if user.ScreenToClient(hwnd, ctypes.byref(point)):
                            self._put(
                                {
                                    "device": "mouse",
                                    "message": message,
                                    "x": point.x,
                                    "y": point.y,
                                    "data": value.data,
                                    "injected": bool(value.flags & 1),
                                }
                            )
                            if message == 0x200:
                                self.last_move = now
                except Exception as exc:
                    self.error = str(exc)
                    self.enabled.clear()
                return user.CallNextHookEx(None, code, message, data)

            msg = wintypes.MSG()
            user.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
            self.thread_id = kernel.GetCurrentThreadId()
            module = kernel.GetModuleHandleW(None)
            for kind, callback in ((13, keyboard), (14, mouse)):
                hook = user.SetWindowsHookExW(kind, callback, module, 0)
                if not hook:
                    raise OSError(ctypes.get_last_error(), "Could not install input observer.")
                hooks.append(hook)
            self.ready.set()
            while True:
                result = user.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0:
                    break
                if result == -1:
                    raise OSError("Input observer message loop failed.")
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.enabled.clear()
            for hook in hooks:
                user.UnhookWindowsHookEx(hook)
            if handle:
                kernel.CloseHandle(handle)
            self.ready.set()
