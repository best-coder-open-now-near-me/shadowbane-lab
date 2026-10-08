"""Selected-object inspection in Graphics Lab; frozen reports, no game writes."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import IntVar, StringVar, Text, filedialog, ttk

from .visual_inspector import VisualInspectorClient, enrich


class VisualPanel:
    def __init__(self, notebook):
        self.frame = ttk.Frame(notebook, padding=12)
        notebook.add(self.frame, text="Visuals")
        self.client = None
        self.pending = None
        self.future = None
        self.report = None
        self.executor = None
        self.selection = IntVar(value=1)
        self.folder = StringVar()
        self.status = StringVar(value="Connect a game instance, then capture its selected object.")
        row = ttk.Frame(self.frame)
        row.pack(fill="x")
        for value, label in enumerate(("My character", "Selected object")):
            ttk.Radiobutton(row, text=label, variable=self.selection, value=value).pack(side="left")
        self.capture_button = ttk.Button(
            row, text="Capture", command=self.capture, state="disabled"
        )
        self.capture_button.pack(side="right")
        ttk.Label(self.frame, text="Client cache folder", style="Muted.TLabel").pack(
            anchor="w", pady=(8, 0)
        )
        folder_row = ttk.Frame(self.frame)
        folder_row.pack(fill="x")
        ttk.Entry(folder_row, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(folder_row, text="Browse…", command=self.browse).pack(side="right")
        ttk.Label(self.frame, textvariable=self.status, wraplength=620).pack(fill="x", pady=8)
        tree_frame = ttk.Frame(self.frame)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=("bone", "names"), height=8)
        self.tree.heading("#0", text="Live render tree")
        self.tree.heading("bone", text="Attachment")
        self.tree.heading("names", text="Candidate names")
        self.tree.column("#0", width=185, minwidth=100)
        self.tree.column("bone", width=80, minwidth=50)
        self.tree.column("names", width=235, minwidth=100)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.show_details)
        ttk.Label(self.frame, text="Resource details", style="Muted.TLabel").pack(
            anchor="w", pady=(8, 0)
        )
        detail_frame = ttk.Frame(self.frame)
        detail_frame.pack(fill="both", expand=True)
        self.details = Text(detail_frame, height=10, width=55, wrap="word", state="disabled")
        detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.details.yview)
        self.details.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side="right", fill="y")
        self.details.pack(fill="both", expand=True)
        self.export_button = ttk.Button(
            self.frame, text="Save snapshot…", command=self.export, state="disabled"
        )
        self.export_button.pack(anchor="e", pady=(8, 0))
        self.frame.bind("<Destroy>", self.destroyed, add=True)
        self.poll_after = self.frame.after(100, self.poll)

    def browse(self):
        path = filedialog.askdirectory(parent=self.frame, title="Choose the client's cache folder")
        if path:
            self.folder.set(path)

    def clear(self):
        self.report = None
        self.tree.delete(*self.tree.get_children())
        self.set_details("")
        self.export_button.configure(state="disabled")

    def connect(self, target):
        self.disconnect()
        root = target.executable_path.parent
        choices = [root / "cache", root / "Cache", root]
        self.folder.set(
            str(next((p for p in choices if (p / "Render.cache").is_file()), choices[0]))
        )
        try:
            self.client = VisualInspectorClient(target)
            self.capture_button.configure(state="normal")
            self.status.set("Select an object in game, then press Capture. Nothing is modified.")
        except (OSError, ValueError) as error:
            self.status.set(str(error))

    def disconnect(self):
        self.pending = None
        if self.future:
            self.future.cancel()
            self.future = None
        if self.client:
            self.client.close()
            self.client = None
        self.capture_button.configure(state="disabled")
        self.clear()
        self.status.set("Connect a game instance to inspect visuals.")

    def capture(self):
        if not self.client or self.pending or self.future:
            return
        self.clear()
        try:
            sequence = self.client.request(self.selection.get())
            self.pending = (sequence, time.monotonic() + 8, self.folder.get())
            self.capture_button.configure(state="disabled")
            self.status.set("Waiting for the next game scene…")
        except (OSError, ValueError, TimeoutError) as error:
            self.status.set(str(error))

    def poll(self):
        try:
            if self.pending and self.client:
                sequence, deadline, folder = self.pending
                snapshot = self.client.read()
                if snapshot["request"] != sequence:
                    raise ValueError("Another panel replaced this request; capture again")
                if snapshot["applied"] == sequence:
                    self.pending = None
                    if snapshot["status"]:
                        raise ValueError(snapshot["status_text"])
                    if self.executor is None:
                        self.executor = ThreadPoolExecutor(
                            max_workers=1, thread_name_prefix="visual-cache"
                        )
                    self.future = self.executor.submit(enrich, snapshot, folder)
                    self.status.set("Resolving captured references in the local caches…")
                elif time.monotonic() > deadline:
                    raise TimeoutError(
                        "No game scene received. Bring the game into the world and capture again."
                    )
            if self.future and self.future.done():
                future, self.future = self.future, None
                self.display(future.result())
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            self.pending = None
            self.status.set(str(error))
        if self.client and not self.pending and not self.future:
            self.capture_button.configure(state="normal")
        self.poll_after = self.frame.after(100, self.poll)

    def display(self, report):
        self.clear()
        self.report = report
        for row in report["nodes"]:
            templates = row.get("templates", [])
            bones = sorted({t.get("target_bone", "") for t in templates} - {""})
            names = sorted({c["name"] for t in templates for c in t.get("object_candidates", [])})
            self.tree.insert(
                "" if row["parent"] is None else str(row["parent"]),
                "end",
                iid=str(row["index"]),
                text=f"Render {row['render_id']}",
                values=(", ".join(bones) or "—", ", ".join(names) or "—"),
                open=True,
            )
        owner = "Self" if report["selection"] == 0 else "Selected object"
        warnings = report.get("warnings", [])
        self.status.set(
            f"Frozen capture · {owner} {report['object_type']}:{report['object_uuid']} · "
            f"{len(report['nodes'])} render nodes. Capture again after changing selection."
            + (" " + "; ".join(warnings) if warnings else "")
        )
        self.export_button.configure(state="normal")
        if report["nodes"]:
            self.tree.selection_set("0")
            self.show_details()

    def set_details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def show_details(self, *_):
        selected = self.tree.selection()
        if not selected or not self.report:
            return
        row = self.report["nodes"][int(selected[0])]
        lines = [
            row.get("resolution", ""),
            "Template references describe cached assets. Equipment names are candidates; "
            "slots and live texture overrides are not verified.",
        ]
        for template in row.get("templates", []):
            lines.append(f"\nRender {template['render_key']}")
            if "error" in template:
                lines.append(template["error"])
                continue
            for field, label in (
                ("target_bone", "Attachment bone"),
                ("mesh_keys", "Meshes"),
                ("texture_keys", "Texture layers"),
                ("specular_key", "Specular"),
                ("child_keys", "Template children"),
            ):
                value = template.get(field, "")
                lines.append(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
            lines += [
                f"Candidate {c['key']}: {c['name']} (type {c['object_type']})"
                for c in template.get("object_candidates", [])
            ]
            lines += template.get("missing_resources", [])
        lines.append("\nEffects and gameplay item stats are not inferred from this render tree.")
        self.set_details("\n".join(lines))

    def export(self):
        if not self.report:
            return
        path = filedialog.asksaveasfilename(
            parent=self.frame,
            title="Save local visual snapshot",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if path:
            try:
                # Exclusive creation protects existing reports and arbitrary client files.
                with Path(path).open("x", encoding="utf-8") as stream:
                    json.dump(self.report, stream, indent=2)
            except OSError as error:
                self.status.set(f"Could not save snapshot: {error}")

    def destroyed(self, event):
        if event.widget == self.frame:
            self.frame.after_cancel(self.poll_after)
            if self.client:
                self.client.close()
                self.client = None
            if self.executor:
                self.executor.shutdown(wait=False, cancel_futures=True)
