"""Local tester dashboard for both Wonderbane and private Shadowbane recordings."""

from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .delivery import deliver, list_reports, load_connection
from .discovery import discover_characters
from .watcher import Watcher


class Dashboard:
    def __init__(self, root, output):
        self.root, self.output, self.watcher = root, Path(output), None
        self.dictating = False
        self.transcripts, self.transcript_text, self.drafts = {}, {}, {}
        self.current_incident = None
        self.last_path, self.closing, self.paused = None, False, False
        self.background = queue.Queue()
        self.characters, self.report_rows = {}, {}
        self.discovering = self.sending = False
        config_root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
        self.connection = None
        try:
            self.connection = load_connection(config_root / "connection.json")
        except (OSError, ValueError, KeyError):
            pass
        root.title("Shadowbane Companion")
        root.geometry("860x720")
        root.minsize(720, 640)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#101827")
        style.configure("TLabel", background="#101827", foreground="#e5edf8", padding=4)
        style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"))
        style.configure("TButton", padding=8)
        panel = ttk.Frame(root, padding=16)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Shadowbane Companion", style="Title.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Play normally. Tell us when something happens.").pack(anchor="w")
        self.tabs = ttk.Notebook(panel)
        self.tabs.pack(fill="both", expand=True, pady=(10, 0))
        record_page, report_page = (
            ttk.Frame(self.tabs, padding=12),
            ttk.Frame(self.tabs, padding=12),
        )
        self.tabs.add(record_page, text="  Record a session  ")
        self.tabs.add(report_page, text="  My reports  ")
        self.report_page = report_page
        self.profile, self.character, self.server, self.pid = (
            tk.StringVar(value="Wonderbane"),
            tk.StringVar(),
            tk.StringVar(),
            tk.StringVar(),
        )
        self.character_choice = tk.StringVar()
        discovery = ttk.Frame(record_page)
        discovery.pack(fill="x")
        self.character_picker = ttk.Combobox(
            discovery, textvariable=self.character_choice, state="readonly"
        )
        self.character_picker.pack(side="left", fill="x", expand=True)
        self.find_button = ttk.Button(
            discovery, text="Find characters", command=self.find_characters
        )
        self.find_button.pack(side="right", padx=(8, 0))
        self.input_opt = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            record_page, text="Include game controls in this recording", variable=self.input_opt
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            record_page,
            text="Optional. Only the game window is recorded; pause before typing "
            "in chat.\nThe microphone stays off until you choose Start dictation.",
            wraplength=750,
        ).pack(anchor="w")
        controls = ttk.Frame(record_page)
        controls.pack(fill="x", pady=8)
        self.start_button = ttk.Button(controls, text="Start recording", command=self.start)
        self.start_button.pack(side="left", padx=(0, 8))
        self.pause_button = ttk.Button(controls, text="Pause", command=self.pause, state="disabled")
        self.pause_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(
            controls, text="Finish report", command=self.stop, state="disabled"
        )
        self.stop_button.pack(side="left", padx=4)
        self.status = tk.StringVar(value="Log into the game. Your character will appear here.")
        self.health = tk.StringVar(value="")
        ttk.Label(record_page, textvariable=self.status, wraplength=750).pack(anchor="w")
        ttk.Label(record_page, textvariable=self.health, wraplength=750).pack(anchor="w")
        ttk.Separator(record_page).pack(fill="x", pady=6)
        marker = ttk.Frame(record_page)
        marker.pack(fill="x")
        self.label = tk.StringVar(value="Something happened")
        ttk.Entry(marker, textvariable=self.label).pack(side="left", fill="x", expand=True)
        self.mark_button = ttk.Button(
            marker, text="Mark this moment", command=self.mark, state="disabled"
        )
        self.mark_button.pack(side="right", padx=(8, 0))
        self.incident, self.incidents = tk.StringVar(), {}
        self.selector = ttk.Combobox(record_page, textvariable=self.incident, state="readonly")
        self.selector.pack(fill="x", pady=6)
        self.selector.bind("<<ComboboxSelected>>", self.select_incident)
        self.speech_status = tk.StringVar(value="Microphone off")
        speech_controls = ttk.Frame(record_page)
        speech_controls.pack(fill="x", pady=2)
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
            ttk.Label(record_page, text=label).pack(anchor="w")
            box = tk.Text(
                record_page,
                height=2,
                wrap="word",
                font=("Segoe UI", 10),
                background="#202e43",
                foreground="#edf3fc",
                insertbackground="white",
            )
            box.pack(fill="x")
            self.answers[key] = box
        self.note_button = ttk.Button(
            record_page, text="Save explanation", command=self.annotate, state="disabled"
        )
        self.note_button.pack(anchor="e", pady=5)
        ttk.Label(report_page, text="Your reports", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            report_page,
            text="Reports stay on this computer until you choose Send report.",
            wraplength=740,
        ).pack(anchor="w")
        self.report_list = ttk.Treeview(
            report_page,
            columns=("character", "date", "status"),
            show="headings",
            height=7,
            selectmode="browse",
        )
        for key, title, width in (
            ("character", "Character", 200),
            ("date", "Recorded", 200),
            ("status", "Delivery", 160),
        ):
            self.report_list.heading(key, text=title)
            self.report_list.column(key, width=width)
        self.report_list.pack(fill="x", pady=10)
        self.report_list.bind("<<TreeviewSelect>>", self.review_report)
        self.report_preview = tk.StringVar(value="Select a report to review.")
        ttk.Label(report_page, textvariable=self.report_preview, wraplength=740).pack(anchor="w")
        self.delivery_status = tk.StringVar(
            value=(
                "Connected to your private server."
                if self.connection
                else "Ask the server owner for an installer with report delivery configured."
            )
        )
        ttk.Label(report_page, textvariable=self.delivery_status, wraplength=740).pack(
            anchor="w", pady=12
        )
        self.send_button = ttk.Button(
            report_page, text="Send report", command=self.send_report, state="disabled"
        )
        self.send_button.pack(anchor="e")
        ttk.Button(report_page, text="Open local reports", command=self.open_output).pack(
            anchor="w"
        )
        self.refresh_reports()
        root.after(100, self.poll)
        root.after(250, self.find_characters)

    def find_characters(self):
        if self.discovering or self.watcher:
            return
        self.discovering = True
        self.find_button.configure(state="disabled")
        self.status.set("Looking for your logged-in character…")

        def work():
            try:
                found, issues = discover_characters()
                self.background.put(("characters", (found, issues)))
            except Exception:
                self.background.put(
                    (
                        "characters",
                        (
                            [],
                            [
                                "Could not find the game. "
                                "Open Shadowbane and log in, then try again."
                            ],
                        ),
                    )
                )

        threading.Thread(target=work, daemon=True).start()

    def refresh_reports(self):
        self.report_rows.clear()
        self.report_list.delete(*self.report_list.get_children())
        for index, item in enumerate(list_reports(self.output)):
            key = str(index)
            self.report_rows[key] = item
            summary = item["summary"]
            self.report_list.insert(
                "",
                "end",
                iid=key,
                values=(
                    summary["source"].get("character_name", "Character"),
                    summary.get("started_at_utc", "")[:19].replace("T", " "),
                    item["status"],
                ),
            )

    def review_report(self, _event=None):
        selected = self.report_list.selection()
        if not selected:
            return
        item = self.report_rows[selected[0]]
        summary = item["summary"]
        labels = (
            ", ".join(i["label"] for i in summary.get("incidents", [])) or "No incidents marked"
        )
        source = summary["source"]
        self.report_preview.set(
            f"{source.get('character_name', 'Character')} "
            f"on {source.get('server_name', 'server')}\n"
            f"{labels}\n\nIncludes character/equipment snapshots, performance and connection "
            "details, your notes and any optional controls or speech transcripts. "
            "Microphone audio is not included."
        )
        self.send_button.configure(
            state="normal"
            if self.connection and not self.sending and item["status"] != "Sent"
            else "disabled"
        )

    def send_report(self):
        selected = self.report_list.selection()
        if self.sending or not self.connection or not selected:
            return
        item = self.report_rows[selected[0]]
        self.sending = True
        self.send_button.configure(state="disabled")
        self.delivery_status.set("Sending to your private server…")

        def work():
            try:
                receipt = deliver(
                    item["path"],
                    self.connection,
                    progress=lambda sent, total: self.background.put(
                        ("progress", int(sent * 100 / total))
                    ),
                )
                self.background.put(("delivered", receipt))
            except Exception:
                self.background.put(("delivery_error", None))

        threading.Thread(target=work, daemon=True).start()

    def poll_background(self):
        while True:
            try:
                kind, value = self.background.get_nowait()
            except queue.Empty:
                break
            if kind == "characters":
                found, issues = value
                self.characters.clear()
                for item in found:
                    label = f"{item['character_name']} — {item['server_name']}"
                    if label in self.characters:
                        label += f" (window {len(self.characters) + 1})"
                    self.characters[label] = item
                self.character_picker.configure(values=tuple(self.characters))
                self.character_choice.set(next(iter(self.characters), ""))
                self.discovering = False
                self.find_button.configure(state="normal")
                self.status.set(
                    "Choose your character and start recording."
                    if found
                    else (
                        issues[0]
                        if issues
                        else "Open Shadowbane and log in, then click Find characters."
                    )
                )
            elif kind == "progress":
                self.delivery_status.set(f"Sending report… {value}%")
            elif kind == "delivered":
                self.sending = False
                self.delivery_status.set("Sent successfully. Your server confirmed receipt.")
                self.refresh_reports()
            elif kind == "delivery_error":
                self.sending = False
                self.delivery_status.set(
                    "Could not confirm delivery. Your report is saved. "
                    "Check that Tailscale is connected, then select the report and try again."
                )
                self.review_report()

    def send(self, kind, **payload):
        if not self.watcher:
            return
        try:
            self.watcher.command(kind, **payload)
        except queue.Full:
            messagebox.showerror("Recorder busy", "The command queue is full. Please retry.")

    def start(self):
        try:
            selected = self.characters.get(self.character_choice.get())
            if not selected:
                raise ValueError("Log into your character, then click Find characters.")
            self.pid.set(str(selected["process_id"]))
            self.character.set(selected["character_name"])
            self.server.set(selected["server_name"])
            self.profile.set(selected["profile"])
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
                expected_creation=selected["process_creation_filetime_utc"],
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
            if self.current_incident and any(
                box.get("1.0", "end").strip() for box in self.answers.values()
            ):
                self.annotate()
            self.status.set("Saving your report…")
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
        self.poll_background()
        if self.watcher:
            while True:
                try:
                    item = self.watcher.updates.get_nowait()
                except queue.Empty:
                    break
                kind = item["kind"]
                if kind == "started":
                    self.last_path = item["path"]
                    self.refresh_reports()
                    self.tabs.select(self.report_page)
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
                    self.refresh_reports()
                    self.tabs.select(self.report_page)
                    self.status.set(
                        ("Stopped with a problem. " if item["failed"] else "Export ready. ")
                        + item["reason"]
                    )
                    self.health.set("Report saved. Review it in My reports when you are ready.")
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

        try:
            return run_self_test(args.self_test)
        except Exception as exc:
            import json

            args.self_test.write_text(
                json.dumps({"passed": False, "error": str(exc)}, indent=2), encoding="utf-8"
            )
            return 1
    root = tk.Tk()
    Dashboard(root, args.output_root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
