"""Single-purpose tagged Windows clicks for live acceptance actions."""

from __future__ import annotations

import os
from importlib import import_module
from typing import Any, Protocol, runtime_checkable

from .backend import ClickInvocation, DragInvocation, HotkeyInvocation, KeyPressInvocation
from .model import MouseButton

WORLD_MAP_ACTION_TEST_INPUT_TAG = 0x53424C54


@runtime_checkable
class TaggedPointerButtonSender(Protocol):
    def click(self, button: MouseButton, *, tag: int) -> None: ...


class WindowsTaggedPointerButtonSender:
    """Emit one button transition pair with a stable low-level-hook marker."""

    _INPUT_MOUSE = 0
    _BUTTON_FLAGS = {
        MouseButton.LEFT: (0x0002, 0x0004),
        MouseButton.RIGHT: (0x0008, 0x0010),
    }

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("tagged pointer input requires Windows")
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes

        class MouseInput(ctypes.Structure):
            _fields_ = (
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouse_data", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("extra_info", ctypes.c_size_t),
            )

        class InputPayload(ctypes.Union):
            _fields_ = (("mouse", MouseInput),)

        class Input(ctypes.Structure):
            _anonymous_ = ("payload",)
            _fields_ = (("type", wintypes.DWORD), ("payload", InputPayload))

        self._mouse_input = MouseInput
        self._input = Input
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = (
            wintypes.UINT,
            ctypes.POINTER(Input),
            ctypes.c_int,
        )
        self._user32.SendInput.restype = wintypes.UINT

    def click(self, button: MouseButton, *, tag: int) -> None:
        if button not in self._BUTTON_FLAGS:
            raise ValueError("tagged test input supports only left and right clicks")
        if isinstance(tag, bool) or not isinstance(tag, int) or not 0 < tag <= 0xFFFFFFFF:
            raise ValueError("tag must be a positive unsigned 32-bit integer")
        down, up = self._BUTTON_FLAGS[button]
        inputs = (self._input * 2)(
            self._input(
                type=self._INPUT_MOUSE,
                mouse=self._mouse_input(flags=down, extra_info=tag),
            ),
            self._input(
                type=self._INPUT_MOUSE,
                mouse=self._mouse_input(flags=up, extra_info=tag),
            ),
        )
        self._ctypes.set_last_error(0)
        sent = self._user32.SendInput(2, inputs, self._ctypes.sizeof(self._input))
        if sent != 2:
            error = self._ctypes.get_last_error() or 31  # ERROR_GEN_FAILURE
            release = self._input(
                type=self._INPUT_MOUSE,
                mouse=self._mouse_input(flags=up, extra_info=tag),
            )
            release_sent = self._user32.SendInput(
                1,
                self._ctypes.byref(release),
                self._ctypes.sizeof(self._input),
            )
            if release_sent != 1:
                raise OSError(
                    error,
                    f"SendInput inserted {sent} of 2 events and button-up cleanup failed",
                )
            raise OSError(error, f"SendInput inserted {sent} of 2 events")


class WorldMapTestInputBackend:
    """Move safely through PyAutoGUI, then emit only a tagged map-test click."""

    def __init__(
        self,
        pyautogui_module: Any | None = None,
        sender: TaggedPointerButtonSender | None = None,
    ) -> None:
        module = pyautogui_module
        if module is None:
            try:
                module = import_module("pyautogui")
            except ImportError as exc:
                raise RuntimeError(
                    "PyAutoGUI is not installed; install shadowbane-lab[client]"
                ) from exc
        module.FAILSAFE = True
        resolved_sender = sender if sender is not None else WindowsTaggedPointerButtonSender()
        if not isinstance(resolved_sender, TaggedPointerButtonSender):
            raise ValueError("sender must implement TaggedPointerButtonSender")
        self._pyautogui = module
        self._sender = resolved_sender

    @property
    def name(self) -> str:
        return "world-map-test-input"

    @property
    def produces_desktop_input(self) -> bool:
        return True

    def click(self, invocation: ClickInvocation) -> None:
        if not isinstance(invocation, ClickInvocation):
            raise ValueError("invocation must be ClickInvocation")
        if invocation.button is not MouseButton.RIGHT or invocation.clicks != 1:
            raise ValueError("world-map acceptance input requires one right click")
        self._pyautogui.moveTo(invocation.point.x, invocation.point.y)
        self._sender.click(
            invocation.button,
            tag=WORLD_MAP_ACTION_TEST_INPUT_TAG,
        )

    def drag(self, invocation: DragInvocation) -> None:
        raise RuntimeError("world-map acceptance input cannot dispatch drags")

    def key_press(self, invocation: KeyPressInvocation) -> None:
        raise RuntimeError("world-map acceptance input cannot dispatch key presses")

    def hotkey(self, invocation: HotkeyInvocation) -> None:
        raise RuntimeError("world-map acceptance input cannot dispatch hotkeys")


__all__ = [
    "WORLD_MAP_ACTION_TEST_INPUT_TAG",
    "TaggedPointerButtonSender",
    "WindowsTaggedPointerButtonSender",
    "WorldMapTestInputBackend",
]
