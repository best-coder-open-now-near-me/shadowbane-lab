"""Sky controls within the existing connected Graphics Lab."""

from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, ttk

from .sky import RANGES, SkyClient, SkySettings, load_settings, save_settings


class SkyPanel:
    def __init__(self, notebook: ttk.Notebook) -> None:
        self.client: SkyClient | None = None
        self.tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.tab, text="Sky / horizon")
        self.status = tk.StringVar(value="Connect the full-profile sky package")
        self.enabled = tk.BooleanVar(value=False)
        ttk.Label(self.tab, text="Clear day - infinite sky - horizon haze").pack(anchor="w")
        ttk.Label(self.tab, text="Decorative background; does not add or repair terrain.").pack(
            anchor="w"
        )
        ttk.Checkbutton(self.tab, text="Sky enabled", variable=self.enabled).pack(anchor="w")
        labels = {
            "orientation": "Orientation (degrees)",
            "intensity": "Appearance intensity",
            "horizon_height": "Horizon elevation",
            "horizon_width": "Horizon transition width",
            "clouds": "Cirrus strength",
            "sun": "Sun glow",
            "fog_match": "Match native fog",
        }
        fields = ttk.Frame(self.tab)
        fields.pack(fill="x", pady=8)
        self.values = {}
        for row, (name, (low, high)) in enumerate(RANGES.items()):
            ttk.Label(fields, text=f"{labels[name]} ({low} to {high})").grid(
                row=row, column=0, sticky="w", pady=4
            )
            value = tk.StringVar(value=str(getattr(SkySettings(), name)))
            self.values[name] = value
            ttk.Entry(fields, textvariable=value, width=12).grid(row=row, column=1, padx=10)
        actions = ttk.Frame(self.tab)
        actions.pack(fill="x")
        for label, command in (
            ("Apply", self.apply),
            ("Enable", self.enable),
            ("Disable", self.disable),
            ("Restore original", self.restore),
        ):
            ttk.Button(actions, text=label, command=command).pack(side="left")
        presets = ttk.Frame(self.tab)
        presets.pack(fill="x", pady=8)
        ttk.Button(
            presets,
            text="Clear-day defaults",
            command=lambda: self.set(SkySettings(enabled=int(self.enabled.get()))),
        ).pack(side="left")
        ttk.Button(presets, text="Save appearance...", command=self.save).pack(side="left")
        ttk.Button(presets, text="Load appearance...", command=self.load).pack(side="left")
        ttk.Label(self.tab, textvariable=self.status, wraplength=560).pack(fill="x", pady=8)
        self.tab.after(500, self.poll)

    def set(self, settings: SkySettings) -> None:
        self.enabled.set(bool(settings.enabled))
        for name, value in self.values.items():
            value.set(str(getattr(settings, name)))

    def get(self) -> SkySettings:
        settings = SkySettings(
            enabled=int(self.enabled.get()),
            **{name: float(value.get()) for name, value in self.values.items()},
        )
        settings.validate()
        return settings

    def connect(self, target) -> None:
        self.disconnect()
        try:
            self.client = SkyClient(target)
            self.set(self.client.read()[0])
        except (OSError, ValueError, RuntimeError) as error:
            self.disconnect()
            self.status.set(str(error))

    def disconnect(self) -> None:
        if self.client:
            self.client.close()
        self.client = None

    def apply(self) -> None:
        try:
            if not self.client:
                raise OSError("Connect the full-profile sky package first")
            sequence = self.client.write(self.get())
            self.status.set(f"Queued {sequence}; waiting for the next scene")
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            self.status.set(str(error))

    def enable(self) -> None:
        self.enabled.set(True)
        self.apply()

    def disable(self) -> None:
        self.enabled.set(False)
        try:
            if self.client:
                # Invalid pending field edits cannot prevent disabling the live feature.
                settings = replace(self.client.read()[0], enabled=0)
                self.client.write(settings)
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            self.status.set(str(error))

    def restore(self) -> None:
        self.set(SkySettings())
        self.apply()

    def save(self) -> None:
        try:
            settings = self.get()
            name = filedialog.asksaveasfilename(
                parent=self.tab, defaultextension=".json", filetypes=[("Sky appearance", "*.json")]
            )
            if name:
                save_settings(Path(name), settings)
                self.status.set("Appearance saved")
        except (OSError, ValueError) as error:
            self.status.set(str(error))

    def load(self) -> None:
        name = filedialog.askopenfilename(parent=self.tab, filetypes=[("Sky appearance", "*.json")])
        if not name:
            return
        try:
            self.set(load_settings(Path(name)))
            self.status.set("Appearance loaded; Apply to update the connected client")
        except (OSError, ValueError) as error:
            self.status.set(str(error))

    def poll(self) -> None:
        if self.client:
            try:
                _, stats, desired, applied, error = self.client.read()
                reason = {
                    0: "ready",
                    1: "waiting for verified camera/scene",
                    2: "graphics state refused",
                    3: "no verified world scene",
                }.get(stats[4], "unavailable")
                self.status.set(
                    f"Sequence {applied}/{desired}; error {error} - {reason}\n"
                    f"Sky drawn: {bool(stats[1])} - native draws replaced: {stats[3]}\n"
                    f"Background cost: {stats[5]} us - refused frames: {stats[2]}"
                )
            except (OSError, ValueError, RuntimeError) as error:
                self.status.set(str(error))
        self.tab.after(500, self.poll)
