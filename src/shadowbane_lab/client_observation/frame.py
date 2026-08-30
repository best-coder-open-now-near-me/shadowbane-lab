"""Dependency-light RGB frames and optional PyAutoGUI screen capture."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol, runtime_checkable

from shadowbane_lab.client_input import WindowBounds


@dataclass(frozen=True, slots=True)
class RgbFrame:
    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        if isinstance(self.width, bool) or not isinstance(self.width, int) or self.width <= 0:
            raise ValueError("frame width must be a positive integer")
        if isinstance(self.height, bool) or not isinstance(self.height, int) or self.height <= 0:
            raise ValueError("frame height must be a positive integer")
        if not isinstance(self.pixels, bytes):
            raise ValueError("frame pixels must be bytes")
        if len(self.pixels) != self.width * self.height * 3:
            raise ValueError("frame pixel byte count does not match RGB dimensions")

    def rgb_at(self, x: int, y: int) -> tuple[int, int, int]:
        if not 0 <= x < self.width or not 0 <= y < self.height:
            raise ValueError("pixel coordinates are outside the frame")
        offset = (y * self.width + x) * 3
        return self.pixels[offset], self.pixels[offset + 1], self.pixels[offset + 2]


@runtime_checkable
class FrameCapture(Protocol):
    def capture(self, bounds: WindowBounds) -> RgbFrame: ...


class StaticFrameCapture:
    """Returns a deterministic frame without touching the desktop."""

    def __init__(self, frame: RgbFrame) -> None:
        if not isinstance(frame, RgbFrame):
            raise ValueError("frame must be RgbFrame")
        self.frame = frame
        self.capture_count = 0
        self.bounds: list[WindowBounds] = []

    def capture(self, bounds: WindowBounds) -> RgbFrame:
        if not isinstance(bounds, WindowBounds):
            raise ValueError("bounds must be WindowBounds")
        self.capture_count += 1
        self.bounds.append(bounds)
        return self.frame


class PyAutoGuiFrameCapture:
    """Captures only an already-guarded client rectangle and never sends input."""

    def __init__(self, pyautogui_module: Any | None = None) -> None:
        module = pyautogui_module
        if module is None:
            try:
                module = import_module("pyautogui")
            except ImportError as exc:
                raise RuntimeError(
                    "PyAutoGUI is not installed; install shadowbane-lab[client]"
                ) from exc
        self._pyautogui = module

    def capture(self, bounds: WindowBounds) -> RgbFrame:
        if not isinstance(bounds, WindowBounds):
            raise ValueError("bounds must be WindowBounds")
        image = self._pyautogui.screenshot(
            region=(bounds.left, bounds.top, bounds.width, bounds.height)
        )
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        return RgbFrame(width=width, height=height, pixels=rgb_image.tobytes())
