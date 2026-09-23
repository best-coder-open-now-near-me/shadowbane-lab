"""Small native Windows UI for the portable vanilla diagnostics release."""

from __future__ import annotations

import json
import os
import queue
import threading
from pathlib import Path
from typing import Any

from .archive import create_portable_archive
from .capture import (
    CaptureConfig,
    assert_required_output_root,
    mark_active_capture,
    run_capture,
)
from .discovery import WindowsProcessDiscovery
from .model import ProcessIdentity
from .package import verify_package
from .preflight import PreflightConfig, run_preflight
from .windows import (
    WindowsNetworkProbe,
    WindowsProcessProbe,
    WindowsWindowInputProbe,
)

_DURATION_CHOICES = {
    "5 minutes": 300.0,
    "10 minutes": 600.0,
    "15 minutes": 900.0,
    "30 minutes": 1800.0,
}


def portable_output_root(package_root: Path, package: dict[str, Any]) -> Path:
    output = package_root / "evidence"
    assert_required_output_root(
        output,
        str(package["required_output_root"]),
        package_root=package_root,
    )
    return output


def run_portable_self_test(package_root: Path, result_path: Path) -> int:
    """Exercise the packaged executable without requiring a running game."""

    payload: dict[str, object]
    try:
        package = verify_package(package_root)
        output = portable_output_root(package_root, package)
        process_id = os.getpid()
        process = WindowsProcessProbe().sample(process_id)
        discovered = WindowsProcessDiscovery().find(Path(process.identity.executable_path).name)
        window = WindowsWindowInputProbe().sample(process_id)
        network = WindowsNetworkProbe().sample(process_id)
        content_safe = (
            window["input_content_captured"] is False
            and network["payload_captured"] is False
        )
        payload = {
            "ok": (
                any(identity.exact_key == process.identity.exact_key for identity in discovered)
                and content_safe
            ),
            "package_id": package["package_id"],
            "package_version": package["package_version"],
            "source_revision": package["source_revision"],
            "output_root": str(output),
            "process_identity": process.identity.as_dict(),
            "window_input_content_captured": window["input_content_captured"],
            "network_payload_captured": network["payload_captured"],
        }
    except Exception as exc:
        payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if payload["ok"] else 2


