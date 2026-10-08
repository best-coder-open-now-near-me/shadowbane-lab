"""One owner for native reads, diagnostic probes, input events and tester commands."""

from __future__ import annotations

import queue
import threading
import time

from shadowbane_lab.cases.capture import CaptureQuality, CaptureRecordKind
from shadowbane_lab.client_input.window import WindowsForegroundWindowInspector
from shadowbane_lab.client_observation.native_character_session import NativeCharacterSession
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from shadowbane_lab.client_observation.native_snapshot import (
    NativePlayerSnapshotReader,
    load_bundled_native_player_snapshot_profiles,
)
from shadowbane_vanilla_diagnostics.windows import WindowsNetworkProbe, WindowsProcessProbe

from .binding import CaptureCharacterReader as NativeCharacterConfigReader
from .binding import PrivateServerCharacterReader
from .build import BuildReadError, NativeCharacterBuildReader
from .input import WindowsGameInput
from .recording import Recording, RecordingLimit
from .speech import WindowsDictation
from .transfer import CaptureError, observe_character


class Watcher:
    def __init__(
        self,
        root,
        character,
        server,
        *,
        pid=None,
        inputs=False,
        profile="Wonderbane",
        expected_creation=None,
    ):
        if (
            not character.strip()
            or not server.strip()
            or profile not in ("Wonderbane", "Private SB")
        ):
            raise ValueError("Choose a profile and enter the character and server names.")
        self.expected_creation = expected_creation
        self.root, self.character, self.server = root, character, server
        self.pid, self.inputs, self.profile = pid, inputs, profile
        self.commands = queue.Queue(maxsize=256)
        self.updates = queue.Queue(maxsize=256)
        self.stop_requested = threading.Event()
        self.thread = None

    def start(self):
        if self.thread is not None:
            raise RuntimeError("A watcher instance may only start once.")
        self.thread = threading.Thread(target=self._run, name="character-recorder", daemon=True)
        self.thread.start()

    def command(self, kind, **payload):
        self.commands.put_nowait((time.monotonic_ns(), kind, payload))

    def stop(self):
        self.stop_requested.set()

    def notify(self, kind, **payload):
        try:
            self.updates.put_nowait({"kind": kind, **payload})
        except queue.Full:
            # Presentation is replaceable; evidence producers have their own loss reporting.
            self.updates.get_nowait()
            self.updates.put_nowait({"kind": kind, **payload})

    def _run(self):
        process = inputs = recording = speech = None
        speech_incident = None
        failed, reason = False, "Stopped by tester"

        def drain_speech():
            if speech is None:
                return
            recording.losses["speech"] = speech.dropped
            while not speech.events.empty():
                at, payload = speech.events.get_nowait()
                event = recording.emit(
                    "speech-transcript",
                    {**payload, "timing_alignment": "approximate-audio-stream"},
                    kind=CaptureRecordKind.OBSERVATION,
                    at=at,
                    correlation=speech_incident,
                    quality=(CaptureQuality.PARTIAL,) if payload["kind"] == "rejected" else (),
                )
                if payload["kind"] == "transcript":
                    recording.speech_records[event.record_id] = speech_incident
                self.notify(
                    "speech",
                    payload=payload,
                    incident_id=speech_incident,
                    record_id=event.record_id,
                )

        def stop_speech():
            if speech is not None:
                speech.stop()
                drain_speech()
                recording.emit(
                    "speech-control",
                    {"active": False, "forced_stop": speech.forced_stop},
                    kind=CaptureRecordKind.EVENT,
                    correlation=speech_incident,
                )
                self.notify("speech_stopped")

        try:
            process = (
                WindowsReadOnlyProcessMemory.open_unique("sb.exe")
                if self.pid is None
                else WindowsReadOnlyProcessMemory.open_for_process("sb.exe", self.pid)
            )
            if (
                self.expected_creation is not None
                and process.process_creation_filetime_utc != self.expected_creation
            ):
                raise CaptureError("The game restarted. Find your character again.")
            identity_reader = (
                PrivateServerCharacterReader
                if self.profile == "Private SB"
                else NativeCharacterConfigReader
            )
            session = NativeCharacterSession(identity_reader(process))
            identity = session.binding.identity
            if (
                identity.character_name.casefold() != self.character.casefold()
                or identity.server_name.casefold() != self.server.casefold()
            ):
                raise CaptureError(
                    "Logged-in character/server differs from the dashboard selection."
                )
            build = NativeCharacterBuildReader(session)
            native = NativePlayerSnapshotReader(
                load_bundled_native_player_snapshot_profiles(), process
            )
            initial = observe_character(session, native, build)
            recording = Recording(
                self.root,
                {
                    **session.binding.as_dict(),
                    "profile": self.profile,
                    "input_recording_enabled": self.inputs,
                },
            )
            recording.emit("character", initial)
            inspector = WindowsForegroundWindowInspector()
            metrics, network = WindowsProcessProbe(), WindowsNetworkProbe()
            if self.inputs:
                inputs = WindowsGameInput(process.pid, process.process_creation_filetime_utc)
                inputs.start()
                inputs.enabled.set()
            self.notify("started", path=str(recording.path), source=recording.source)
            paused, next_sample, next_network, drops, last_focus = False, 0, 0, 0, None
            while True:
                self.stop_requested.wait(0.025)
                if time.monotonic_ns() > recording.deadline:
                    raise RecordingLimit("Two-hour recording limit reached.")
                for _ in range(256):
                    try:
                        at, kind, payload = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        if kind == "pause":
                            paused = bool(payload["paused"])
                            if paused and speech is not None:
                                stop_speech()
                                speech = None
                            if inputs:
                                inputs.enabled.clear() if paused else inputs.enabled.set()
                            recording.emit(
                                "recorder-control",
                                {"paused": paused},
                                kind=CaptureRecordKind.EVENT,
                                at=at,
                            )
                            self.notify("paused", paused=paused)
                        elif kind == "mark":
                            identifier = recording.mark(payload["label"], at=at)
                            self.notify("marked", incident_id=identifier, label=payload["label"])
                        elif kind == "dictate":
                            if paused:
                                raise ValueError("Resume recording before dictating.")
                            if speech is not None:
                                stop_speech()
                                speech = None
                            speech_incident = payload["incident_id"]
                            if speech_incident not in recording.incidents:
                                raise ValueError("Select an incident before dictating.")
                            speech = WindowsDictation()
                            speech.start()
                            recording.emit(
                                "speech-control",
                                {"active": True},
                                kind=CaptureRecordKind.EVENT,
                                correlation=speech_incident,
                            )
                            self.notify("speech_starting")
                        elif kind == "dictation_stop":
                            stop_speech()
                            speech = None
                        elif kind == "annotate":
                            recording.annotate(at=at, **payload)
                            self.notify("annotated", incident_id=payload["incident_id"])
                        else:
                            raise ValueError("Unknown dashboard command.")
                    except (ValueError, KeyError) as exc:
                        self.notify("command_error", error=str(exc))
                if speech is not None:
                    drain_speech()
                    if speech.process.poll() is not None:
                        stop_speech()
                        speech = None
                if inputs:
                    # Drain even across pause; the hook recorded these before the boundary.
                    for _ in range(8192):
                        try:
                            at, payload = inputs.events.get_nowait()
                        except queue.Empty:
                            break
                        recording.emit("game-input", payload, kind=CaptureRecordKind.EVENT, at=at)
                    if inputs.dropped != drops:
                        recording.emit(
                            "input-health",
                            {"dropped_events": inputs.dropped - drops},
                            kind=CaptureRecordKind.PRODUCER_HEALTH,
                            quality=(CaptureQuality.DROPPED,),
                        )
                        drops = inputs.dropped
                        recording.losses["game-input"] = drops
                    if inputs.error:
                        raise RuntimeError("Input capture failed: " + inputs.error)
                if self.stop_requested.is_set():
                    break
                now = time.monotonic()
                if now < next_sample:
                    continue
                next_sample = now + 1
                session.require_current()  # Also stop on logout while paused.
                if paused:
                    continue
                window = inspector.inspect()
                focused = bool(
                    window
                    and window.is_foreground
                    and window.process_id == process.pid
                    and window.process_started_at_100ns == process.process_creation_filetime_utc
                )
                if focused != last_focus:
                    recording.emit(
                        "game-focus",
                        {"foreground": focused, "held_keys_unknown": True},
                        kind=CaptureRecordKind.EVENT,
                    )
                    last_focus = focused
                sample = metrics.sample(process.pid)
                if sample.identity.exact_key != (
                    process.pid,
                    process.process_creation_filetime_utc,
                ):
                    raise CaptureError("Diagnostic process lifetime changed.")
                recording.emit("process-metrics", sample.metrics)
                if now >= next_network:
                    # Endpoint inventory only, not packets, payloads or authentication.
                    try:
                        value = network.sample(process.pid)
                        session.require_current()
                        recording.emit("network-endpoints", value)
                    except OSError as exc:
                        recording.emit(
                            "network-health",
                            {"error": str(exc)},
                            kind=CaptureRecordKind.PRODUCER_HEALTH,
                            quality=(CaptureQuality.PARTIAL,),
                        )
                    next_network = now + 5
                try:
                    snapshot = observe_character(session, native, build)
                    recording.emit("character", snapshot)
                    self.notify(
                        "sample",
                        bytes=recording.bytes,
                        equipment=sum(
                            e["item"] is not None for e in snapshot["current_build"]["equipment"]
                        ),
                        runes=len(snapshot["current_build"]["applied_runes"]),
                        foreground=focused,
                        counts=dict(recording.counts),
                    )
                except (BuildReadError, CaptureError) as exc:
                    recording.emit(
                        "character-health",
                        {"error": str(exc)},
                        kind=CaptureRecordKind.PRODUCER_HEALTH,
                        quality=(CaptureQuality.PARTIAL,),
                    )
                    self.notify("sample_error", error=str(exc))
        except RecordingLimit as exc:
            reason = str(exc)
        except Exception as exc:
            failed, reason = True, str(exc)
            self.notify("error", error=reason)
        finally:
            if speech is not None:
                try:
                    stop_speech()
                except Exception as exc:
                    failed, reason = True, "Speech stop/seal failed: " + str(exc)
            if inputs:
                try:
                    inputs.stop()
                except Exception as exc:
                    failed, reason = True, str(exc)
                # Preserve queued final events and explicitly account for capacity loss.
                if recording and not recording.closed:
                    try:
                        while not inputs.events.empty():
                            at, payload = inputs.events.get_nowait()
                            recording.emit(
                                "game-input", payload, kind=CaptureRecordKind.EVENT, at=at
                            )
                    except Exception as exc:
                        failed = True
                        reason += "; final input drain failed: " + str(exc)
                        recording.losses["unwritten-final-input-events"] = inputs.events.qsize() + 1
                    recording.losses["game-input"] = inputs.dropped
            if process:
                process.close()
            if recording:
                try:
                    path = recording.finish(reason, failed=failed)
                    self.notify("finished", path=str(path), reason=reason, failed=failed)
                except Exception as exc:
                    self.notify(
                        "error",
                        error=f"Seal failed; raw evidence remains at {recording.path}: {exc}",
                    )
            self.notify("stopped")
