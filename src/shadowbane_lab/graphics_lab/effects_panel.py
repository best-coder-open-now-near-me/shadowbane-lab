"""Effects tab in the existing Graphics Lab; no observation publisher is required."""

from __future__ import annotations

import tkinter as tk
from dataclasses import asdict
from tkinter import ttk

from .effects import PRESETS, RANGES, EffectsClient, EffectsConfig


class EffectsPanel:
    def __init__(self, notebook: ttk.Notebook) -> None:
        self.client: EffectsClient | None = None
        self.tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.tab, text="Particles / trails")
        self.status = tk.StringVar(value="Connect a full-profile effects client")
        ttk.Label(self.tab, text="Actor-root attachments · scene depth · no depth writes").pack(
            anchor="w"
        )
        self.attachment = tk.StringVar(value="Local player root")
        ttk.Combobox(
            self.tab,
            textvariable=self.attachment,
            state="readonly",
            values=("Local player root", "Selected character root"),
        ).pack(fill="x")
        self.flags = [tk.BooleanVar() for _ in range(4)]
        row = ttk.Frame(self.tab)
        row.pack(fill="x")
        for flag, label in zip(
            self.flags, ("Enabled", "Emitter", "Ribbon", "Additive"), strict=True
        ):
            ttk.Checkbutton(row, variable=flag, text=label).pack(side="left")
        self.preset = tk.StringVar(value="Azure wake")
        presets = ttk.Frame(self.tab)
        presets.pack(fill="x")
        ttk.Combobox(
            presets, textvariable=self.preset, values=tuple(PRESETS), state="readonly"
        ).pack(side="left")
        ttk.Button(
            presets, text="Load preset", command=lambda: self.set(PRESETS[self.preset.get()])
        ).pack(side="left")
        fields = ttk.Frame(self.tab)
        fields.pack(fill="both", expand=True)
        self.values = {}
        defaults = asdict(EffectsConfig())
        for index, name in enumerate(("burst_count", "particle_budget", "sample_budget", *RANGES)):
            row, column = divmod(index, 2)
            ttk.Label(fields, text=name.replace("_", " ")).grid(
                row=row, column=column * 2, sticky="w", pady=3
            )
            variable = tk.StringVar(value=str(defaults[name]))
            self.values[name] = variable
            ttk.Entry(fields, textvariable=variable, width=9).grid(
                row=row, column=column * 2 + 1, padx=6
            )
        actions = ttk.Frame(self.tab)
        actions.pack(fill="x")
        ttk.Button(actions, text="Apply", command=self.apply).pack(side="left")
        ttk.Button(actions, text="Burst now", command=lambda: self.apply(burst=True)).pack(
            side="left"
        )
        ttk.Button(actions, text="Disable / clear", command=self.disable).pack(side="left")
        ttk.Label(self.tab, textvariable=self.status, wraplength=540).pack(fill="x", pady=8)
        self.tab.after(500, self.poll)

    def set(self, config: EffectsConfig) -> None:
        for index, flag in enumerate(self.flags):
            flag.set(bool(config.flags & (1 << index)))
        self.attachment.set("Selected character root" if config.attachment else "Local player root")
        for name, variable in self.values.items():
            variable.set(str(getattr(config, name)))

    def connect(self, target) -> None:
        self.disconnect()
        try:
            self.client = EffectsClient(target)
            self.set(self.client.read()[0])
        except (OSError, ValueError, RuntimeError) as error:
            self.disconnect()
            self.status.set(str(error))

    def disconnect(self) -> None:
        if self.client:
            self.client.close()
        self.client = None

    def apply(self, *, burst: bool = False) -> None:
        if not self.client:
            self.status.set("Effects unavailable: connect the full-profile effects package")
            return
        try:
            values = {
                name: (int if name.endswith("budget") or name == "burst_count" else float)(
                    var.get()
                )
                for name, var in self.values.items()
            }
            config = EffectsConfig(
                **values,
                flags=sum(1 << i for i, flag in enumerate(self.flags) if flag.get()),
                attachment=int(self.attachment.get() == "Selected character root"),
            )
            if burst and not config.flags & 1:
                raise ValueError("Enable effects before triggering a burst")
            sequence = self.client.write(config, burst=burst)
            self.status.set(f"Queued {sequence}; waiting for the next world frame")
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            self.status.set(str(error))

    def disable(self) -> None:
        self.flags[0].set(False)
        if not self.client:
            return
        try:
            # A malformed edit must never prevent the emergency clear action.
            sequence = self.client.write(EffectsConfig())
            self.status.set(f"Disable queued {sequence}")
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            self.status.set(str(error))

    def poll(self) -> None:
        if self.client:
            try:
                _, stats, desired, applied, error = self.client.read()
                self.status.set(
                    f"Sequence {applied}/{desired}; error {error} · particles {stats[0]} "
                    f"· samples {stats[1]}\n"
                    f"Budget drops {stats[2]} · rejected attachments {stats[3]} "
                    f"· resets {stats[4]}\n"
                    f"Degenerate segments {stats[5]} · quads {stats[6]} · rejected draws {stats[7]}"
                )
            except (OSError, ValueError, RuntimeError) as error:
                self.status.set(str(error))
        self.tab.after(500, self.poll)
