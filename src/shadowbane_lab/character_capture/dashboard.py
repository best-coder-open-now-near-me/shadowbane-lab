"""Local tester dashboard for both Wonderbane and private Shadowbane recordings."""

from __future__ import annotations

import argparse
import os
import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .watcher import Watcher


class Dashboard:
    def __init__(self, root, output):
        self.root, self.output, self.watcher = root, output, None
        self.dictating = False
        self.transcripts = {}
        self.transcript_text = {}
        self.drafts = {}
        self.current_incident = None
        self.last_path, self.closing, self.paused = None, False, False
        root.title("Shadowbane • Tester recorder")
        root.geometry("880x810")
        root.minsize(780, 770)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#101827")
        style.configure("TLabel", background="#101827", foreground="#e5edf8", padding=4)
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("TButton", padding=8)
        panel = ttk.Frame(root, padding=20)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Character & session recorder", style="Title.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Capture a build, mark a moment, explain what happened.").pack(
            anchor="w"
        )
        fields = ttk.Frame(panel)
        fields.pack(fill="x", pady=12)
        self.profile, self.character, self.server, self.pid = (
            tk.StringVar(value="Wonderbane"),
            tk.StringVar(),
            tk.StringVar(value="Wonderbane"),
            tk.StringVar(),
        )
        for col, (label, variable) in enumerate(
            (
                ("Profile", self.profile),
                ("Character", self.character),
                ("Server name", self.server),
                ("PID (optional)", self.pid),
            )
        ):
            ttk.Label(fields, text=label).grid(row=0, column=col, sticky="w")
            widget = (
                ttk.Combobox(
                    fields,
                    textvariable=variable,
                    values=("Wonderbane", "Private SB"),
                    state="readonly",
                    width=17,
                )
                if col == 0
                else ttk.Entry(fields, textvariable=variable, width=19)
            )
            widget.grid(row=1, column=col, sticky="ew", padx=(0, 8))
            fields.columnconfigure(col, weight=1)
        self.input_opt = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            panel,
            text="Record game keyboard/button codes while the game is foreground",
            variable=self.input_opt,
        ).pack(anchor="w")
        ttk.Label(
            panel,
            text="Input recording is optional. Codes can reveal in-game typing. "
            "Pause before chat.\nNo microphone, screenshots or automatic upload. "
            "Each session stays on one character.",
        ).pack(anchor="w")
        controls = ttk.Frame(panel)
        controls.pack(fill="x", pady=10)
        self.start_button = ttk.Button(controls, text="Start session", command=self.start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.pause_button = ttk.Button(controls, text="Pause", command=self.pause, state="disabled")
        self.pause_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(
            controls, text="Stop & export", command=self.stop, state="disabled"
        )
        self.stop_button.pack(side="left", padx=4)
        ttk.Button(controls, text="Open output folder", command=self.open_output).pack(side="right")
        self.status = tk.StringVar(value="Ready — log in, enter the exact names, then start.")
        self.health = tk.StringVar(value="Waiting for a session.")
        ttk.Label(panel, textvariable=self.status, wraplength=760).pack(anchor="w", pady=(5, 2))
        ttk.Label(panel, textvariable=self.health, wraplength=760).pack(anchor="w")
        ttk.Separator(panel).pack(fill="x", pady=12)
        marker = ttk.Frame(panel)
        marker.pack(fill="x")
        self.label = tk.StringVar(value="Something happened")
        ttk.Entry(marker, textvariable=self.label).pack(side="left", fill="x", expand=True)
        self.mark_button = ttk.Button(
            marker, text="Mark incident", command=self.mark, state="disabled"
        )
        self.mark_button.pack(side="right", padx=(8, 0))
        ttk.Label(
            panel,
            text="Keeps the surrounding 60 seconds before / 30 seconds after. "
            "Mark first; add the explanation afterward.",
        ).pack(anchor="w")
        self.incident = tk.StringVar()
        self.incidents = {}
        self.selector = ttk.Combobox(panel, textvariable=self.incident, state="readonly")
        self.selector.pack(fill="x", pady=6)
        self.selector.bind("<<ComboboxSelected>>", self.select_incident)
        self.speech_status = tk.StringVar(value="Microphone off • local speech-to-text")
        speech_controls = ttk.Frame(panel)
        speech_controls.pack(fill="x", pady=3)
        self.speech_button = ttk.Button(
            speech_controls, text="Start dictation", command=self.dictate, state="disabled"
        )
        self.speech_button.pack(side="left")
        ttk.Label(speech_controls, textvariable=self.speech_status).pack(side="left", padx=8)
        self.answers = {}
        for key, label in (
            ("intent", "What were you trying to do?"),
            ("expected", "What did you expect?"),
            ("actual", "What happened?"),
        ):
            ttk.Label(panel, text=label).pack(anchor="w")
            box = tk.Text(
                panel,
                height=2,
                wrap="word",
                font=("Segoe UI", 10),
                background="#202e43",
                foreground="#edf3fc",
                insertbackground="white",
            )
            box.pack(fill="x", pady=(0, 3))
            self.answers[key] = box
        self.note_button = ttk.Button(
            panel, text="Save explanation", command=self.annotate, state="disabled"
        )
        self.note_button.pack(anchor="e", pady=8)
        root.after(100, self.poll)

    def send(self, kind, **payload):
        if not self.watcher:
            return
        try:
            self.watcher.command(kind, **payload)
        except queue.Full:
            messagebox.showerror("Recorder busy", "The command queue is full. Please retry.")

    def start(self):
        try:
            pid = int(self.pid.get()) if self.pid.get().strip() else None
            if pid is not None and pid <= 0:
                raise ValueError("PID must be positive.")
            self.watcher = Watcher(
                self.output,
                self.character.get().strip(),
                self.server.get().strip(),
                pid=pid,
                inputs=self.input_opt.get(),
                profile=self.profile.get(),
            )
            self.incidents.clear()
            self.transcripts.clear()
            self.transcript_text.clear()
            self.drafts.clear()
            self.current_incident = None
            self.selector.configure(values=())
            self.incident.set("")
            self.paused = False
            self.pause_button.configure(text="Pause")
            self.start_button.configure(state="disabled")
            self.status.set("Binding the character and checking the automatic build reader…")
            self.watcher.start()
        except Exception as exc:
            self.watcher = None
            self.start_button.configure(state="normal")
            messagebox.showerror("Cannot start", str(exc))

    def pause(self):
        self.paused = not self.paused
        self.send("pause", paused=self.paused)

    def stop(self):
        if self.watcher:
            self.status.set("Stopping and sealing the local evidence bundle…")
            self.watcher.stop()

    def mark(self):
        self.send("mark", label=self.label.get())

    def annotate(self):
        identifier = self.incidents.get(self.incident.get())
        if not identifier:
            messagebox.showerror("Select an incident", "Mark or select the moment to explain.")
            return
        self.send(
            "annotate",
            incident_id=identifier,
            transcript_ids=self.transcripts.get(identifier, ()),
            **{k: box.get("1.0", "end") for k, box in self.answers.items()},
        )

    def select_incident(self, _event=None):
        if self.current_incident:
            self.drafts[self.current_incident] = {
                k: box.get("1.0", "end").strip() for k, box in self.answers.items()
            }
        identifier = self.incidents.get(self.incident.get())
        self.current_incident = identifier
        draft = self.drafts.get(
            identifier,
            {
                "intent": "",
                "expected": "",
                "actual": " ".join(self.transcript_text.get(identifier, ())),
            },
        )
        for key, box in self.answers.items():
            box.delete("1.0", "end")
            box.insert("1.0", draft[key])

    def dictate(self):
        if self.dictating:
            self.send("dictation_stop")
            return
        identifier = self.incidents.get(self.incident.get())
        if not identifier:
            messagebox.showerror("Select an incident", "Mark or select an incident first.")
            return
        self.send("dictate", incident_id=identifier)

    def open_output(self):
        path = Path(self.last_path or self.output)
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def poll(self):
        if self.watcher:
            while True:
                try:
                    item = self.watcher.updates.get_nowait()
                except queue.Empty:
                    break
                kind = item["kind"]
                if kind == "started":
                    self.last_path = item["path"]
                    self.status.set(
                        "Recording • "
                        + item["source"]["character_name"]
                        + " on "
                        + item["source"]["server_name"]
                    )
                    for button in (
                        self.pause_button,
                        self.stop_button,
                        self.mark_button,
                        self.note_button,
                        self.speech_button,
                    ):
                        button.configure(state="normal")
                elif kind == "sample":
                    self.health.set(
                        f"{item['equipment']} equipped items • {item['runes']} runes • "
                        f"{item['bytes'] // 1024} KiB • "
                        + ("Game foreground" if item["foreground"] else "Game background")
                    )
                elif kind == "speech_starting":
                    self.dictating = True
                    self.speech_button.configure(text="Stop dictation")
                    self.speech_status.set("Starting microphone…")
                elif kind == "speech_stopped":
                    self.dictating = False
                    self.speech_button.configure(text="Start dictation")
                    self.speech_status.set("Microphone off")
                elif kind == "speech":
                    payload = item["payload"]
                    if payload["kind"] == "ready":
                        self.speech_status.set("MIC ON • " + payload["culture"])
                    elif payload["kind"] == "transcript":
                        identifier = item["incident_id"]
                        self.transcripts.setdefault(identifier, []).append(item["record_id"])
                        self.transcript_text.setdefault(identifier, []).append(payload["text"])
                        if identifier in self.drafts:
                            self.drafts[identifier]["actual"] += " " + payload["text"]
                        self.speech_status.set(
                            f"MIC ON • confidence {payload['confidence']:.0%} • check wording"
                        )
                        if self.incidents.get(self.incident.get()) == identifier:
                            self.answers["actual"].insert("end", payload["text"] + " ")
                        else:
                            self.status.set("Transcript saved to its original incident.")
                    elif payload["kind"] in ("error", "rejected"):
                        self.speech_status.set("Speech needs attention: " + payload["text"][:100])
                elif kind == "paused":
                    self.status.set(
                        "Paused — native and input collection suspended."
                        if item["paused"]
                        else "Recording resumed"
                    )
                    self.pause_button.configure(text="Resume" if item["paused"] else "Pause")
                elif kind == "marked":
                    label = f"{len(self.incidents) + 1}. {item['label']}"
                    self.incidents[label] = item["incident_id"]
                    self.selector.configure(values=tuple(self.incidents))
                    self.incident.set(label)
                    self.select_incident()
                    self.status.set(
                        "Incident marked. Continue for 30 seconds to finish its window."
                    )
                elif kind == "annotated":
                    self.status.set("Explanation saved with the selected incident.")
                elif kind in ("error", "sample_error", "command_error"):
                    self.status.set(item["error"])
                elif kind == "finished":
                    self.last_path = item["path"]
                    self.status.set(
                        ("Stopped with a problem. " if item["failed"] else "Export ready. ")
                        + item["reason"]
                    )
                    self.health.set("Local evidence.zip: " + item["path"])
                elif kind == "stopped":
                    for button in (
                        self.pause_button,
                        self.stop_button,
                        self.mark_button,
                        self.note_button,
                        self.speech_button,
                    ):
                        button.configure(state="disabled")
                    self.start_button.configure(state="normal")
                    self.watcher = None
                    if self.closing:
                        self.root.destroy()
                        return
                    break
        self.root.after(100, self.poll)

    def close(self):
        if self.watcher:
            self.closing = True
            self.stop()
        else:
            self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    default = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ShadowbaneRecorder" / "captures"
    )
    parser.add_argument("--self-test", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--output-root", type=Path, default=default)
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("The tester dashboard requires Windows.")
    if args.self_test:
        from .selftest import run_self_test

        return run_self_test(args.self_test)
    root = tk.Tk()
    Dashboard(root, args.output_root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
