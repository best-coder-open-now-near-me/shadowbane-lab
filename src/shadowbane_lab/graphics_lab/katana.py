"""Live katana length controls in Graphics Lab; exact-process shared channel."""

from __future__ import annotations

import ctypes
import math
import struct
from tkinter import DoubleVar, StringVar, ttk

from . import control

SIZE = 64
HEADER = struct.Struct("<4IQ3If2I")


def unpack(data, target):
    if len(data) != SIZE:
        raise ValueError("Katana control size mismatch")
    magic, version, size, pid, creation, desired, applied, error, length, matches, draws = (
        HEADER.unpack_from(data)
    )
    if (magic, version, size, pid, creation) != (
        0x4B574257,
        1,
        SIZE,
        target.process_id,
        target.process_creation_filetime_utc,
    ):
        raise ValueError("Katana control identity mismatch")
    if not math.isfinite(length) or not 0.599999 <= length <= 1.200001 or desired & 1:
        raise ValueError("Katana controls unavailable or being updated")
    return length, desired, applied, error, matches, draws


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

    def write(self, percent):
        if isinstance(percent, bool) or not math.isfinite(percent) or not 60 <= percent <= 120:
            raise ValueError("Overall length must be between 60 and 120 percent")
        api = control._kernel32
        if not self.mutex or api.WaitForSingleObject(self.mutex, 100) not in (0, 0x80):
            raise TimeoutError("Katana controls are busy")
        try:
            _, desired, applied, *_ = self.read()
            sequence = max(desired, applied) + 2
            if sequence >= 0x7FFFFFFE:
                sequence = 2
            word = ctypes.c_uint32.from_address(self.address + 24)
            word.value = sequence - 1
            ctypes.memmove(self.address + 36, struct.pack("<f", percent / 100), 4)
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
        self.value = DoubleVar(value=100)
        self.label = StringVar(value="Overall length: 100%")
        self.status = StringVar(value="Connect a game instance to adjust its equipped katanas.")
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
        ttk.Label(self.frame, textvariable=self.status, wraplength=480).pack(anchor="w", pady=12)
        self.frame.after(500, self.poll)

    def set_length(self, value):
        self.value.set(value)
        self.change()

    def change(self, *_):
        self.label.set(f"Overall length: {round(self.value.get())}%")
        if self.pending:
            self.frame.after_cancel(self.pending)
        self.pending = self.frame.after(60, self.apply)

    def apply(self):
        self.pending = None
        if self.client:
            try:
                self.client.write(round(self.value.get()))
            except (OSError, RuntimeError, ValueError) as error:
                self.status.set(str(error))

    def connect(self, target):
        self.disconnect()
        try:
            self.client = KatanaClient(target)
            length, *_ = self.client.read()
            self.value.set(length * 100)
            self.label.set(f"Overall length: {round(length * 100)}%")
            for widget in (self.slider, self.shorter, self.reset):
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
        for widget in (self.slider, self.shorter, self.reset):
            widget.configure(state="disabled")

    def poll(self):
        if self.client:
            try:
                length, desired, applied, error, matches, draws = self.client.read()
                if error:
                    self.status.set(f"Waiting for equipped katana rendering (status {error}).")
                elif desired != applied:
                    self.status.set("Waiting for the next game frame…")
                elif length != 1 and not draws:
                    self.status.set(
                        f"Matched {matches} katanas; waiting for supported visible draws."
                    )
                else:
                    self.status.set(
                        f"{matches} katanas / {round(length * 100)}% / {draws} adjusted draws"
                    )
            except (OSError, RuntimeError, ValueError) as error:
                self.disconnect()
                self.status.set(str(error))
        self.frame.after(500, self.poll)
