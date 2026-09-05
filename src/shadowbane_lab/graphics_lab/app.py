"""Small native panel for live WonderBane graphics art direction."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from .control import (
    ADAPTIVE_OUTLINES,
    BANDED_LIGHTING,
    DEFAULT_PARAMETERS,
    DEPTH_CONTOUR_DEBUG_NONE,
    DEPTH_CONTOUR_DEBUG_REJECTED,
    DEPTH_CONTOUR_DEBUG_RESPONSE,
    DEPTH_CONTOUR_DEBUG_SUPPORT,
    DEPTH_CONTOUR_DEBUG_SUSTAINED_RESPONSE,
    DEPTH_CONTOUR_LEGACY,
    DEPTH_CONTOUR_SUSTAINED,
    DEPTH_CONTOURS,
    FEATURE_ACCENTS,
    GraphicsControlClient,
    GraphicsControlTarget,
    GraphicsParameters,
    discover_graphics_targets,
    normalize_fixed_accent_controls,
    target_process_is_alive,
)
from .presets import GraphicsPresetStore
from .selected_cue import CuePanel

_BACKGROUND = "#171b22"
_PANEL = "#202630"
_TEXT = "#edf1f7"
_MUTED = "#9ca9bb"
_ACCENT = "#a995d6"
_ERROR = "#ff8d8d"

_CONTOUR_DEBUG_LABELS = {
    "Off": DEPTH_CONTOUR_DEBUG_NONE,
    "Raw response": DEPTH_CONTOUR_DEBUG_RESPONSE,
    "Sustained response": DEPTH_CONTOUR_DEBUG_SUSTAINED_RESPONSE,
    "Sustained support": DEPTH_CONTOUR_DEBUG_SUPPORT,
    "Rejected candidates": DEPTH_CONTOUR_DEBUG_REJECTED,
}


class GraphicsLabApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("WonderBane Graphics Lab")
        self.root.geometry("640x790")
        self.root.minsize(600, 700)
        self.root.configure(background=_BACKGROUND)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.targets: tuple[GraphicsControlTarget, ...] = ()
        self.client: GraphicsControlClient | None = None
        self.pending_sequence: int | None = None
        self._apply_after: str | None = None
        self._suspend_updates = False
        self._color_values: dict[str, tuple[float, float, float]] = {}
        self._color_buttons: dict[str, tk.Button] = {}
        self._preset_store = GraphicsPresetStore()
        self._poll_count = 0
        self._configure_style()
        self._create_variables()
        self._build()
        self._set_parameters(DEFAULT_PARAMETERS)
        self.refresh_targets()
        self._poll_acknowledgement()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=_BACKGROUND, foreground=_TEXT)
        style.configure("TFrame", background=_BACKGROUND)
        style.configure("Panel.TFrame", background=_PANEL)
        style.configure(
            "TLabel", background=_BACKGROUND, foreground=_TEXT, font=("Segoe UI", 10)
        )
        style.configure(
            "Muted.TLabel", background=_BACKGROUND, foreground=_MUTED, font=("Segoe UI", 9)
        )
        style.configure(
            "Title.TLabel",
            background=_BACKGROUND,
            foreground=_TEXT,
            font=("Segoe UI Semibold", 18),
        )
        style.configure("TCheckbutton", background=_BACKGROUND, foreground=_TEXT)
        style.map("TCheckbutton", background=[("active", _BACKGROUND)])
        style.configure("TButton", padding=(10, 6))
        style.configure("Accent.TButton", background=_ACCENT, foreground="#11141a")
        style.map("Accent.TButton", background=[("active", "#b8a7df")])
        style.configure("TNotebook", background=_BACKGROUND, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=_PANEL,
            foreground=_MUTED,
            padding=(14, 8),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#2b3340")],
            foreground=[("selected", _TEXT)],
        )

    def _create_variables(self) -> None:
        self.target_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Looking for a live graphics client…")
        self.preset_name_var = tk.StringVar()
        self.preset_choice_var = tk.StringVar()
        self.sustained_contours_var = tk.BooleanVar()
        self.contour_debug_var = tk.StringVar(value="Off")
        self.flag_vars = {
            BANDED_LIGHTING: tk.BooleanVar(),
            DEPTH_CONTOURS: tk.BooleanVar(),
            FEATURE_ACCENTS: tk.BooleanVar(),
            ADAPTIVE_OUTLINES: tk.BooleanVar(),
        }
        self.numeric_vars = {
            "dark_scene_outline_strength": tk.DoubleVar(),
            "bright_scene_ink_alpha": tk.DoubleVar(),
            "depth_edge_threshold": tk.DoubleVar(),
            "sustained_edge_threshold": tk.DoubleVar(),
            "band_threshold_0": tk.DoubleVar(),
            "band_threshold_1": tk.DoubleVar(),
            "band_threshold_2": tk.DoubleVar(),
            "vertex_tint_gamma": tk.DoubleVar(),
            "distant_highlight_compression": tk.DoubleVar(),
        }
        for variable in [
            *self.flag_vars.values(),
            *self.numeric_vars.values(),
            self.sustained_contours_var,
            self.contour_debug_var,
        ]:
            variable.trace_add("write", self._schedule_live_apply)

    def _build(self) -> None:
        container = ttk.Frame(self.root, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="WonderBane Graphics Lab", style="Title.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            container,
            text="Live frame-boundary art direction · no game restart",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 14))
        target_row = ttk.Frame(container)
        target_row.pack(fill="x", pady=(0, 8))
        self.target_combo = ttk.Combobox(
            target_row, textvariable=self.target_var, state="readonly"
        )
        self.target_combo.pack(side="left", fill="x", expand=True)
        self.target_combo.bind("<<ComboboxSelected>>", self._connect_selected)
        ttk.Button(target_row, text="Refresh", command=self.refresh_targets).pack(
            side="left", padx=(8, 0)
        )
        self.status_label = ttk.Label(
            container, textvariable=self.status_var, style="Muted.TLabel"
        )
        self.status_label.pack(anchor="w", pady=(0, 10))
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)
        outline_tab = ttk.Frame(notebook, padding=16)
        lighting_tab = ttk.Frame(notebook, padding=16)
        preset_tab = ttk.Frame(notebook, padding=16)
        notebook.add(outline_tab, text="Outlines")
        notebook.add(lighting_tab, text="Cel lighting")
        notebook.add(preset_tab, text="Presets")
        self._build_outline_tab(outline_tab)
        self._build_lighting_tab(lighting_tab)
        self._build_preset_tab(preset_tab)
        self.cue_panel = CuePanel(notebook, lambda: self.client.target if self.client else None)

    def _build_outline_tab(self, parent: ttk.Frame) -> None:
        ttk.Checkbutton(
            parent,
            text="Adaptive light-on-dark / dark-on-light silhouettes",
            variable=self.flag_vars[ADAPTIVE_OUTLINES],
        ).pack(anchor="w", pady=(0, 8))
        ttk.Checkbutton(
            parent,
            text="Depth-based silhouettes and seams",
            variable=self.flag_vars[DEPTH_CONTOURS],
        ).pack(anchor="w")
        ttk.Checkbutton(
            parent,
            text="Reject one-pixel depth cracks (experimental)",
            variable=self.sustained_contours_var,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            parent,
            text="Interior accents · black, fixed 1 px",
            variable=self.flag_vars[FEATURE_ACCENTS],
        ).pack(anchor="w", pady=(4, 16))
        self._color_control(parent, "dark_scene_outline", "Dark-scene rim tint")
        self._slider(parent, "dark_scene_outline_strength", "Dark-scene rim strength", 0.0, 1.0, 2)
        self._slider(parent, "bright_scene_ink_alpha", "Bright-scene ink amount", 0.0, 1.0, 2)
        self._slider(
            parent,
            "depth_edge_threshold",
            "Edge threshold · lower reveals more detail",
            0.005,
            0.20,
            3,
        )
        self._slider(
            parent,
            "sustained_edge_threshold",
            "Sustained support threshold",
            0.005,
            0.20,
            3,
        )
        diagnostic_row = ttk.Frame(parent)
        diagnostic_row.pack(fill="x", pady=5)
        ttk.Label(diagnostic_row, text="Contour diagnostic view").pack(anchor="w")
        ttk.Combobox(
            diagnostic_row,
            textvariable=self.contour_debug_var,
            values=tuple(_CONTOUR_DEBUG_LABELS),
            state="readonly",
        ).pack(fill="x", pady=(3, 0))
        ttk.Label(
            parent,
            text=(
                "Rim tint affects dark-surface outer outlines, not interior accents.\n"
                "Interior accents currently have an on/off control only."
            ),
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(12, 0))

    def _build_lighting_tab(self, parent: ttk.Frame) -> None:
        ttk.Checkbutton(
            parent,
            text="Normal-driven cel lighting",
            variable=self.flag_vars[BANDED_LIGHTING],
        ).pack(anchor="w", pady=(0, 12))
        colors = ttk.Frame(parent)
        colors.pack(fill="x")
        for key, label in (
            ("band_color_0", "Shadow"),
            ("band_color_1", "Low"),
            ("band_color_2", "Mid"),
            ("band_color_3", "Highlight"),
        ):
            frame = ttk.Frame(colors)
            frame.pack(side="left", fill="x", expand=True, padx=(0, 6))
            self._color_control(frame, key, label, compact=True)
        ttk.Separator(parent).pack(fill="x", pady=12)
        self._slider(parent, "band_threshold_0", "Shadow → low threshold", 0.05, 0.80, 2)
        self._slider(parent, "band_threshold_1", "Low → mid threshold", 0.10, 0.90, 2)
        self._slider(parent, "band_threshold_2", "Mid → highlight threshold", 0.20, 0.98, 2)
        self._slider(parent, "vertex_tint_gamma", "World-light response gamma", 0.25, 2.5, 2)
        self._slider(
            parent,
            "distant_highlight_compression",
            "Distant highlight compression",
            0.0,
            1.0,
            2,
        )

    def _build_preset_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text=(
                "Presets contain only reviewed visual parameters. Loading one updates the "
                "attached client on the next frame."
            ),
            style="Muted.TLabel",
            wraplength=520,
        ).pack(anchor="w", pady=(0, 16))
        ttk.Label(parent, text="Saved presets").pack(anchor="w")
        self.preset_combo = ttk.Combobox(
            parent, textvariable=self.preset_choice_var, state="readonly"
        )
        self.preset_combo.pack(fill="x", pady=(4, 8))
        ttk.Button(parent, text="Load selected preset", command=self._load_preset).pack(
            anchor="w"
        )
        ttk.Separator(parent).pack(fill="x", pady=18)
        ttk.Label(parent, text="Save current look as").pack(anchor="w")
        ttk.Entry(parent, textvariable=self.preset_name_var).pack(fill="x", pady=(4, 8))
        ttk.Button(
            parent, text="Save preset", style="Accent.TButton", command=self._save_preset
        ).pack(anchor="w")
        ttk.Separator(parent).pack(fill="x", pady=18)
        ttk.Button(
            parent,
            text="Reset to reviewed visual baseline",
            command=lambda: self._set_parameters(DEFAULT_PARAMETERS, apply=True),
        ).pack(anchor="w")
        self._refresh_presets()

    def _slider(
        self,
        parent: ttk.Frame,
        key: str,
        label: str,
        minimum: float,
        maximum: float,
        digits: int,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=5)
        label_row = ttk.Frame(row)
        label_row.pack(fill="x")
        ttk.Label(label_row, text=label).pack(side="left")
        value_var = tk.StringVar()
        ttk.Label(label_row, textvariable=value_var, style="Muted.TLabel").pack(side="right")
        def update_value(*_: object) -> None:
            value_var.set(f"{self.numeric_vars[key].get():.{digits}f}")

        scale = ttk.Scale(
            row,
            from_=minimum,
            to=maximum,
            variable=self.numeric_vars[key],
        )
        scale.pack(fill="x", pady=(2, 0))
        self.numeric_vars[key].trace_add("write", update_value)
        update_value()

    def _color_control(
        self, parent: ttk.Frame, key: str, label: str, *, compact: bool = False
    ) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, 8))
        ttk.Label(frame, text=label).pack(anchor="center" if compact else "w")
        button = tk.Button(
            frame,
            text="#000000",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=7,
            command=lambda: self._choose_color(key),
        )
        button.pack(fill="x", pady=(3, 0))
        self._color_buttons[key] = button

    def refresh_targets(self) -> None:
        try:
            targets = discover_graphics_targets()
        except (OSError, RuntimeError) as error:
            targets = ()
            self._show_status(str(error), error=True)
        self.targets = targets
        self.target_combo.configure(values=[target.label for target in targets])
        if not targets:
            self._disconnect()
            self.target_var.set("")
            self._show_status("No verified graphics client is publishing live controls.")
            return
        current_identity = (
            None
            if self.client is None
            else (
                self.client.target.process_id,
                self.client.target.process_creation_filetime_utc,
            )
        )
        selected = next(
            (
                index
                for index, target in enumerate(targets)
                if (target.process_id, target.process_creation_filetime_utc)
                == current_identity
            ),
            0,
        )
        self.target_combo.current(selected)
        self._connect_target(targets[selected])

    def _connect_selected(self, _: object = None) -> None:
        index = self.target_combo.current()
        if 0 <= index < len(self.targets):
            self._connect_target(self.targets[index])

    def _connect_target(self, target: GraphicsControlTarget) -> None:
        self._disconnect()
        try:
            self.client = GraphicsControlClient(target)
        except (OSError, RuntimeError, ValueError) as error:
            self.client = None
            self._show_status(f"Attach failed: {error}", error=True)
            return
        try:
            snapshot = self.client.read()
        except ValueError as error:
            try:
                self.pending_sequence = self.client.restore_reviewed_baseline()
            except (OSError, RuntimeError, TimeoutError, ValueError) as repair_error:
                self._disconnect()
                self._show_status(
                    f"Attach failed: {error}; baseline restore failed: {repair_error}",
                    error=True,
                )
                return
            self._set_parameters(DEFAULT_PARAMETERS)
            self._show_status(
                "Restored invalid live controls to the reviewed visual baseline "
                f"· queued sequence {self.pending_sequence}"
            )
            return
        self.pending_sequence = None
        self._set_parameters(snapshot.parameters)
        self._show_status(
            f"Attached to PID {target.process_id} · sequence {snapshot.applied_sequence}"
        )

    def _disconnect(self) -> None:
        if hasattr(self, "cue_panel"):
            self.cue_panel.disconnect()
        if self.client is not None:
            self.client.close()
            self.client = None
        self.pending_sequence = None

    def _schedule_live_apply(self, *_: object) -> None:
        if self._suspend_updates or self.client is None:
            return
        if self._apply_after is not None:
            self.root.after_cancel(self._apply_after)
        self._apply_after = self.root.after(60, self._apply_live)

    def _apply_live(self) -> None:
        self._apply_after = None
        if self.client is None:
            return
        try:
            self.pending_sequence = self.client.write(self._parameters_from_ui())
            self._show_status(f"Queued sequence {self.pending_sequence}…")
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            self._show_status(str(error), error=True)

    def _parameters_from_ui(self) -> GraphicsParameters:
        flags = sum(flag for flag, variable in self.flag_vars.items() if variable.get())
        parameters = GraphicsParameters(
            flags=flags,
            dark_scene_outline=self._color_values["dark_scene_outline"],
            dark_scene_outline_strength=self.numeric_vars[
                "dark_scene_outline_strength"
            ].get(),
            bright_scene_ink_alpha=self.numeric_vars["bright_scene_ink_alpha"].get(),
            depth_edge_threshold=self.numeric_vars["depth_edge_threshold"].get(),
            band_thresholds=(
                self.numeric_vars["band_threshold_0"].get(),
                self.numeric_vars["band_threshold_1"].get(),
                self.numeric_vars["band_threshold_2"].get(),
            ),
            band_colors=(
                self._color_values["band_color_0"],
                self._color_values["band_color_1"],
                self._color_values["band_color_2"],
                self._color_values["band_color_3"],
            ),
            vertex_tint_gamma=self.numeric_vars["vertex_tint_gamma"].get(),
            distant_highlight_compression=self.numeric_vars[
                "distant_highlight_compression"
            ].get(),
            feature_outline_width=1.0,
            sustained_edge_threshold=self.numeric_vars[
                "sustained_edge_threshold"
            ].get(),
            depth_contour_mode=(
                DEPTH_CONTOUR_SUSTAINED
                if self.sustained_contours_var.get()
                else DEPTH_CONTOUR_LEGACY
            ),
            depth_contour_debug_mode=_CONTOUR_DEBUG_LABELS[
                self.contour_debug_var.get()
            ],
        )
        parameters.validate()
        return parameters

    def _set_parameters(self, parameters: GraphicsParameters, *, apply: bool = False) -> None:
        parameters = normalize_fixed_accent_controls(parameters)
        self._suspend_updates = True
        try:
            for flag, variable in self.flag_vars.items():
                variable.set(bool(parameters.flags & flag))
            self.sustained_contours_var.set(
                parameters.depth_contour_mode == DEPTH_CONTOUR_SUSTAINED
            )
            debug_label = next(
                (
                    label
                    for label, mode in _CONTOUR_DEBUG_LABELS.items()
                    if mode == parameters.depth_contour_debug_mode
                ),
                "Off",
            )
            self.contour_debug_var.set(debug_label)
            values = {
                "dark_scene_outline_strength": parameters.dark_scene_outline_strength,
                "bright_scene_ink_alpha": parameters.bright_scene_ink_alpha,
                "depth_edge_threshold": parameters.depth_edge_threshold,
                "sustained_edge_threshold": parameters.sustained_edge_threshold,
                "band_threshold_0": parameters.band_thresholds[0],
                "band_threshold_1": parameters.band_thresholds[1],
                "band_threshold_2": parameters.band_thresholds[2],
                "vertex_tint_gamma": parameters.vertex_tint_gamma,
                "distant_highlight_compression": parameters.distant_highlight_compression,
            }
            for key, value in values.items():
                self.numeric_vars[key].set(value)
            colors = {
                "dark_scene_outline": parameters.dark_scene_outline,
                "band_color_0": parameters.band_colors[0],
                "band_color_1": parameters.band_colors[1],
                "band_color_2": parameters.band_colors[2],
                "band_color_3": parameters.band_colors[3],
            }
            for key, color in colors.items():
                self._set_color(key, color)
        finally:
            self._suspend_updates = False
        if apply:
            self._apply_live()

    def _choose_color(self, key: str) -> None:
        _, chosen = colorchooser.askcolor(
            initialcolor=_color_hex(self._color_values[key]), parent=self.root
        )
        if chosen:
            self._set_color(key, _hex_color(chosen))
            self._schedule_live_apply()

    def _set_color(self, key: str, color: tuple[float, float, float]) -> None:
        self._color_values[key] = color
        hex_value = _color_hex(color)
        luminance = color[0] * 0.2126 + color[1] * 0.7152 + color[2] * 0.0722
        foreground = "#101319" if luminance > 0.55 else "#f4f6fa"
        self._color_buttons[key].configure(
            text=hex_value.upper(),
            background=hex_value,
            activebackground=hex_value,
            foreground=foreground,
            activeforeground=foreground,
        )

    def _poll_acknowledgement(self) -> None:
        self._poll_count += 1
        if self.client is None and self._poll_count % 5 == 0:
            self.refresh_targets()
        if self.client is not None:
            try:
                if self._poll_count % 5 == 0 and not target_process_is_alive(
                    self.client.target
                ):
                    raise RuntimeError("the exact sb.exe process has exited")
                snapshot = self.client.read()
                if (
                    self.pending_sequence is not None
                    and snapshot.rejected_sequence == self.pending_sequence
                ):
                    self._show_status(
                        f"Sequence {self.pending_sequence} rejected · Win32 "
                        f"{snapshot.last_error}",
                        error=True,
                    )
                    self.pending_sequence = None
                elif (
                    self.pending_sequence is not None
                    and snapshot.applied_sequence == self.pending_sequence
                ):
                    self._show_status(
                        f"Applied sequence {self.pending_sequence} on the frame boundary"
                    )
                    self.pending_sequence = None
            except (OSError, RuntimeError, ValueError) as error:
                self._show_status(f"Client detached: {error}", error=True)
                self._disconnect()
        self.root.after(200, self._poll_acknowledgement)

    def _save_preset(self) -> None:
        try:
            parameters = self._parameters_from_ui()
            path = self._preset_store.save(self.preset_name_var.get(), parameters)
        except (OSError, ValueError) as error:
            messagebox.showerror("Preset not saved", str(error), parent=self.root)
            return
        self.preset_name_var.set(path.stem)
        self._refresh_presets(select=path.stem)
        self._show_status(f"Saved preset {path.stem!r}")

    def _load_preset(self) -> None:
        try:
            parameters = self._preset_store.load(self.preset_choice_var.get())
        except (OSError, ValueError) as error:
            messagebox.showerror("Preset not loaded", str(error), parent=self.root)
            return
        self._set_parameters(parameters, apply=True)

    def _refresh_presets(self, *, select: str | None = None) -> None:
        names = self._preset_store.list_names()
        self.preset_combo.configure(values=names)
        if select in names:
            self.preset_choice_var.set(select)
        elif names and self.preset_choice_var.get() not in names:
            self.preset_choice_var.set(names[0])
        elif not names:
            self.preset_choice_var.set("")

    def _show_status(self, text: str, *, error: bool = False) -> None:
        self.status_var.set(text)
        self.status_label.configure(foreground=_ERROR if error else _MUTED)

    def close(self) -> None:
        if self._apply_after is not None:
            self.root.after_cancel(self._apply_after)
        self._disconnect()
        self.cue_panel.close()
        self.root.destroy()


def _color_hex(color: tuple[float, float, float]) -> str:
    channels = [max(0, min(255, round(channel * 255))) for channel in color]
    return f"#{channels[0]:02x}{channels[1]:02x}{channels[2]:02x}"


def _hex_color(value: str) -> tuple[float, float, float]:
    text = value.removeprefix("#")
    if len(text) != 6:
        raise ValueError("color must be a six-digit RGB value")
    return (
        int(text[0:2], 16) / 255.0,
        int(text[2:4], 16) / 255.0,
        int(text[4:6], 16) / 255.0,
    )


def main() -> int:
    root = tk.Tk()
    GraphicsLabApp(root)
    root.mainloop()
    return 0
