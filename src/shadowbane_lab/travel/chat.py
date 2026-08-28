"""Foreground-scoped keyboard bridge for local Shadowbane control commands."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass

from shadowbane_lab.client_input import ForegroundWindowGuard, WindowGuardError


@dataclass(frozen=True, slots=True)
class GoChatCommandUpdate:
    """State change produced while assembling one in-game chat line."""

    interaction_started: bool = False
    submitted_command: str | None = None


class GoChatCommandAssembler:
    """Retain only a supported Shadowbane Lab control-command line."""

    _DIRECT_COMMAND_ALIASES = {
        "/runegate": "/go runegate",
    }

    def __init__(self, *, maximum_length: int = 128) -> None:
        if isinstance(maximum_length, bool) or not isinstance(maximum_length, int):
            raise ValueError("maximum_length must be an integer")
        if maximum_length < 3:
            raise ValueError("maximum_length must be at least 3")
        self._maximum_length = maximum_length
        self._line_active = False
        self._candidate: str | None = None

    @property
    def line_active(self) -> bool:
        return self._line_active

    @property
    def retained_text(self) -> str | None:
        return self._candidate

    def handle_enter(self) -> GoChatCommandUpdate:
        if not self._line_active:
            self._line_active = True
            self._candidate = ""
            return GoChatCommandUpdate(interaction_started=True)

        command = self._submitted_control_command(self._candidate)
        self.reset()
        return GoChatCommandUpdate(submitted_command=command)

    def handle_character(self, character: str) -> GoChatCommandUpdate:
        if not isinstance(character, str) or len(character) != 1:
            raise ValueError("character must contain exactly one character")
        interaction_started = False
        if not self._line_active:
            if character != "/":
                return GoChatCommandUpdate()
            self._line_active = True
            self._candidate = ""
            interaction_started = True

        if self._candidate is not None:
            candidate = self._candidate + character
            if (
                len(candidate) > self._maximum_length
                or not self._could_be_control_command(candidate)
            ):
                self._candidate = None
            else:
                self._candidate = candidate
        return GoChatCommandUpdate(interaction_started=interaction_started)

    def handle_backspace(self) -> GoChatCommandUpdate:
        if self._line_active and self._candidate:
            self._candidate = self._candidate[:-1]
        return GoChatCommandUpdate()

    def handle_escape(self) -> GoChatCommandUpdate:
        self.reset()
        return GoChatCommandUpdate()

    def reset(self) -> None:
        self._line_active = False
        self._candidate = None

    @staticmethod
    def _could_be_control_command(candidate: str) -> bool:
        normalized = candidate.casefold()
        if any(
            command.startswith(normalized)
            for command in (
                "/go",
                "/pve",
                "/stop",
                "/zone",
                *GoChatCommandAssembler._DIRECT_COMMAND_ALIASES,
            )
        ):
            return True
        if normalized.startswith("/go "):
            return True
        if normalized.startswith("/pve"):
            return not normalized.removeprefix("/pve").strip()
        if normalized.startswith("/stop"):
            return not normalized.removeprefix("/stop").strip()
        if normalized.startswith("/zone "):
            return True
        for alias in GoChatCommandAssembler._DIRECT_COMMAND_ALIASES:
            if normalized.startswith(alias):
                return not normalized.removeprefix(alias).strip()
        return False

    @staticmethod
    def _submitted_control_command(candidate: str | None) -> str | None:
        if candidate is None:
            return None
        normalized = candidate.casefold()
        alias = GoChatCommandAssembler._DIRECT_COMMAND_ALIASES.get(normalized.rstrip())
        if alias is not None:
            return alias
        if (
            normalized == "/go"
            or normalized.startswith("/go ")
            or normalized.rstrip() == "/pve"
            or normalized.rstrip() == "/stop"
            or normalized.rstrip() == "/zone"
            or normalized.startswith("/zone ")
        ):
            return candidate
        return None


@dataclass(frozen=True, slots=True)
class PhysicalPointerInteraction:
    """One non-injected physical pointer press observed over the game."""

    screen_x: int
    screen_y: int
    button: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.screen_x, "screen_x"),
            (self.screen_y, "screen_y"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
        if self.button not in {"left", "right", "middle", "x"}:
            raise ValueError("button must identify a supported physical pointer button")


class WindowsGoChatCommandListener:
    """Observe keyboard events only while the calibrated game owns foreground focus.

    The hook never suppresses or injects input. It keeps at most one possible ``/go``,
    ``/pve``, ``/stop``, or direct travel-alias command and immediately forgets ordinary
    chat and unrelated commands.
    """

    _WH_KEYBOARD_LL = 13
    _WH_MOUSE_LL = 14
    _WM_KEYDOWN = 0x0100
    _WM_SYSKEYDOWN = 0x0104
    _WM_LBUTTONDOWN = 0x0201
    _WM_RBUTTONDOWN = 0x0204
    _WM_MBUTTONDOWN = 0x0207
    _WM_XBUTTONDOWN = 0x020B
    _WM_QUIT = 0x0012
    _LLKHF_INJECTED = 0x10
    _LLMHF_INJECTED = 0x01
    _ERROR_ALREADY_EXISTS = 183
    _MUTEX_NAME = "Local\\ShadowbaneLabGoChatCommandListener"

    _VK_BACK = 0x08
    _VK_RETURN = 0x0D
    _VK_ESCAPE = 0x1B
    _VK_SHIFT = 0x10
    _VK_SPACE = 0x20
    _VK_NUMPAD0 = 0x60
    _VK_NUMPAD9 = 0x69
    _VK_SUBTRACT = 0x6D
    _VK_DECIMAL = 0x6E
    _VK_DIVIDE = 0x6F
    _VK_OEM_PLUS = 0xBB
    _VK_OEM_COMMA = 0xBC
    _VK_OEM_MINUS = 0xBD
    _VK_OEM_PERIOD = 0xBE
    _VK_OEM_2 = 0xBF

    def __init__(
        self,
        guard: ForegroundWindowGuard,
        *,
        on_command: Callable[[str], None],
        on_interaction: Callable[[], None] | None = None,
        on_pointer: Callable[[PhysicalPointerInteraction], None] | None = None,
    ) -> None:
        if not isinstance(guard, ForegroundWindowGuard):
            raise ValueError("guard must be ForegroundWindowGuard")
        if not callable(on_command):
            raise ValueError("on_command must be callable")
        if on_interaction is not None and not callable(on_interaction):
            raise ValueError("on_interaction must be callable when present")
        if on_pointer is not None and not callable(on_pointer):
            raise ValueError("on_pointer must be callable when present")
        self._guard = guard
        self._on_command = on_command
        self._on_interaction = on_interaction
        self._on_pointer = on_pointer
        self._assembler = GoChatCommandAssembler()
        self._closed = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._startup_error: BaseException | None = None
        self._mutex_handle: int | None = None

    def start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("WindowsGoChatCommandListener requires Windows")
        if self._thread is not None:
            raise RuntimeError("chat-command listener has already been started")
        self._acquire_single_instance()
        self._thread = threading.Thread(
            target=self._listen,
            name="shadowbane-chat-command-listener",
            daemon=True,
        )
        try:
            self._thread.start()
        except BaseException:
            self._release_single_instance()
            raise
        if not self._ready.wait(timeout=5.0):
            self.close()
            raise RuntimeError("chat-command listener did not initialize")
        if self._startup_error is not None:
            error = self._startup_error
            self.close()
            raise RuntimeError(f"chat-command listener failed: {error}")

    def close(self) -> None:
        self._closed.set()
        thread_id = self._thread_id
        if thread_id is not None and os.name == "nt":
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(thread_id, self._WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._release_single_instance()

    def __enter__(self) -> WindowsGoChatCommandListener:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _listen(self) -> None:
        import ctypes
        from ctypes import wintypes

        class KeyboardEvent(ctypes.Structure):
            _fields_ = (
                ("vk_code", wintypes.DWORD),
                ("scan_code", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("extra_info", ctypes.c_size_t),
            )

        class MouseEvent(ctypes.Structure):
            _fields_ = (
                ("point", wintypes.POINT),
                ("mouse_data", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("extra_info", ctypes.c_size_t),
            )

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.SetWindowsHookExW.argtypes = (
            ctypes.c_int,
            callback_type,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        )
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = (
            ctypes.c_void_p,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        user32.GetAsyncKeyState.restype = wintypes.SHORT
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        keyboard_hook: int | None = None
        mouse_hook: int | None = None

        @callback_type
        def keyboard_callback(code: int, message: int, event_pointer: int) -> int:
            if code >= 0 and message in (self._WM_KEYDOWN, self._WM_SYSKEYDOWN):
                event = ctypes.cast(
                    event_pointer,
                    ctypes.POINTER(KeyboardEvent),
                ).contents
                if not event.flags & self._LLKHF_INJECTED:
                    try:
                        self._handle_key(
                            int(event.vk_code),
                            shift_down=bool(
                                user32.GetAsyncKeyState(self._VK_SHIFT) & 0x8000
                            ),
                        )
                    except Exception:
                        self._assembler.reset()
            return int(
                user32.CallNextHookEx(
                    keyboard_hook,
                    code,
                    message,
                    event_pointer,
                )
            )

        @callback_type
        def mouse_callback(code: int, message: int, event_pointer: int) -> int:
            if code >= 0 and message in (
                self._WM_LBUTTONDOWN,
                self._WM_RBUTTONDOWN,
                self._WM_MBUTTONDOWN,
                self._WM_XBUTTONDOWN,
            ):
                event = ctypes.cast(
                    event_pointer,
                    ctypes.POINTER(MouseEvent),
                ).contents
                if not event.flags & self._LLMHF_INJECTED:
                    try:
                        self._handle_pointer_interaction(
                            PhysicalPointerInteraction(
                                screen_x=int(event.point.x),
                                screen_y=int(event.point.y),
                                button={
                                    self._WM_LBUTTONDOWN: "left",
                                    self._WM_RBUTTONDOWN: "right",
                                    self._WM_MBUTTONDOWN: "middle",
                                    self._WM_XBUTTONDOWN: "x",
                                }[int(message)],
                            )
                        )
                    except Exception:
                        self._assembler.reset()
            return int(
                user32.CallNextHookEx(
                    mouse_hook,
                    code,
                    message,
                    event_pointer,
                )
            )

        try:
            self._thread_id = int(kernel32.GetCurrentThreadId())
            module = kernel32.GetModuleHandleW(None)
            keyboard_hook = user32.SetWindowsHookExW(
                self._WH_KEYBOARD_LL,
                keyboard_callback,
                module,
                0,
            )
            if not keyboard_hook:
                raise OSError(ctypes.get_last_error(), "keyboard SetWindowsHookExW failed")
            mouse_hook = user32.SetWindowsHookExW(
                self._WH_MOUSE_LL,
                mouse_callback,
                module,
                0,
            )
            if not mouse_hook:
                raise OSError(ctypes.get_last_error(), "mouse SetWindowsHookExW failed")
            self._ready.set()
            message = wintypes.MSG()
            while not self._closed.is_set():
                status = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if status == 0:
                    break
                if status == -1:
                    raise OSError(ctypes.get_last_error(), "GetMessageW failed")
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
        finally:
            if mouse_hook:
                user32.UnhookWindowsHookEx(mouse_hook)
            if keyboard_hook:
                user32.UnhookWindowsHookEx(keyboard_hook)

    def _acquire_single_instance(self) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.CreateMutexW(None, True, self._MUTEX_NAME)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
        if ctypes.get_last_error() == self._ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            raise RuntimeError("another Shadowbane chat-command listener is already running")
        self._mutex_handle = int(handle)

    def _release_single_instance(self) -> None:
        handle = self._mutex_handle
        self._mutex_handle = None
        if handle is None or os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        native_handle = wintypes.HANDLE(handle)
        kernel32.ReleaseMutex(native_handle)
        kernel32.CloseHandle(native_handle)

    def _handle_key(self, virtual_key: int, *, shift_down: bool) -> None:
        try:
            self._guard.require_target()
        except WindowGuardError:
            self._assembler.reset()
            return

        if virtual_key == self._VK_RETURN:
            update = self._assembler.handle_enter()
        elif virtual_key == self._VK_ESCAPE:
            update = self._assembler.handle_escape()
        elif virtual_key == self._VK_BACK:
            update = self._assembler.handle_backspace()
        else:
            character = self._character_for(virtual_key, shift_down=shift_down)
            if character is None:
                return
            update = self._assembler.handle_character(character)

        if update.interaction_started and self._on_interaction is not None:
            self._on_interaction()
        if update.submitted_command is not None:
            self._on_command(update.submitted_command)

    def _handle_pointer_interaction(
        self,
        interaction: PhysicalPointerInteraction | None = None,
    ) -> None:
        try:
            self._guard.require_target()
        except WindowGuardError:
            self._assembler.reset()
            return
        self._assembler.reset()
        if self._on_interaction is not None:
            self._on_interaction()
        if interaction is not None and self._on_pointer is not None:
            self._on_pointer(interaction)

    @classmethod
    def _character_for(cls, virtual_key: int, *, shift_down: bool) -> str | None:
        if 0x30 <= virtual_key <= 0x39:
            digit = virtual_key - 0x30
            return ")!@#$%^&*("[digit] if shift_down else str(digit)
        if 0x41 <= virtual_key <= 0x5A:
            return chr(virtual_key).lower()
        if cls._VK_NUMPAD0 <= virtual_key <= cls._VK_NUMPAD9:
            return str(virtual_key - cls._VK_NUMPAD0)
        if virtual_key == cls._VK_SPACE:
            return " "
        if virtual_key == cls._VK_SUBTRACT:
            return "-"
        if virtual_key == cls._VK_OEM_MINUS:
            return "_" if shift_down else "-"
        if virtual_key == cls._VK_DECIMAL:
            return "."
        if virtual_key == cls._VK_OEM_PERIOD:
            return ">" if shift_down else "."
        if virtual_key == cls._VK_OEM_COMMA:
            return "<" if shift_down else ","
        if virtual_key in (cls._VK_DIVIDE, cls._VK_OEM_2):
            return "?" if shift_down else "/"
        if virtual_key == cls._VK_OEM_PLUS:
            return "+" if shift_down else "="
        return None
