"""Typed absolute-input backends, including an opt-in PyAutoGUI backend."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol, runtime_checkable

from shadowbane_lab.client_input.model import AbsolutePoint, MouseButton


@dataclass(frozen=True, slots=True)
class ClickInvocation:
    point: AbsolutePoint
    button: MouseButton
    clicks: int = 1


@dataclass(frozen=True, slots=True)
class DragInvocation:
    start: AbsolutePoint
    end: AbsolutePoint
    duration_ms: int
    button: MouseButton


@dataclass(frozen=True, slots=True)
class KeyPressInvocation:
    key: str


@dataclass(frozen=True, slots=True)
class HotkeyInvocation:
    keys: tuple[str, ...]


InputInvocation = ClickInvocation | DragInvocation | KeyPressInvocation | HotkeyInvocation


@runtime_checkable
class InputBackend(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def produces_desktop_input(self) -> bool: ...

    def click(self, invocation: ClickInvocation) -> None: ...

    def drag(self, invocation: DragInvocation) -> None: ...

    def key_press(self, invocation: KeyPressInvocation) -> None: ...

    def hotkey(self, invocation: HotkeyInvocation) -> None: ...


class RecordingInputBackend:
    """Records resolved input without importing or calling desktop automation."""

    @property
    def name(self) -> str:
        return "recording-input"

    @property
    def produces_desktop_input(self) -> bool:
        return False

    def __init__(self) -> None:
        self._invocations: list[InputInvocation] = []

    @property
    def invocations(self) -> tuple[InputInvocation, ...]:
        return tuple(self._invocations)

    def click(self, invocation: ClickInvocation) -> None:
        self._invocations.append(invocation)

    def drag(self, invocation: DragInvocation) -> None:
        self._invocations.append(invocation)

    def key_press(self, invocation: KeyPressInvocation) -> None:
        self._invocations.append(invocation)

    def hotkey(self, invocation: HotkeyInvocation) -> None:
        self._invocations.append(invocation)


class PyAutoGuiBackend:
    """Sends already-guarded absolute input through PyAutoGUI."""

    def __init__(self, pyautogui_module: Any | None = None) -> None:
        module = pyautogui_module
        if module is None:
            try:
                module = import_module("pyautogui")
            except ImportError as exc:
                raise RuntimeError(
                    "PyAutoGUI is not installed; install shadowbane-lab[client]"
                ) from exc
        module.FAILSAFE = True
        self._pyautogui = module

    @property
    def name(self) -> str:
        return "pyautogui"

    @property
    def produces_desktop_input(self) -> bool:
        return True

    def click(self, invocation: ClickInvocation) -> None:
        self._pyautogui.click(
            x=invocation.point.x,
            y=invocation.point.y,
            clicks=invocation.clicks,
            button=invocation.button.value,
        )

    def drag(self, invocation: DragInvocation) -> None:
        self._pyautogui.moveTo(invocation.start.x, invocation.start.y)
        self._pyautogui.dragTo(
            invocation.end.x,
            invocation.end.y,
            duration=invocation.duration_ms / 1000.0,
            button=invocation.button.value,
        )

    def key_press(self, invocation: KeyPressInvocation) -> None:
        self._pyautogui.press(invocation.key)

    def hotkey(self, invocation: HotkeyInvocation) -> None:
        self._pyautogui.hotkey(*invocation.keys)