class PortableDiagnosticsApp:
    def __init__(self, package_root: Path) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._tk = tk
        self._ttk = ttk
        self.package_root = package_root.resolve(strict=True)
        self.package = verify_package(self.package_root)
        self.output_root = portable_output_root(self.package_root, self.package)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.discovery = WindowsProcessDiscovery()
        self.target: ProcessIdentity | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.capture_active = False
        self.close_when_done = False

        root = tk.Tk()
        self.root = root
        root.title("Shadowbane Vanilla Diagnostics")
        root.geometry("760x610")
        root.minsize(680, 540)
        root.protocol("WM_DELETE_WINDOW", self._close_requested)

        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        outer = ttk.Frame(root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="Shadowbane Vanilla Diagnostics",
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Read-only stutter capture for one exact unmodified sb.exe. "
                "No extension, packet payload, key content, or saved pixels."
            ),
            wraplength=710,
        ).pack(anchor="w", pady=(4, 14))

        target_box = ttk.LabelFrame(outer, text="Game", padding=10)
        target_box.pack(fill="x")
        self.target_text = tk.StringVar(value="Looking for sb.exe…")
        ttk.Label(target_box, textvariable=self.target_text, wraplength=600).pack(
            side="left", fill="x", expand=True
        )
        self.refresh_button = ttk.Button(
            target_box,
            text="Refresh",
            command=self.refresh_target,
        )
        self.refresh_button.pack(side="right", padx=(10, 0))

        controls = ttk.LabelFrame(outer, text="Capture", padding=10)
        controls.pack(fill="x", pady=(12, 0))
        ttk.Label(controls, text="Length:").grid(row=0, column=0, sticky="w")
        self.duration_text = tk.StringVar(value="15 minutes")
        self.duration_box = ttk.Combobox(
            controls,
            textvariable=self.duration_text,
            values=tuple(_DURATION_CHOICES),
            state="readonly",
            width=14,
        )
        self.duration_box.grid(row=0, column=1, padx=(6, 16), sticky="w")
        self.preflight_button = ttk.Button(
            controls,
            text="Verify Vanilla Client",
            command=self.start_preflight,
        )
        self.preflight_button.grid(row=0, column=2, padx=(0, 8))
        self.start_button = ttk.Button(
            controls,
            text="Start Capture",
            command=self.start_capture,
        )
        self.start_button.grid(row=0, column=3, padx=(0, 8))
        self.stop_button = ttk.Button(
            controls,
            text="Stop && Seal",
            command=self.stop_capture,
            state="disabled",
        )
        self.stop_button.grid(row=0, column=4)
        controls.columnconfigure(5, weight=1)
        self.progress_text = tk.StringVar(value="Idle")
        ttk.Label(controls, textvariable=self.progress_text).grid(
            row=1,
            column=0,
            columnspan=6,
            sticky="w",
            pady=(10, 0),
        )

        marker_box = ttk.LabelFrame(outer, text="Location markers", padding=10)
        marker_box.pack(fill="x", pady=(12, 0))
        self.marker_buttons: list[Any] = []
        for column, (label, marker) in enumerate(
            (
                ("Baseline SDR", "baseline_sdr"),
                ("Departed SDR", "departed_sdr"),
                ("First Stutter", "first_stutter"),
                ("Turtles Center", "turtles_center"),
            )
        ):
            button = ttk.Button(
                marker_box,
                text=label,
                command=lambda value=marker: self.add_marker(value),
                state="disabled",
            )
            button.grid(row=0, column=column, padx=(0 if column == 0 else 8, 0))
            self.marker_buttons.append(button)

        log_box = ttk.LabelFrame(outer, text="Status", padding=8)
        log_box.pack(fill="both", expand=True, pady=(12, 0))
        self.log = tk.Text(
            log_box,
            height=12,
            state="disabled",
            wrap="word",
            font=("Consolas", 9),
        )
        self.log.pack(fill="both", expand=True)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(
            footer,
            text="Open Evidence Folder",
            command=self.open_evidence,
        ).pack(side="left")
        ttk.Label(
            footer,
            text=(
                f"v{self.package['package_version']} · "
                f"{str(self.package['source_revision'])[:8]}"
            ),
        ).pack(side="right")

        self._append_log(f"Verified portable package in {self.package_root}")
        self._append_log(f"Evidence will be written to {self.output_root}")
        self.refresh_target()
        root.after(150, self._drain_events)

    def run(self) -> None:
        self.root.mainloop()

    def refresh_target(self) -> None:
        try:
            matches = self.discovery.find("sb.exe")
        except Exception as exc:
            self.target = None
            self.target_text.set(f"Could not inspect running processes: {exc}")
            return
        if not matches:
            self.target = None
            self.target_text.set("No running sb.exe found. Start vanilla Shadowbane, then Refresh.")
            return
        if len(matches) > 1:
            self.target = None
            process_ids = ", ".join(str(item.process_id) for item in matches)
            self.target_text.set(
                f"Found multiple sb.exe processes ({process_ids}). Close extras, then Refresh."
            )
            return
        self.target = matches[0]
        self.target_text.set(
            f"PID {self.target.process_id} · {self.target.executable_path}"
        )
        self._append_log(f"Selected exact sb.exe PID {self.target.process_id}")

    def _require_target(self) -> ProcessIdentity | None:
        self.refresh_target()
        if self.target is None:
            self.root.bell()
        return self.target

    def start_preflight(self) -> None:
        target = self._require_target()
        if target is None or self._worker_running():
            return

        def work() -> None:
            try:
                result = run_preflight(
                    PreflightConfig(
                        package_root=self.package_root,
                        output_root=self.output_root,
                        process_id=target.process_id,
                        client_executable=Path(target.executable_path),
                    )
                )
                self.events.put(("log", f"Vanilla preflight accepted: {result}"))
                self.events.put(("worker_done", "Preflight accepted"))
            except Exception as exc:
                self.events.put(("error", f"Preflight rejected: {type(exc).__name__}: {exc}"))
                self.events.put(("worker_done", "Preflight rejected"))

        self._begin_worker(work, "Verifying exact vanilla client…", capture=False)

    def start_capture(self) -> None:
        target = self._require_target()
        if target is None or self._worker_running():
            return
        duration = _DURATION_CHOICES[self.duration_text.get()]
        self.stop_event.clear()

        def work() -> None:
            try:
                result = run_capture(
                    CaptureConfig(
                        package_root=self.package_root,
                        output_root=self.output_root,
                        process_id=target.process_id,
                        client_executable=Path(target.executable_path),
                        duration_seconds=duration,
                    ),
                    stop_requested=self.stop_event.is_set,
                    progress_callback=lambda value: self.events.put(("progress", value)),
                )
                archive, checksum = create_portable_archive(result)
                self.events.put(("log", f"Shareable archive: {archive} ({checksum.name})"))
                self.events.put(("log", f"Capture sealed: {result}"))
                self.events.put(("worker_done", "Capture sealed"))
            except Exception as exc:
                self.events.put(("error", f"Capture failed: {type(exc).__name__}: {exc}"))
                self.events.put(("worker_done", "Capture failed"))

        self._begin_worker(work, "Starting capture…", capture=True)

    def stop_capture(self) -> None:
        if self.capture_active:
            self.stop_event.set()
            self.progress_text.set("Stopping and sealing evidence…")
            self.stop_button.configure(state="disabled")

    def add_marker(self, marker: str) -> None:
        if not self.capture_active:
            return

        def work() -> None:
            try:
                path = mark_active_capture(self.output_root, marker)
                self.events.put(("log", f"Marker added: {marker} ({path.name})"))
            except Exception as exc:
                self.events.put(("error", f"Marker failed: {type(exc).__name__}: {exc}"))

        threading.Thread(target=work, name=f"marker-{marker}", daemon=True).start()

    def open_evidence(self) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        os.startfile(self.output_root)  # type: ignore[attr-defined]

    def _begin_worker(self, target: Any, status: str, *, capture: bool) -> None:
        self.capture_active = capture
        self.progress_text.set(status)
        self._set_primary_controls(enabled=False)
        self.stop_button.configure(state="normal" if capture else "disabled")
        for button in self.marker_buttons:
            button.configure(state="normal" if capture else "disabled")
        self.worker = threading.Thread(target=target, name="diagnostics-worker", daemon=True)
        self.worker.start()

    def _worker_running(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _set_primary_controls(self, *, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.refresh_button.configure(state=state)
        self.preflight_button.configure(state=state)
        self.start_button.configure(state=state)
        self.duration_box.configure(state="readonly" if enabled else "disabled")

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "error":
                    self._append_log(str(payload))
                    self.root.bell()
                elif kind == "progress" and isinstance(payload, dict):
                    self._handle_progress(payload)
                elif kind == "worker_done":
                    self.capture_active = False
                    self._set_primary_controls(enabled=True)
                    self.stop_button.configure(state="disabled")
                    for button in self.marker_buttons:
                        button.configure(state="disabled")
                    self.progress_text.set(str(payload))
                    if self.close_when_done:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self.root.after(150, self._drain_events)

    def _handle_progress(self, payload: dict[str, object]) -> None:
        event = payload.get("event")
        if event == "started":
            self.progress_text.set("Capture active — return to Shadowbane")
        elif event == "progress":
            elapsed = float(payload.get("elapsed_seconds", 0.0))
            self.progress_text.set(
                f"Capture active · {elapsed / 60:.1f} minutes · "
                f"{payload.get('sample_count', 0)} samples"
            )
        elif event == "completed":
            self.progress_text.set(f"Capture {payload.get('terminal_state', 'completed')}")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _close_requested(self) -> None:
        if not self._worker_running():
            self.root.destroy()
            return
        from tkinter import messagebox

        if self.capture_active:
            accepted = messagebox.askyesno(
                "Stop capture?",
                "Stop the active capture, seal its evidence, and close when finished?",
                parent=self.root,
            )
            if not accepted:
                return
            self.close_when_done = True
            self.stop_capture()
            return
        messagebox.showinfo(
            "Please wait",
            "Client verification is still finishing.",
            parent=self.root,
        )


def launch_portable_app(package_root: Path) -> None:
    PortableDiagnosticsApp(package_root).run()


__all__ = [
    "PortableDiagnosticsApp",
    "launch_portable_app",
    "portable_output_root",
    "run_portable_self_test",
]
