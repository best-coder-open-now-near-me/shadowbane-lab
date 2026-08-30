"""Selective world-map pointer capture layered over the responsive input listener."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite

from shadowbane_lab.client_input import ForegroundWindowGuard, WindowGuardError
from shadowbane_lab.client_observation import (
    NativeWorldMapError,
    NativeWorldMapObservation,
    NativeWorldMapProfile,
    load_bundled_native_world_map_profile,
    open_windows_native_world_map_reader,
)
from shadowbane_lab.travel.chat import (
    PhysicalPointerInteraction,
    _PhysicalKeyboardInteraction,
)
from shadowbane_lab.travel.chat import (
    WindowsGoChatCommandListener as _BaseWindowsGoChatCommandListener,
)


@dataclass(frozen=True, slots=True)
class WorldMapPointerInteraction(PhysicalPointerInteraction):
    """A captured map selection normalized into client-local map pixels.

    ``screen_x`` and ``screen_y`` intentionally retain the legacy field names used by
    the travel command queue, but contain client-local coordinates suitable for the
    native ``ArcWorldMapHud`` projection. The original desktop coordinates and actual
    physical button remain available for diagnostics.

    ``button`` is always ``"right"`` because the existing travel queue uses that value
    as its map-destination routing discriminator. ``physical_button`` records whether
    the player actually selected the map with the left or right mouse button.
    """

    physical_button: str
    desktop_screen_x: int
    desktop_screen_y: int
    process_id: int
    window_handle: int
    lt: float
    lg: float
    snapshot_token: str

    def __post_init__(self) -> None:
        PhysicalPointerInteraction.__post_init__(self)
        if self.button != "right":
            raise ValueError("captured world-map selections must use right-button routing")
        if self.physical_button not in {"left", "right"}:
            raise ValueError("physical_button must be left or right")
        for value, field_name in (
            (self.desktop_screen_x, "desktop_screen_x"),
            (self.desktop_screen_y, "desktop_screen_y"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
        for value, field_name in (
            (self.process_id, "process_id"),
            (self.window_handle, "window_handle"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        for value, field_name in ((self.lt, "lt"), (self.lg, "lg")):
            if not isfinite(value):
                raise ValueError(f"{field_name} must be finite")
        if not isinstance(self.snapshot_token, str) or not self.snapshot_token:
            raise ValueError("snapshot_token must be non-empty")


@dataclass(frozen=True, slots=True)
class _WorldMapCaptureSnapshot:
    """Fresh immutable state read away from the latency-sensitive Win32 hook."""

    observation: NativeWorldMapObservation
    observed_at: float
    client_left: int
    client_top: int
    process_id: int
    window_handle: int

    def __post_init__(self) -> None:
        if not isinstance(self.observation, NativeWorldMapObservation):
            raise ValueError("observation must be NativeWorldMapObservation")
        if not isfinite(self.observed_at) or self.observed_at < 0:
            raise ValueError("observed_at must be finite and non-negative")
        for value, field_name in (
            (self.client_left, "client_left"),
            (self.client_top, "client_top"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
        for value, field_name in (
            (self.process_id, "process_id"),
            (self.window_handle, "window_handle"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")


class WindowsGoChatCommandListener(_BaseWindowsGoChatCommandListener):
    """Responsive chat listener with fail-open, map-only selection capture.

    Native map state is sampled on a background thread. The low-level mouse hook performs
    only a constant-time check against the newest immutable sample. It suppresses a physical
    left- or right-button press only when all of these remain true:

    * the calibrated client still owns the foreground window;
    * the sample is fresh and belongs to that exact window and process;
    * the native world map is open; and
    * the point resolves through the live map projection.

    This lets ordinary left-clicks on rendered zone emblems become travel destinations
    without reaching WonderBane first and mutating or closing the map. Every other pointer
    event passes through unchanged, including gameplay clicks, map chrome, stale/unknown
    map state, middle/X buttons, and clicks outside the projected world.
    """

    _WM_LBUTTONUP = 0x0202
    _WM_RBUTTONUP = 0x0205
    _WORLD_MAP_POLL_SECONDS = 0.05
    _WORLD_MAP_MAX_AGE_SECONDS = 0.25

    def __init__(
        self,
        guard: ForegroundWindowGuard,
        *,
        on_command: Callable[[str], None],
        on_interaction: Callable[[], None] | None = None,
        on_pointer: Callable[[PhysicalPointerInteraction], None] | None = None,
        world_map_profile: NativeWorldMapProfile | None = None,
    ) -> None:
        super().__init__(
            guard,
            on_command=on_command,
            on_interaction=on_interaction,
            on_pointer=on_pointer,
        )
        if world_map_profile is not None and not isinstance(
            world_map_profile, NativeWorldMapProfile
        ):
            raise ValueError("world_map_profile must be NativeWorldMapProfile or None")
        self._world_map_profile = world_map_profile
        self._world_map_thread: threading.Thread | None = None
        self._world_map_ready = threading.Event()
        self._world_map_capture: _WorldMapCaptureSnapshot | None = None
        self._suppress_left_button_up = False
        self._suppress_right_button_up = False
        self._world_map_observations = 0
        self._world_map_read_errors = 0
        self._world_map_capture_attempts = 0
        self._world_map_captured_clicks = 0
        self._world_map_captured_left_clicks = 0
        self._world_map_captured_right_clicks = 0
        self._world_map_capture_misses = 0
        self._suppressed_left_button_ups = 0
        self._suppressed_right_button_ups = 0
        self._last_world_map_error: str | None = None

    @property
    def is_alive(self) -> bool:
        map_listener_alive = self._on_pointer is None or bool(
            self._world_map_thread is not None and self._world_map_thread.is_alive()
        )
        return super().is_alive and map_listener_alive

    @property
    def diagnostics(self) -> dict[str, int | str | None]:
        diagnostics = dict(super().diagnostics)
        diagnostics.update(
            {
                "world_map_observations": self._world_map_observations,
                "world_map_read_errors": self._world_map_read_errors,
                "world_map_capture_attempts": self._world_map_capture_attempts,
                "world_map_captured_clicks": self._world_map_captured_clicks,
                "world_map_captured_left_clicks": self._world_map_captured_left_clicks,
                "world_map_captured_right_clicks": self._world_map_captured_right_clicks,
                "world_map_capture_misses": self._world_map_capture_misses,
                "suppressed_left_button_ups": self._suppressed_left_button_ups,
                "suppressed_right_button_ups": self._suppressed_right_button_ups,
                "last_world_map_error": self._last_world_map_error,
            }
        )
        return diagnostics

    def start(self) -> None:
        super().start()
        if self._on_pointer is None:
            return
        self._world_map_thread = threading.Thread(
            target=self._observe_world_map,
            name="shadowbane-world-map-pointer-observer",
            daemon=True,
        )
        try:
            self._world_map_thread.start()
        except BaseException:
            super().close()
            raise
        self._world_map_ready.wait(timeout=1.0)

    def close(self) -> None:
        super().close()
        if self._world_map_thread is not None:
            self._world_map_thread.join(timeout=2.0)
        self._world_map_capture = None
        self._suppress_left_button_up = False
        self._suppress_right_button_up = False

    def _listen(self) -> None:
        """Install responsive hooks and selectively consume captured map selections."""

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
        user32.GetForegroundWindow.restype = wintypes.HWND
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        keyboard_hook: int | None = None
        mouse_hook: int | None = None

        @callback_type
        def keyboard_callback(code: int, message: int, event_pointer: int) -> int:
            if code >= 0 and message in (self._WM_KEYDOWN, self._WM_SYSKEYDOWN):
                self._keyboard_hook_events += 1
                event = ctypes.cast(
                    event_pointer,
                    ctypes.POINTER(KeyboardEvent),
                ).contents
                if not event.flags & self._LLKHF_INJECTED:
                    self._physical_keyboard_events += 1
                    self._pending_input.put(
                        _PhysicalKeyboardInteraction(
                            int(event.vk_code),
                            bool(user32.GetAsyncKeyState(self._VK_SHIFT) & 0x8000),
                        )
                    )
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
            button_up = None
            if message == self._WM_LBUTTONUP:
                button_up = "left"
            elif message == self._WM_RBUTTONUP:
                button_up = "right"
            if code >= 0 and button_up is not None:
                event = ctypes.cast(
                    event_pointer,
                    ctypes.POINTER(MouseEvent),
                ).contents
                if (
                    not event.flags & self._LLMHF_INJECTED
                    and self._consume_button_up_suppression(button_up)
                ):
                    return 1

            if code >= 0 and message in (
                self._WM_LBUTTONDOWN,
                self._WM_RBUTTONDOWN,
                self._WM_MBUTTONDOWN,
                self._WM_XBUTTONDOWN,
            ):
                self._mouse_hook_events += 1
                event = ctypes.cast(
                    event_pointer,
                    ctypes.POINTER(MouseEvent),
                ).contents
                if not event.flags & self._LLMHF_INJECTED:
                    self._physical_mouse_events += 1
                    interaction = PhysicalPointerInteraction(
                        screen_x=int(event.point.x),
                        screen_y=int(event.point.y),
                        button={
                            self._WM_LBUTTONDOWN: "left",
                            self._WM_RBUTTONDOWN: "right",
                            self._WM_MBUTTONDOWN: "middle",
                            self._WM_XBUTTONDOWN: "x",
                        }[int(message)],
                    )
                    physical_button = interaction.button
                    suppress = False
                    if physical_button in {"left", "right"}:
                        self._clear_button_up_suppression(physical_button)
                        try:
                            interaction, suppress = self._prepare_pointer_interaction(
                                interaction,
                                foreground_window_handle=int(user32.GetForegroundWindow() or 0),
                            )
                        except Exception:
                            # Hook callbacks must always fail open. Diagnostics and the
                            # downstream native reader retain the ordinary error path.
                            suppress = False
                    self._pending_input.put(interaction)
                    if suppress:
                        self._arm_button_up_suppression(physical_button)
                        return 1
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

    def _observe_world_map(self) -> None:
        reader = None
        profile = self._world_map_profile
        try:
            while not self._closed.is_set():
                try:
                    if profile is None:
                        profile = load_bundled_native_world_map_profile()
                    target = self._guard.require_target()
                    if target.process_id is None:
                        raise WindowGuardError("foreground process identity is unavailable")
                    if target.window_handle is None:
                        raise WindowGuardError("foreground window handle is unavailable")
                    if reader is None or reader.process_id != target.process_id:
                        if reader is not None:
                            reader.close()
                        reader = open_windows_native_world_map_reader(
                            profile,
                            process_id=target.process_id,
                        )
                    observation = reader.observe()
                    self._world_map_observations += 1
                    self._last_world_map_error = None
                    if observation.is_open:
                        self._world_map_capture = _WorldMapCaptureSnapshot(
                            observation=observation,
                            observed_at=time.monotonic(),
                            client_left=target.client_bounds.left,
                            client_top=target.client_bounds.top,
                            process_id=target.process_id,
                            window_handle=target.window_handle,
                        )
                    else:
                        self._world_map_capture = None
                except WindowGuardError as exc:
                    self._world_map_capture = None
                    self._last_world_map_error = str(exc)[:512]
                except (NativeWorldMapError, OSError, RuntimeError, ValueError) as exc:
                    self._world_map_capture = None
                    self._world_map_read_errors += 1
                    self._last_world_map_error = str(exc)[:512]
                    if reader is not None:
                        reader.close()
                        reader = None
                finally:
                    self._world_map_ready.set()
                self._closed.wait(self._WORLD_MAP_POLL_SECONDS)
        finally:
            self._world_map_capture = None
            self._world_map_ready.set()
            if reader is not None:
                reader.close()

    def _arm_button_up_suppression(self, button: str) -> None:
        if button == "left":
            self._suppress_left_button_up = True
            return
        if button == "right":
            self._suppress_right_button_up = True
            return
        raise ValueError("only left and right button-up events can be suppressed")

    def _clear_button_up_suppression(self, button: str) -> None:
        if button == "left":
            self._suppress_left_button_up = False
            return
        if button == "right":
            self._suppress_right_button_up = False
            return
        raise ValueError("only left and right button-up events can be suppressed")

    def _consume_button_up_suppression(self, button: str) -> bool:
        if button == "left":
            if not self._suppress_left_button_up:
                return False
            self._suppress_left_button_up = False
            self._suppressed_left_button_ups += 1
            return True
        if button == "right":
            if not self._suppress_right_button_up:
                return False
            self._suppress_right_button_up = False
            self._suppressed_right_button_ups += 1
            return True
        raise ValueError("only left and right button-up events can be suppressed")

    def _prepare_pointer_interaction(
        self,
        interaction: PhysicalPointerInteraction,
        *,
        foreground_window_handle: int,
        now: float | None = None,
    ) -> tuple[PhysicalPointerInteraction, bool]:
        """Normalize and claim one valid map selection without touching native state."""

        if not isinstance(interaction, PhysicalPointerInteraction):
            raise ValueError("interaction must be PhysicalPointerInteraction")
        if isinstance(foreground_window_handle, bool) or not isinstance(
            foreground_window_handle, int
        ):
            raise ValueError("foreground_window_handle must be an integer")
        if now is None:
            now = time.monotonic()
        if not isfinite(now) or now < 0:
            raise ValueError("now must be finite and non-negative")
        if interaction.button not in {"left", "right"}:
            return interaction, False

        self._world_map_capture_attempts += 1
        capture = self._world_map_capture
        if (
            capture is None
            or foreground_window_handle <= 0
            or foreground_window_handle != capture.window_handle
            or now < capture.observed_at
            or now - capture.observed_at > self._WORLD_MAP_MAX_AGE_SECONDS
        ):
            self._world_map_capture_misses += 1
            return interaction, False

        client_x = interaction.screen_x - capture.client_left
        client_y = interaction.screen_y - capture.client_top
        try:
            point = capture.observation.resolve_screen_point(client_x, client_y)
        except (NativeWorldMapError, RuntimeError, ValueError):
            self._world_map_capture_misses += 1
            return interaction, False

        self._world_map_captured_clicks += 1
        if interaction.button == "left":
            self._world_map_captured_left_clicks += 1
        else:
            self._world_map_captured_right_clicks += 1
        return (
            WorldMapPointerInteraction(
                screen_x=client_x,
                screen_y=client_y,
                button="right",
                physical_button=interaction.button,
                desktop_screen_x=interaction.screen_x,
                desktop_screen_y=interaction.screen_y,
                process_id=capture.process_id,
                window_handle=capture.window_handle,
                lt=point.lt,
                lg=point.lg,
                snapshot_token=capture.observation.snapshot_token,
            ),
            True,
        )
