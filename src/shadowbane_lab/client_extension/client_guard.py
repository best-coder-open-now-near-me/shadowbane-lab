"""Exact client admission for native actions, independent of screen calibration."""
from __future__ import annotations

import ntpath
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_input.window import WindowGuardError, WindowInspector, WindowSnapshot


@runtime_checkable
class NativeClientTarget(Protocol):
    def require_target(self) -> WindowSnapshot: ...


class NativeClientWindowSelector:
    """Inspect the current native client without retaining a service-wide binding.

    Long-lived listeners may admit different clients. Each admitted operation must
    retain its own captured identity, independently of this selector.
    """

    def __init__(self, inspector: WindowInspector) -> None:
        if not isinstance(inspector, WindowInspector):
            raise ValueError("inspector must implement WindowInspector")
        self._inspector = inspector

    def require_target(self) -> WindowSnapshot:
        snapshot = self._inspector.inspect()
        if snapshot is None or not snapshot.is_foreground or not snapshot.is_visible:
            raise WindowGuardError("native client is not foreground and visible")
        identity = (snapshot.process_id, snapshot.process_started_at_100ns, snapshot.window_handle)
        if any(type(part) is not int or part <= 0 for part in identity):
            raise WindowGuardError("native client process/window identity is unavailable")
        path = snapshot.executable_path
        if not path or not ntpath.isabs(path):
            raise WindowGuardError("native client executable path is unavailable")
        path = ntpath.normcase(ntpath.normpath(path))
        if (snapshot.executable_name.casefold() != "sb.exe"
                or ntpath.basename(path) != "sb.exe"):
            raise WindowGuardError("foreground executable is not the native client")
        return snapshot


class NativeClientIdentityGuard:
    """Capture one foreground client lifetime and retain it across native work.

    Native readers validate the executable build and character session. This guard
    binds their containing process/window; pixels, DPI, title and input mappings
    cannot establish or invalidate that identity.
    """

    def __init__(
        self,
        inspector: WindowInspector,
        *,
        expected_process_id: int | None = None,
        expected_process_started_at_100ns: int | None = None,
        expected_window_handle: int | None = None,
        expected_executable_path: str | None = None,
    ) -> None:
        if not isinstance(inspector, WindowInspector):
            raise ValueError("inspector must implement WindowInspector")
        self._expected = (expected_process_id, expected_process_started_at_100ns,
                          expected_window_handle)
        for part in self._expected:
            if part is not None and (type(part) is not int or part <= 0):
                raise ValueError("expected native process/window identity must be positive")
        if expected_executable_path is not None and (
            not isinstance(expected_executable_path, str)
            or not ntpath.isabs(expected_executable_path)
        ):
            raise ValueError("expected executable path must be absolute")
        self._expected_path = (None if expected_executable_path is None
                               else ntpath.normcase(ntpath.normpath(expected_executable_path)))
        self._selector = NativeClientWindowSelector(inspector)
        self._binding: tuple[int, int, int, str] | None = None

    def require_target(self) -> WindowSnapshot:
        snapshot = self._selector.require_target()
        identity = (snapshot.process_id, snapshot.process_started_at_100ns, snapshot.window_handle)
        path = ntpath.normcase(ntpath.normpath(snapshot.executable_path))
        if any(expected is not None and actual != expected
               for actual, expected in zip(identity, self._expected, strict=True)):
            raise WindowGuardError("native client process/window identity changed")
        if self._expected_path is not None and path != self._expected_path:
            raise WindowGuardError("native client executable path changed")
        binding = (*identity, path)
        if self._binding is not None and binding != self._binding:
            raise WindowGuardError("captured native client lifetime or window changed")
        self._binding = binding
        return snapshot
