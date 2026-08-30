"""Emergency-stop signals for guarded desktop input."""

from __future__ import annotations

import os
import threading
from time import sleep
from typing import Protocol, runtime_checkable


@runtime_checkable
class StopSignal(Protocol):
    def is_set(self) -> bool: ...


class EventEmergencyStop:
    """Thread-safe, one-way stop signal suitable for UI wiring and tests."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def trip(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


class AnyStopSignal:
    """Expose the union of multiple independent stop signals."""

    def __init__(self, *signals: StopSignal) -> None:
        if not signals:
            raise ValueError("at least one stop signal is required")
        if any(not isinstance(signal, StopSignal) for signal in signals):
            raise ValueError("signals must implement StopSignal")
        self._signals = signals

    def is_set(self) -> bool:
        return any(signal.is_set() for signal in self._signals)


class WindowsHotkeyEmergencyStop(EventEmergencyStop):
    """Trips when Ctrl+Shift+F12 is held; call ``start`` before live dispatch."""

    _DEFAULT_KEYS = (0x11, 0x10, 0x7B)  # Ctrl, Shift, F12

    def __init__(self, poll_interval_seconds: float = 0.05) -> None:
        super().__init__()
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._poll_interval_seconds = poll_interval_seconds
        self._closed = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("WindowsHotkeyEmergencyStop requires Windows")
        if self._thread is not None:
            raise RuntimeError("emergency-stop listener has already been started")
        self._thread = threading.Thread(
            target=self._listen,
            name="shadowbane-input-emergency-stop",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self._closed.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._poll_interval_seconds * 4))

    def __enter__(self) -> WindowsHotkeyEmergencyStop:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _listen(self) -> None:
        import ctypes

        get_async_key_state = ctypes.windll.user32.GetAsyncKeyState
        while not self._closed.is_set() and not self.is_set():
            if all(get_async_key_state(key) & 0x8000 for key in self._DEFAULT_KEYS):
                self.trip()
                return
            sleep(self._poll_interval_seconds)
