"""Live katana length controls in Graphics Lab; exact-process shared channel."""

from __future__ import annotations

import ctypes
import math
import struct
from dataclasses import dataclass
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, ttk

from . import control

SIZE = 96
HEADER = struct.Struct("<4IQ3If3I6f3I")
OWNER_LABELS = ("My character", "Selected character")
FIRE = struct.Struct("<I6f")
FIRE_CONTROLS = (
    ("strength", "Glow strength", 0, 150, 111),
    ("size", "Square size", 60, 150, 100),
    ("spacing", "Spacing", 80, 150, 80),
    ("pulse", "Pulse", 0, 35, 35),
    ("hilt", "Hilt diamond", 25, 250, 125),
    ("width", "Glow width", 40, 400, 86),
)


@dataclass(frozen=True)
class FireSettings:
    enabled: int = 1
    strength: float = 1.11
    size: float = 1.0
    spacing: float = 0.8
    pulse: float = 0.35
    hilt: float = 1.25
    width: float = 0.86

    def values(self):
        return (self.enabled, *(getattr(self, item[0]) for item in FIRE_CONTROLS))

    def validate(self):
        if self.enabled not in (0, 1):
            raise ValueError("Invalid moon-fire toggle")
        for field, label, low, high, _ in FIRE_CONTROLS:
            value = getattr(self, field)
            if not math.isfinite(value) or not low / 100 - 1e-6 <= value <= high / 100 + 1e-6:
                raise ValueError(f"{label} must be between {low} and {high} percent")


def unpack(data, target):
    if len(data) != SIZE:
        raise ValueError("Katana control size mismatch")
    values = HEADER.unpack_from(data)
    magic, version, size, pid, creation, desired, applied, error, length, matches, draws = values[
        :11
    ]
    if (magic, version, size, pid, creation) != (
        0x4B574257,
        3,
        SIZE,
        target.process_id,
        target.process_creation_filetime_utc,
    ):
        raise ValueError("Katana control identity mismatch")
    if not math.isfinite(length) or not 0.599999 <= length <= 1.200001 or desired & 1:
        raise ValueError("Katana controls unavailable or being updated")
    fire = FireSettings(*values[11:18])
    fire.validate()
    if values[20] not in (0, 1):
        raise ValueError("Invalid katana character selection")
    return length, desired, applied, error, matches, draws, fire, values[18], values[19], values[20]


class KatanaClient:
    def __init__(self, target):
        self.target = target
        self.mapping = self.address = self.mutex = None
        if not control.verify_target_identity(target):
            raise OSError("The selected game instance has changed")
        api = control._kernel32
        name = f"Local\\WonderBaneKatana-{target.process_id}-{target.process_creation_filetime_utc}"
        try:
            self.mapping = api.OpenFileMappingW(0xF001F, False, name)
            if not self.mapping:
                raise OSError("This client needs the live katana extension update")
            self.address = api.MapViewOfFile(self.mapping, 0xF001F, 0, 0, SIZE)
            if not self.address:
                raise OSError("Could not open katana controls")
            self.mutex = api.CreateMutexW(None, False, name + "-writer")
            if not self.mutex:
                raise OSError("Could not open katana control writer")
            self.read()
        except Exception:
            self.close()
            raise

    def read(self):
        if not self.address or not control.target_process_is_alive(self.target):
            raise OSError("Game closed or changed")
        first = ctypes.c_uint32.from_address(self.address + 24).value
        data = ctypes.string_at(self.address, SIZE)
        last = ctypes.c_uint32.from_address(self.address + 24).value
        if first != last or HEADER.unpack_from(data)[5] != first:
            raise ValueError("Katana controls are being updated")
        return unpack(data, self.target)

    def write(self, percent, fire=None, selection=None):
        if isinstance(percent, bool) or not math.isfinite(percent) or not 60 <= percent <= 120:
            raise ValueError("Overall length must be between 60 and 120 percent")
        if fire is not None:
            fire.validate()
        if selection is not None and (type(selection) is not int or selection not in (0, 1)):
            raise ValueError("Invalid katana character selection")
        api = control._kernel32
        if not self.mutex or api.WaitForSingleObject(self.mutex, 100) not in (0, 0x80):
            raise TimeoutError("Katana controls are busy")
        try:
            snapshot = self.read()
            _, desired, applied, *_ = snapshot
            fire = fire if fire is not None else snapshot[6]
            selection = selection if selection is not None else snapshot[9]
            sequence = max(desired, applied) + 2
            if sequence >= 0x7FFFFFFE:
                sequence = 2
            word = ctypes.c_uint32.from_address(self.address + 24)
            word.value = sequence - 1
            ctypes.memmove(self.address + 36, struct.pack("<f", percent / 100), 4)
            ctypes.memmove(self.address + 48, FIRE.pack(*fire.values()), FIRE.size)
            ctypes.memmove(self.address + 84, struct.pack("<I", selection), 4)
            word.value = sequence
        finally:
            api.ReleaseMutex(self.mutex)

    def close(self):
        api = control._kernel32
        if self.address:
            api.UnmapViewOfFile(self.address)
        for handle in (self.mapping, self.mutex):
            if handle:
                api.CloseHandle(handle)
        self.mapping = self.address = self.mutex = None


