"""Selected-character cue controls in the existing Graphics Lab."""

from __future__ import annotations

import ctypes
import json
import math
import os
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, StringVar, colorchooser, ttk

from . import control

MAGIC = 0x55434257
SIZE = 88
HEADER = struct.Struct("<10I")
PARAMETERS = struct.Struct("<I7f")


@dataclass(frozen=True)
class CueSettings:
    enabled: bool = False
    red: float = 0.2
    green: float = 0.85
    blue: float = 1.0
    opacity: float = 0.8
    radius: float = 5.0
    indicator_size: float = 24.0
    indicator_y: float = 0.18

    def validate(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be boolean")
        for name, low, high in (
            ("red", 0, 1),
            ("green", 0, 1),
            ("blue", 0, 1),
            ("opacity", 0.05, 1),
            ("radius", 1, 12),
            ("indicator_size", 12, 64),
            ("indicator_y", 0.12, 0.75),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError(f"{name} must be between {low} and {high}")

    def pack(self) -> bytes:
        self.validate()
        return PARAMETERS.pack(
            int(self.enabled),
            self.red,
            self.green,
            self.blue,
            self.opacity,
            self.radius,
            self.indicator_size,
            self.indicator_y,
        )


def unpack(
    data: bytes, target: control.GraphicsControlTarget
) -> tuple[CueSettings, tuple[int, ...]]:
    if len(data) != SIZE:
        raise ValueError("cue control size mismatch")
    h = HEADER.unpack_from(data)
    if (
        h[:4] != (MAGIC, 1, SIZE, target.process_id)
        or (h[4] | h[5] << 32) != target.process_creation_filetime_utc
    ):
        raise ValueError("cue control identity/version mismatch")
    if h[6] & 1:
        raise ValueError("cue control write in progress")
    p = PARAMETERS.unpack_from(data, 40)
    if p[0] > 1:
        raise ValueError("invalid cue enable flag")
    settings = CueSettings(bool(p[0]), *p[1:])
    settings.validate()
    return settings, (*h[6:], *struct.unpack_from("<4I", data, 72))


class CueClient:
    def __init__(self, target: control.GraphicsControlTarget):
        if os.name != "nt" or not control.verify_target_identity(target):
            raise OSError("cue target identity is unavailable")
        self.target = target
        self._mapping = self._address = self._mutex = None
        api = control._kernel32
        name = (
            f"Local\\WonderBaneSelectedCue-{target.process_id}-"
            f"{target.process_creation_filetime_utc}"
        )
        try:
            self._mapping = api.OpenFileMappingW(0xF001F, False, name)
            if not self._mapping:
                raise OSError("selected-character cue is unavailable in this client package")
            self._address = api.MapViewOfFile(self._mapping, 0xF001F, 0, 0, SIZE)
            if not self._address:
                raise OSError("could not map selected-character controls")
            self._mutex = api.CreateMutexW(None, False, name + "-writer")
            if not self._mutex:
                raise OSError("could not acquire cue writer")
            self.read()
        except Exception:
            self.close()
            raise

    def read(self):
        if not self._address or not control.target_process_is_alive(self.target):
            raise OSError("cue target closed or changed")
        # Coherent snapshot, including sequence validation around the copy.
        first = ctypes.c_uint32.from_address(self._address + 24).value
        data = ctypes.string_at(self._address, SIZE)
        last = ctypes.c_uint32.from_address(self._address + 24).value
        if first != last or first & 1 or HEADER.unpack_from(data)[6] != first:
            raise ValueError("cue write in progress")
        return unpack(data, self.target)

    def write(self, settings: CueSettings) -> int:
        payload = settings.pack()
        api = control._kernel32
        if not self._mutex or api.WaitForSingleObject(self._mutex, 2000) not in (0, 0x80):
            raise TimeoutError("cue controls are busy")
        try:
            _, state = self.read()
            sequence = max(state[:3]) + 2
            if sequence >= 0x7FFFFFFE:
                sequence = 2
            word = ctypes.c_uint32.from_address(self._address + 24)
            word.value = sequence - 1
            ctypes.memmove(self._address + 40, payload, len(payload))
            word.value = sequence
            return sequence
        finally:
            api.ReleaseMutex(self._mutex)

    def close(self):
        api = control._kernel32
        if self._address:
            api.UnmapViewOfFile(self._address)
        for handle in (self._mapping, self._mutex):
            if handle:
                api.CloseHandle(handle)
        self._mapping = self._address = self._mutex = None


class CuePanel:
    def __init__(self, notebook, get_target):
        self.frame = ttk.Frame(notebook, padding=16)
        notebook.add(self.frame, text="Selection")
        self.get_target = get_target
        self.client = None
        self.color = (0.2, 0.85, 1.0)
        self.enabled = BooleanVar(value=False)
        self.status = StringVar(value="Choose a connected client, then apply settings.")
        ttk.Checkbutton(
            self.frame, text="Selected-character glow and direction", variable=self.enabled
        ).pack(anchor="w")
        ttk.Label(
            self.frame,
            text="Visible glow; obstacles hide it. Arrow indicates the camera turn.",
            wraplength=480,
        ).pack(anchor="w", pady=8)
        self.values = {}
        for key, label, default, low, high in (
            ("opacity", "Opacity", 0.8, 0.05, 1),
            ("radius", "Glow radius (pixels)", 5, 1, 12),
            ("indicator_size", "Arrow size (pixels)", 24, 12, 64),
            ("indicator_y", "Arrow height from top (fraction)", 0.18, 0.12, 0.75),
        ):
            ttk.Label(self.frame, text=label).pack(anchor="w", pady=(8, 0))
            value = DoubleVar(value=default)
            self.values[key] = value
            ttk.Scale(self.frame, variable=value, from_=low, to=high).pack(fill="x")
        ttk.Button(self.frame, text="Choose cue color", command=self.choose_color).pack(
            anchor="w", pady=10
        )
        ttk.Button(self.frame, text="Apply to selected client", command=self.apply).pack(anchor="w")
        ttk.Button(self.frame, text="Save appearance", command=self.save).pack(anchor="w", pady=8)
        ttk.Label(self.frame, textvariable=self.status, wraplength=480).pack(anchor="w", pady=8)
        self.path = (
            Path(os.environ.get("LOCALAPPDATA", Path.home()))
            / "ShadowbaneLab"
            / "graphics-lab"
            / "selected-cue.json"
        )
        try:
            saved = CueSettings(**json.loads(self.path.read_text(encoding="utf-8")))
            saved.validate()
            self.set_values(saved)
        except (OSError, ValueError, TypeError):
            pass
        self.timer = self.frame.after(500, self.poll)

    def settings(self):
        return CueSettings(
            self.enabled.get(), *self.color, **{k: v.get() for k, v in self.values.items()}
        )

    def set_values(self, settings):
        self.color = (settings.red, settings.green, settings.blue)
        for key, variable in self.values.items():
            variable.set(getattr(settings, key))

    def choose_color(self):
        value, _ = colorchooser.askcolor(parent=self.frame)
        if value:
            self.color = tuple(channel / 255 for channel in value)

    def apply(self):
        try:
            target = self.get_target()
            if target is None:
                raise OSError("choose a live client first")
            if self.client is None or self.client.target != target:
                self.disconnect()
                self.client = CueClient(target)
            sequence = self.client.write(self.settings())
            self.status.set(f"Queued settings {sequence}; awaiting the client frame.")
        except (OSError, ValueError, TimeoutError) as error:
            self.status.set(str(error))

    def save(self):
        try:
            settings = self.settings()
            settings.validate()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
            self.status.set("Appearance saved. Enable and apply explicitly after reconnecting.")
        except (OSError, ValueError) as error:
            self.status.set(str(error))

    def poll(self):
        if self.client:
            try:
                if self.client.target != self.get_target():
                    self.disconnect()
                else:
                    _, s = self.client.read()
                    desired, applied, rejected, error, binding, draws, gpu_error, observation = s
                    if not binding:
                        self.status.set("Character render binding unavailable; cue is disabled.")
                    elif error or gpu_error or observation:
                        self.status.set(
                            f"Cue unavailable: controls {error}, graphics {gpu_error}, "
                            f"observation {observation}."
                        )
                    elif desired == applied:
                        self.status.set(
                            f"Applied {applied} · owned character draws this frame: {draws}"
                        )
                    else:
                        self.status.set(
                            f"Waiting for frame acknowledgement {desired} "
                            f"(last rejection {rejected})."
                        )
            except (OSError, ValueError) as error:
                self.disconnect()
                self.status.set(str(error))
        self.timer = self.frame.after(500, self.poll)

    def disconnect(self):
        if self.client:
            self.client.close()
        self.client = None

    def close(self):
        self.frame.after_cancel(self.timer)
        self.disconnect()
