"""Dependency-light file-tail and screenshot diagnostic collectors."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from io import BytesIO
from typing import Any

from shadowbane_lab.integrity import is_reparse_point

from .model import DiagnosticError, FileChannel


@dataclass(frozen=True, slots=True)
class FileChunk:
    channel_id: str
    captured_monotonic_ns: int
    source_generation: int
    source_offset: int
    payload: bytes
    initial_context: bool
    rotated_or_truncated: bool
    dropped_bytes: int = 0


class TailFileCollector:
    """Captures appended bytes with bounded initial context and rotation accounting."""

    def __init__(self, channel: FileChannel) -> None:
        self.channel = channel
        self._position: int | None = None
        self._generation = 0
        self._captured_bytes = 0
        self._exhausted = False
        self._source_seen = False

    @property
    def source_seen(self) -> bool:
        return self._source_seen

    def poll(self, monotonic_ns: int) -> tuple[FileChunk, ...]:
        if self._exhausted or not self.channel.path.exists():
            return ()
        path = self.channel.path
        self._source_seen = True
        if not path.is_file() or is_reparse_point(path):
            raise DiagnosticError(f"tail source must be a regular file: {path}")
        size = path.stat().st_size
        initial = self._position is None
        rotated = False
        if initial:
            self._position = max(0, size - self.channel.initial_tail_bytes)
        elif size < self._position:
            self._generation += 1
            self._position = 0
            rotated = True
        assert self._position is not None
        available = size - self._position
        if available <= 0:
            return ()
        remaining = self.channel.maximum_bytes - self._captured_bytes
        read_length = min(available, remaining)
        with path.open("rb") as stream:
            stream.seek(self._position)
            payload = stream.read(read_length)
        if len(payload) != read_length:
            raise DiagnosticError(f"tail source changed during read: {path}")
        source_offset = self._position
        self._position += len(payload)
        self._captured_bytes += len(payload)
        dropped = max(0, available - len(payload))
        if dropped:
            self._exhausted = True
        return (
            FileChunk(
                channel_id=self.channel.channel_id,
                captured_monotonic_ns=monotonic_ns,
                source_generation=self._generation,
                source_offset=source_offset,
                payload=payload,
                initial_context=initial,
                rotated_or_truncated=rotated,
                dropped_bytes=dropped,
            ),
        )


@dataclass(frozen=True, slots=True)
class ScreenshotCapture:
    captured_monotonic_ns: int
    png_bytes: bytes
    width: int
    height: int


class ScreenshotCollector:
    """Captures a configured desktop rectangle without sending input."""

    def __init__(
        self,
        region: tuple[int, int, int, int],
        interval_seconds: float,
        *,
        pyautogui_module: Any | None = None,
    ) -> None:
        module = pyautogui_module
        if module is None:
            try:
                module = import_module("pyautogui")
            except ImportError as exc:
                raise DiagnosticError(
                    "screenshot capture requires shadowbane-lab[client]"
                ) from exc
        self._pyautogui = module
        self._region = region
        self._interval_ns = int(interval_seconds * 1_000_000_000)
        self._next_capture_ns: int | None = None

    def poll(self, monotonic_ns: int) -> tuple[ScreenshotCapture, ...]:
        if self._next_capture_ns is not None and monotonic_ns < self._next_capture_ns:
            return ()
        image = self._pyautogui.screenshot(region=self._region).convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=False)
        width, height = image.size
        self._next_capture_ns = monotonic_ns + self._interval_ns
        return (ScreenshotCapture(monotonic_ns, buffer.getvalue(), width, height),)


__all__ = [
    "FileChunk",
    "ScreenshotCapture",
    "ScreenshotCollector",
    "TailFileCollector",
]