class KatanaPanel:
    def __init__(self, notebook):
        self.frame = ttk.Frame(notebook, padding=16)
        notebook.add(self.frame, text="Katana")
        self.client = None
        self.pending = None
        self.owner_selection = IntVar(value=0)
        self.value = DoubleVar(value=80)
        self.label = StringVar(value="Overall length: 80%")
        self.fire_enabled = BooleanVar(value=True)
        self.fire_vars = {
            name: DoubleVar(value=default) for name, _, _, _, default in FIRE_CONTROLS
        }
        self.fire_labels = {name: StringVar() for name, *_ in FIRE_CONTROLS}
        self.fire_widgets = []
        self.status = StringVar(value="Connect a game instance to adjust its equipped katanas.")
        ttk.Label(self.frame, text="Apply to").pack(anchor="w")
        owners = ttk.Frame(self.frame)
        owners.pack(fill="x", pady=4)
        self.owner_widgets = []
        for index, label in enumerate(OWNER_LABELS):
            button = ttk.Radiobutton(
                owners, text=label, variable=self.owner_selection, value=index,
                command=self.change, state="disabled",
            )
            button.pack(side="left", padx=(0, 16))
            self.owner_widgets.append(button)
        ttk.Label(
            self.frame, text="Selected character follows your current in-game selection.",
            wraplength=480,
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(self.frame, text="Katana proportions").pack(anchor="w")
        ttk.Label(
            self.frame,
            text=(
                "Compresses the whole weapon lengthwise around the hand grip. "
                "Width stays unchanged. 100% is the original model length."
            ),
            wraplength=480,
        ).pack(anchor="w", pady=10)
        ttk.Label(self.frame, textvariable=self.label).pack(anchor="w")
        self.slider = ttk.Scale(
            self.frame, from_=60, to=120, variable=self.value, command=self.change, state="disabled"
        )
        self.slider.pack(fill="x", pady=8)
        self.shorter = ttk.Button(
            self.frame, text="Try 85%", command=lambda: self.set_length(85), state="disabled"
        )
        self.shorter.pack(anchor="w", pady=4)
        self.reset = ttk.Button(
            self.frame, text="Reset to 100%", command=lambda: self.set_length(100), state="disabled"
        )
        self.reset.pack(anchor="w", pady=4)
        self.fire_toggle = ttk.Checkbutton(
            self.frame,
            text="White moon-fire",
            variable=self.fire_enabled,
            command=self.change,
            state="disabled",
        )
        self.fire_toggle.pack(anchor="w", pady=(12, 4))
        self.fire_widgets.append(self.fire_toggle)
        controls = ttk.Frame(self.frame)
        controls.pack(fill="x")
        for index, (name, label, low, high, default) in enumerate(FIRE_CONTROLS):
            box = ttk.Frame(controls, padding=(0, 2, 12, 2))
            box.grid(row=index // 2, column=index % 2, sticky="ew")
            controls.columnconfigure(index % 2, weight=1)
            self.fire_labels[name].set(f"{label}: {default}%")
            ttk.Label(box, textvariable=self.fire_labels[name]).pack(anchor="w")
            slider = ttk.Scale(
                box,
                from_=low,
                to=high,
                variable=self.fire_vars[name],
                command=self.change,
                state="disabled",
            )
            slider.pack(fill="x")
            self.fire_widgets.append(slider)
        ttk.Label(self.frame, textvariable=self.status, wraplength=480).pack(anchor="w", pady=12)
        self.frame.after(500, self.poll)

    def set_length(self, value):
        self.value.set(value)
        self.change()

    def change(self, *_):
        self.update_labels()
        if self.pending:
            self.frame.after_cancel(self.pending)
        self.pending = self.frame.after(60, self.apply)

    def update_labels(self):
        self.label.set(f"Overall length: {round(self.value.get())}%")
        for name, label, *_ in FIRE_CONTROLS:
            self.fire_labels[name].set(f"{label}: {round(self.fire_vars[name].get())}%")

    def apply(self):
        self.pending = None
        if self.client:
            try:
                fire = FireSettings(
                    int(self.fire_enabled.get()),
                    *(round(self.fire_vars[name].get()) / 100 for name, *_ in FIRE_CONTROLS),
                )
                self.client.write(round(self.value.get()), fire, self.owner_selection.get())
            except (OSError, RuntimeError, ValueError) as error:
                self.status.set(str(error))

    def connect(self, target):
        self.disconnect()
        try:
            self.client = KatanaClient(target)
            snapshot = self.client.read()
            length, fire = snapshot[0], snapshot[6]
            self.owner_selection.set(snapshot[9])
            self.value.set(length * 100)
            self.fire_enabled.set(bool(fire.enabled))
            for name, *_ in FIRE_CONTROLS:
                self.fire_vars[name].set(getattr(fire, name) * 100)
            self.update_labels()
            for widget in (
                self.slider, self.shorter, self.reset, *self.fire_widgets, *self.owner_widgets
            ):
                widget.configure(state="normal")
        except (OSError, RuntimeError, ValueError) as error:
            self.disconnect()
            self.status.set(str(error))

    def disconnect(self):
        if self.pending:
            self.frame.after_cancel(self.pending)
            self.pending = None
        if self.client:
            self.client.close()
        self.client = None
        for widget in (
            self.slider, self.shorter, self.reset, *self.fire_widgets, *self.owner_widgets
        ):
            widget.configure(state="disabled")

    def poll(self):
        if self.client:
            try:
                (
                    length, desired, applied, error, matches, draws, fire, fire_draws,
                    reason, selection,
                ) = self.client.read()
                owner = OWNER_LABELS[selection]
                if error:
                    self.status.set(f"{owner}: waiting for equipped katanas (status {error}).")
                elif desired != applied:
                    self.status.set("Waiting for the next game frame…")
                elif fire.enabled and reason:
                    self.status.set(
                        f"{owner}: {matches} katanas; moon-fire waiting "
                        f"for supported draw state ({reason})."
                    )
                elif (length != 1 or fire.enabled) and not draws:
                    self.status.set(
                        f"{owner}: matched {matches} katanas; waiting for supported visible draws."
                    )
                else:
                    self.status.set(
                        f"{owner}: {matches} katanas / {round(length * 100)}% / "
                        + (f"moon-fire on {fire_draws} draws" if fire.enabled else "moon-fire off")
                    )
            except (OSError, RuntimeError, ValueError) as error:
                self.disconnect()
                self.status.set(str(error))
        self.frame.after(500, self.poll)
