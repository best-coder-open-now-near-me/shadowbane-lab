"""Native inspector panel: live controls and offline projected failure inspection."""

from __future__ import annotations

import argparse
import json
import os
import tkinter as tk
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk

from shadowbane_lab.graphics_lab.control import discover_graphics_targets

from .geometry import OVERLAP, Layer, prepare_geometry
from .snapshot import Clearance, Snapshot
from .transport import Channel, Controls

BACKGROUND = "#171b22"
PANEL = "#202630"
TEXT = "#edf1f7"
MUTED = "#9ca9bb"
LAYERS = {
    Layer.RAW: ("Raw search", "#a680ff"),
    Layer.FINAL: ("Movement route", "#33ff73"),
    Layer.CORRIDOR: ("Clearance", "#ffbf40"),
    Layer.PHYSICAL: ("Map blockers", "#ff4d4d"),
    Layer.LEARNED: ("Learned blockers", "#ff994d"),
    Layer.UNCERTAIN: ("Costs / density", "#bfbf59"),
    Layer.OBJECTIVE: ("Goal / waypoint", "#ffffff"),
    Layer.TRAIL: ("Actual trail", "#33d9ff"),
    Layer.EVENTS: ("Events", "#ff4dda"),
}


class InspectorApp:
    def __init__(self, root: tk.Tk, *, discover=discover_graphics_targets):
        self.root, self._discover = root, discover
        self.channel: Channel | None = None
        self.targets = ()
        self.current_snapshot: Snapshot | None = None
        self._loaded: Snapshot | None = None
        self._live: Snapshot | None = None
        self._session = 0
        self._sequence = 0
        self._poll_id = None
        self._zoom = 1.0
        self._center = None
        self._drag = None
        self._timeline = None
        self.root.title("WonderBane Navigation Inspector")
        self.root.geometry("1240x820")
        self.root.minsize(980, 820)
        self.root.configure(background=BACKGROUND)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.target_var = tk.StringVar()
        self.status = tk.StringVar(value="Connect a client or open a saved failure.")
        self.summary = tk.StringVar(value="Projected view · final terrain height is unknown")
        self.enabled = tk.BooleanVar(value=True)
        self.xray = tk.BooleanVar(value=False)
        self.freeze_failure = tk.BooleanVar(value=True)
        self.layers = {layer: tk.BooleanVar(value=True) for layer in LAYERS}
        self.radius = tk.StringVar(value="4")
        self.uncertainty = tk.StringVar(value="1")
        self.margin = tk.StringVar(value="1")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=BACKGROUND, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("TButton", padding=(10, 6))
        style.configure("TCheckbutton", background=BACKGROUND, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure(
            "Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=25
        )
        style.configure("Treeview.Heading", background=PANEL, foreground=TEXT)
        self._build()
        self.refresh_targets()
        self._poll()

    def _build(self):
        header = ttk.Frame(self.root, padding=14)
        header.pack(fill="x")
        ttk.Label(header, text="Navigation inspector", font=("Segoe UI Semibold", 20)).pack(
            side="left"
        )
        ttk.Button(header, text="Open capture", command=self.open_capture).pack(
            side="right", padx=4
        )
        ttk.Button(header, text="Save capture", command=self.save_capture).pack(
            side="right", padx=4
        )
        connections = ttk.Frame(self.root, padding=(14, 0, 14, 10))
        connections.pack(fill="x")
        self.target_box = ttk.Combobox(
            connections, textvariable=self.target_var, state="readonly", width=31
        )
        self.target_box.pack(side="left")
        ttk.Button(connections, text="Refresh", command=self.refresh_targets).pack(
            side="left", padx=4
        )
        ttk.Button(connections, text="Connect", command=self.connect).pack(side="left", padx=4)
        ttk.Button(connections, text="Return to live", command=self.return_live).pack(
            side="left", padx=4
        )
        ttk.Label(self.root, textvariable=self.status, wraplength=1160, foreground=MUTED).pack(
            fill="x", padx=14, pady=(0, 10)
        )
        body = ttk.Frame(self.root, padding=(14, 0, 14, 14))
        body.pack(fill="both", expand=True)
        controls = ttk.Frame(body, width=225)
        controls.pack(side="left", fill="y", padx=(0, 14))
        ttk.Checkbutton(
            controls,
            text="Show in game / arm next run",
            variable=self.enabled,
            command=self.apply_controls,
        ).pack(anchor="w", pady=4)
        ttk.Checkbutton(
            controls,
            text="X-ray measured world trail",
            variable=self.xray,
            command=self.apply_controls,
        ).pack(anchor="w", pady=4)
        ttk.Checkbutton(
            controls,
            text="Freeze on failure",
            variable=self.freeze_failure,
            command=self.apply_controls,
        ).pack(anchor="w", pady=4)
        buttons = ttk.Frame(controls)
        buttons.pack(fill="x", pady=10)
        ttk.Button(buttons, text="Freeze", command=lambda: self.apply_controls(1)).pack(side="left")
        ttk.Button(buttons, text="Resume", command=lambda: self.apply_controls(2)).pack(
            side="left", padx=5
        )
        ttk.Separator(controls).pack(fill="x", pady=8)
        ttk.Label(controls, text="Visible layers", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        for layer, (name, color) in LAYERS.items():
            row = ttk.Frame(controls)
            row.pack(fill="x", pady=3)
            tk.Label(row, text="━", foreground=color, background=BACKGROUND).pack(
                side="left", padx=(0, 6)
            )
            ttk.Checkbutton(
                row, text=name, variable=self.layers[layer], command=self.apply_controls
            ).pack(side="left")
        ttk.Separator(controls).pack(fill="x", pady=10)
        ttk.Label(controls, text="Clearance estimate", font=("Segoe UI Semibold", 12)).pack(
            anchor="w"
        )
        for name, variable in (
            ("Character radius", self.radius),
            ("Movement uncertainty", self.uncertainty),
            ("Extra margin", self.margin),
        ):
            row = ttk.Frame(controls)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=name).pack(side="left")
            ttk.Entry(row, textvariable=variable, width=7).pack(side="right")
        ttk.Button(controls, text="Apply estimate", command=self.apply_controls).pack(
            anchor="e", pady=6
        )
        ttk.Label(
            controls,
            text="World units. This is an estimate,\nnot measured collision geometry.",
            foreground=MUTED,
        ).pack(anchor="w", pady=4)
        ttk.Button(controls, text="Fit view", command=self.fit_view).pack(anchor="w", pady=8)
        ttk.Label(
            controls,
            text="Wheel to zoom · drag to pan\nLT increases right · LG increases up",
            foreground=MUTED,
        ).pack(anchor="w")
        main = ttk.Frame(body)
        main.pack(side="left", fill="both", expand=True)
        ttk.Label(main, textvariable=self.summary, wraplength=890).pack(fill="x", pady=(0, 8))
        self.canvas = tk.Canvas(main, background="#0c1119", highlightthickness=0, height=390)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.render())
        self.canvas.bind("<MouseWheel>", self.zoom)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        tabs = ttk.Notebook(main, height=175)
        tabs.pack(fill="both", pady=(10, 0))
        event_tab, evidence_tab = ttk.Frame(tabs), ttk.Frame(tabs)
        tabs.add(event_tab, text="What happened")
        tabs.add(evidence_tab, text="Evidence and source")
        self.events = ttk.Treeview(
            event_tab, columns=("time", "event", "reason"), show="headings", height=5
        )
        for name, title, width in (
            ("time", "Time", 80),
            ("event", "Event", 160),
            ("reason", "Detail", 530),
        ):
            self.events.heading(name, text=title)
            self.events.column(name, width=width, stretch=name == "reason")
        scroll = ttk.Scrollbar(event_tab, command=self.events.yview)
        self.events.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.events.pack(fill="both", expand=True)
        self.details = tk.Text(
            evidence_tab,
            background=PANEL,
            foreground=TEXT,
            wrap="word",
            font=("Consolas", 10),
            height=7,
            relief="flat",
        )
        self.details.pack(fill="both", expand=True)
        self.details.configure(state="disabled")

    def refresh_targets(self):
        try:
            self.targets = self._discover()
            self.target_box["values"] = tuple(target.label for target in self.targets)
            if len(self.targets) == 1:
                self.target_var.set(self.targets[0].label)
        except Exception as error:
            self.status.set(f"Could not list clients: {error}")

    def connect(self, process_id=None, process_creation_filetime_utc=None):
        selected = (
            [
                target
                for target in self.targets
                if target.process_id == process_id
                and (
                    process_creation_filetime_utc is None
                    or target.process_creation_filetime_utc == process_creation_filetime_utc
                )
            ]
            if process_id is not None
            else [target for target in self.targets if target.label == self.target_var.get()]
        )
        if len(selected) != 1:
            self.status.set("Choose the exact client to record.")
            return
        self.disconnect()
        try:
            self.channel = Channel(selected[0], role="panel")
            defaults = self.channel.startup_controls()
            self._sequence = 0 if defaults is None else defaults.sequence
            self._session = 0
            self._loaded = self._live = self.current_snapshot = None
            self._center = None
            self._zoom = 1
            self.apply_controls()
            self.status.set("Armed for this client. Start /go or /pve to record movement.")
        except (OSError, RuntimeError, ValueError) as error:
            self.disconnect()
            self.status.set(str(error))

    def disconnect(self):
        if self.channel is not None:
            try:
                self._sequence = 2 if self._sequence >= 0xFFFFFFFE else self._sequence + 2
                self.channel.set_controls(Controls(self._sequence, self._session, enabled=False))
            except (OSError, RuntimeError, ValueError):
                pass
            self.channel.close()
            self.channel = None

    def _clearance(self):
        return Clearance(
            float(self.radius.get()), float(self.uncertainty.get()), float(self.margin.get())
        )

    def apply_controls(self, command=0):
        try:
            clearance = self._clearance()
            if self._loaded is not None:
                self._loaded = replace(self._loaded, clearance=clearance)
                self.current_snapshot = self._loaded
                self.render()
                if command:
                    self.status.set(
                        "Saved capture is fixed. Return to live to freeze or resume recording."
                    )
                return
            if self.channel is not None:
                self._sequence = 2 if self._sequence >= 0xFFFFFFFE else self._sequence + 2
                self.channel.set_controls(
                    Controls(
                        self._sequence,
                        self._session,
                        self.enabled.get(),
                        self.xray.get(),
                        self.freeze_failure.get(),
                        command,
                        sum(
                            int(layer) for layer, variable in self.layers.items() if variable.get()
                        ),
                        clearance,
                    )
                )
            self.render()
        except (OSError, RuntimeError, ValueError) as error:
            self.status.set(f"Controls not applied: {error}")

    def _poll(self):
        if self.channel is not None:
            try:
                snapshot, placement = self.channel.read_evidence()
                new_session = snapshot.session_id != self._session
                self._live = snapshot
                self._session = snapshot.session_id
                if self._loaded is None:
                    self.current_snapshot = snapshot
                    if new_session:
                        self._set_estimate(snapshot)
                        self._center = None
                        self.apply_controls()
                    state = "Frozen" if snapshot.frozen else "Recording"
                    self.status.set(
                        f"{state} · {self.channel.target.label}"
                        + (f" · {placement}. Evidence remains available here." if placement else "")
                    )
                    self.render()
            except (OSError, RuntimeError, ValueError) as error:
                if self._loaded is None:
                    self.status.set(str(error))
        self._poll_id = self.root.after(250, self._poll)

    def _set_estimate(self, snapshot):
        self.radius.set(f"{snapshot.clearance.character_radius:g}")
        self.uncertainty.set(f"{snapshot.clearance.movement_uncertainty:g}")
        self.margin.set(f"{snapshot.clearance.margin:g}")

    def load_path(self, path: Path):
        snapshot = Snapshot.load(path)
        self._loaded = self.current_snapshot = snapshot
        self._set_estimate(snapshot)
        self._center = None
        self._zoom = 1
        self.status.set(f"Saved capture · {path.name} · projected evidence only")
        self.render()

    def open_capture(self):
        name = filedialog.askopenfilename(
            parent=self.root, filetypes=[("Inspector capture", "*.json")]
        )
        if name:
            try:
                self.load_path(Path(name))
            except (OSError, ValueError) as error:
                self.status.set(f"Could not open capture: {error}")

    def save_to(self, path: Path):
        if self.current_snapshot is None:
            raise ValueError("There is no capture to save yet.")
        self.current_snapshot.save(path)
        self.status.set(f"Capture saved: {path}")

    def save_capture(self):
        if self.current_snapshot is None:
            self.status.set("There is no capture to save yet.")
            return
        directory = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            / "ShadowbaneLab"
            / "diagnostics"
            / "navigation-inspector"
        )
        try:
            directory.mkdir(parents=True, exist_ok=True)
            name = filedialog.asksaveasfilename(
                parent=self.root,
                initialdir=directory,
                initialfile=f"navigation-{datetime.now():%Y%m%d-%H%M%S}.json",
                defaultextension=".json",
                filetypes=[("Inspector capture", "*.json")],
            )
            if name:
                self.save_to(Path(name))
        except (OSError, ValueError) as error:
            self.status.set(f"Could not save capture: {error}")

    def return_live(self):
        self._loaded = None
        self.current_snapshot = self._live
        self._center = None
        if self._live is not None:
            self._set_estimate(self._live)
        self.status.set(
            "Waiting for live evidence." if self.channel else "Connect a client to record."
        )
        self.apply_controls()
        self.render()

    def _view(self, geometry):
        snapshot = self.current_snapshot
        center = self._center or (
            snapshot.trail[-1][:2]
            if snapshot.trail
            else snapshot.route.start
            if snapshot.route
            else snapshot.plan.start
            if snapshot.plan
            else (0, 0)
        )
        radius = max(
            [50.0]
            + [
                max(abs(p[0] - center[0]), abs(-p[2] - center[1])) + 10
                for line in geometry.lines
                for p in (line.start, line.end)
            ]
        )
        width, height = max(240, self.canvas.winfo_width()), max(200, self.canvas.winfo_height())
        scale = min(width - 40, height - 40) / (2 * radius) * self._zoom
        return center, width, height, scale

    def render(self):
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        snapshot = self.current_snapshot
        if snapshot is None:
            self.events.delete(*self.events.get_children())
            self._timeline = None
            self.summary.set("Projected view · final terrain height is unknown")
            self.details.configure(state="normal")
            self.details.delete("1.0", "end")
            self.details.configure(state="disabled")
            self.canvas.create_text(
                22,
                22,
                anchor="nw",
                fill=MUTED,
                font=("Segoe UI", 13),
                text="Connect a client or open a saved capture.",
            )
            return
        geometry = prepare_geometry(snapshot)
        center, width, height, scale = self._view(geometry)

        def point(value):
            return (
                width / 2 + (value[0] - center[0]) * scale,
                height / 2 + (value[2] + center[1]) * scale,
            )

        last_key = last_end = None
        points = []

        def flush():
            if points:
                self.canvas.create_line(*points, fill=last_key[1], width=1.5)

        for line in geometry.lines:
            if not self.layers[Layer(line.layer)].get():
                continue
            color = "#ff3029" if line.flags & OVERLAP else LAYERS[Layer(line.layer)][1]
            key = (line.layer, color)
            if key != last_key or line.start != last_end:
                flush()
                points = [*point(line.start)]
            points.extend(point(line.end))
            last_key, last_end = key, line.end
        flush()
        self.canvas.create_text(
            14,
            14,
            anchor="nw",
            fill=MUTED,
            font=("Segoe UI", 10),
            text="Projected map · terrain height unknown",
        )
        overlaps = len(
            set(geometry.audit.physical_overlap_segments)
            | set(geometry.audit.learned_overlap_segments)
        )
        audit = (
            "Obstacle model unavailable"
            if snapshot.plan is None
            else (
                f"Modeled overlap on {overlaps} segment(s)"
                if overlaps
                else "No overlap in the captured model"
            )
        )
        loss = (
            geometry.omitted_lines
            + snapshot.omitted_events
            + snapshot.omitted_trail
            + snapshot.dropped_observations
        )
        self.summary.set(
            f"{audit} · clearance estimate {snapshot.clearance.radius:g} units"
            + (f" · {loss} omitted/dropped display or history items" if loss else "")
            + (" · map/search capture truncated" if geometry.audit.model_truncated else "")
        )
        if self._timeline != snapshot.events:
            self.events.delete(*self.events.get_children())
            for event in snapshot.events:
                value = event.value
                self.events.insert(
                    "",
                    "end",
                    values=(
                        f"{value.now_ms / 1000:.2f}s",
                        value.event.replace("_", " "),
                        value.reason or "",
                    ),
                )
            self.events.yview_moveto(1)
            self._timeline = snapshot.events
        detail = {
            "zone": snapshot.context.zone_token,
            "map evidence": snapshot.context.obstacle_provenance,
            "height": snapshot.context.height_provenance,
            "last search": None if snapshot.plan is None else snapshot.plan.mode,
            "search failure": None if snapshot.plan is None else snapshot.plan.failure_reason,
            "movement route": None if snapshot.route is None else snapshot.route.plan_id,
            "clearance": asdict(snapshot.clearance),
            "map revision": snapshot.map_revision,
            "route revision": snapshot.route_revision,
            "coordinates": snapshot.coordinate_convention,
            "source": asdict(snapshot.identity),
            "interpretation": geometry.audit.note,
        }
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", json.dumps(detail, indent=2))
        self.details.configure(state="disabled")

    def fit_view(self):
        self._zoom, self._center = 1, None
        self.render()

    def zoom(self, event):
        self._zoom = min(64, max(0.1, self._zoom * (1.25 if event.delta > 0 else 0.8)))
        self.render()

    def start_drag(self, event):
        if self.current_snapshot is not None:
            center, _width, _height, scale = self._view(prepare_geometry(self.current_snapshot))
            self._drag = (event.x, event.y, center, scale)

    def drag(self, event):
        if self._drag is not None:
            x, y, center, scale = self._drag
            self._center = (center[0] - (event.x - x) / scale, center[1] + (event.y - y) / scale)
            self.render()

    def close(self):
        if self._poll_id is not None:
            self.root.after_cancel(self._poll_id)
        self.disconnect()
        self.root.destroy()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inspect live navigation or a saved failure.")
    parser.add_argument("--pid", type=int, help="Exact client process to connect")
    parser.add_argument(
        "--process-creation-filetime", type=int, help="Require this process lifetime"
    )
    parser.add_argument("--open", type=Path, dest="capture", help="Open a saved capture")
    arguments = parser.parse_args(argv)
    if arguments.process_creation_filetime is not None and arguments.pid is None:
        parser.error("--process-creation-filetime requires --pid")
    root = tk.Tk()
    app = InspectorApp(root)
    if arguments.capture is not None:
        try:
            app.load_path(arguments.capture)
        except (OSError, ValueError) as error:
            app.status.set(f"Could not open capture: {error}")
    elif arguments.pid is not None:
        app.connect(arguments.pid, arguments.process_creation_filetime)
    root.mainloop()
    return 0
