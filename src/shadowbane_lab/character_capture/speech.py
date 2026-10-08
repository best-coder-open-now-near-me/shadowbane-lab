"""Opt-in local Windows dictation; transcripts remain observations until corrected."""

from __future__ import annotations

import json
import math
import os
import queue
import subprocess
import threading
import time
from pathlib import Path


def validate_speech_event(value):
    if not isinstance(value, dict) or value.get("kind") not in (
        "ready",
        "transcript",
        "rejected",
        "error",
    ):
        raise ValueError("Invalid speech event.")
    kind = value["kind"]
    if kind in ("transcript", "rejected", "error"):
        if not isinstance(value.get("text"), str) or len(value["text"]) > 8000:
            raise ValueError("Invalid speech text.")
    if kind in ("transcript", "rejected"):
        confidence = value.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("Invalid speech confidence.")
    if kind == "transcript":
        for key in (
            "audio_start_ms",
            "audio_duration_ms",
            "stream_anchor_ns",
            "observed_monotonic_ns",
        ):
            number = value.get(key)
            if (
                isinstance(number, bool)
                or not isinstance(number, (int, float))
                or not math.isfinite(number)
                or number < 0
            ):
                raise ValueError("Invalid speech timing.")
    return value


class WindowsDictation:
    def __init__(self, *, wave_path=None):
        self.events = queue.Queue(maxsize=256)
        self.process = None
        self.thread = None
        self.dropped = 0
        self.wave_path = wave_path
        self.forced_stop = False

    def start(self):
        helper = Path(__file__).with_name("dictation.ps1")
        shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        command = [
            str(shell),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
        ]
        if self.wave_path:
            command.extend(["-WavePath", str(Path(self.wave_path).resolve())])
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.thread = threading.Thread(target=self._read, name="speech-transcripts", daemon=True)
        self.thread.start()

    def _put(self, value):
        try:
            self.events.put_nowait((time.monotonic_ns(), value))
        except queue.Full:
            self.dropped += 1

    def _read(self):
        try:
            while line := self.process.stdout.readline(16385):
                if len(line) > 16384:
                    raise ValueError("Speech helper output exceeded its bound.")
                self._put(validate_speech_event(json.loads(line)))
        except Exception as exc:
            self._put({"kind": "error", "text": str(exc)[:8000]})
        finally:
            self.process.stdout.close()

    def stop(self):
        if not self.process:
            return
        if self.process.poll() is None:
            try:
                self.process.stdin.write("stop\n")
                self.process.stdin.flush()
                self.process.wait(timeout=4)
            except (BrokenPipeError, OSError):
                pass
            except subprocess.TimeoutExpired:
                self.forced_stop = True
                self.process.kill()
                self.process.wait(timeout=3)
        self.process.stdin.close()
        if self.thread:
            self.thread.join(timeout=3)
        if self.process.poll() not in (None, 0):
            self._put({"kind": "error", "text": "Speech helper exited unsuccessfully."})
