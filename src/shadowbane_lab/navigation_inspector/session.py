"""Optional live producer: callbacks enqueue; one worker owns transport and geometry."""

from __future__ import annotations

import json
import logging
import os
import queue
import secrets
import threading
from contextlib import contextmanager
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from shadowbane_lab.graphics_lab.control import discover_graphics_targets

from .events import ContextEvent, DiagnosticEvent, MotionEvent
from .geometry import prepare_geometry
from .identity import loaded_module_sha256
from .protocol import encode_frame
from .snapshot import Collector, SourceIdentity
from .transport import Channel, Controls, _windows_api

_LOG = logging.getLogger(__name__)
QUEUE_CAPACITY = 256


def source_identity(target) -> SourceIdentity:
    revision = "unavailable"
    try:
        metadata = json.loads(
            Path(__file__).with_name("build_identity.json").read_text(encoding="utf-8")
        )
        revision = metadata["source_revision"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        package_version = version("shadowbane-lab")
    except PackageNotFoundError:
        package_version = "unavailable"
    return SourceIdentity(
        target.process_id,
        target.process_creation_filetime_utc,
        target.executable_sha256,
        revision,
        package_version,
        loaded_module_sha256(target),
    )


class Session:
    """Bounded diagnostics only; has no input adapter or mutable navigation map."""

    def __init__(self, target, controls: Controls):
        self.target = target
        self.initial_controls = controls
        self._queue: queue.Queue[tuple[DiagnosticEvent, int]] = queue.Queue(QUEUE_CAPACITY)
        self._stop = threading.Event()
        self._gap = threading.Event()
        self._clock = _windows_api().GetTickCount64
        self._drops = 0
        self.error: str | None = None
        self._worker = threading.Thread(target=self._run, name="navigation-inspector", daemon=True)
        self._worker.start()

    def __call__(self, event: DiagnosticEvent) -> None:
        if self._stop.is_set():
            return
        try:
            self._queue.put_nowait((event, int(self._clock())))
        except queue.Full:
            self._drops += 1
            self._gap.set()

    def close(self) -> None:
        self._stop.set()
        # No game handle, reader, transport lock or render thread waits on this
        # worker. It owns and closes its channel even after a bounded join expires.
        self._worker.join(timeout=1.0)

    def _run(self) -> None:
        try:
            with Channel(self.target, role="producer") as channel:
                collector = Collector(
                    source_identity(self.target),
                    secrets.randbits(63) or 1,
                    clearance=self.initial_controls.clearance,
                )
                settings = self.initial_controls
                collector.freeze_on_failure = settings.freeze_on_failure
                control_sequence = 0
                sequence = 0
                last_zone_ms = 0
                while channel.alive:
                    if self._gap.is_set():
                        # Losing a context/plan invalidates placement. Drain the
                        # incomplete batch, then wait for new authoritative context.
                        self._gap.clear()
                        while True:
                            try:
                                self._queue.get_nowait()
                            except queue.Empty:
                                break
                        collector.observe(
                            ContextEvent("context", None, "dropped", "diagnostic event gap"),
                            channel.clock_ms(),
                        )
                        collector.dropped_observations = self._drops
                        last_zone_ms = 0
                    for _ in range(QUEUE_CAPACITY):
                        try:
                            event, received = self._queue.get_nowait()
                        except queue.Empty:
                            break
                        collector.observe(event, received)
                        if isinstance(event, ContextEvent):
                            last_zone_ms = received
                    controls = channel.controls(collector.session_id)
                    if controls is not None and controls.sequence != control_sequence:
                        settings = controls
                        control_sequence = controls.sequence
                        collector.clearance = settings.clearance
                        if collector.frozen is not None:
                            collector.frozen = replace(
                                collector.frozen, clearance=settings.clearance
                            )
                        collector.freeze_on_failure = settings.freeze_on_failure
                        if settings.command == 1:
                            collector.freeze()
                        elif settings.command == 2:
                            collector.resume()
                    now = channel.clock_ms()
                    snapshot = collector.snapshot()
                    geometry = prepare_geometry(snapshot)
                    sequence = 2 if sequence >= 0xFFFFFFFE else sequence + 2
                    payload = encode_frame(
                        snapshot,
                        geometry,
                        sequence=sequence,
                        lease_ms=now,
                        live_zone=collector.context.zone_token
                        if now - last_zone_ms <= 2000
                        else None,
                        enabled=settings.enabled,
                        xray=settings.xray,
                        layers=settings.layers,
                    )
                    channel.publish(payload)
                    # close() stops new callbacks, then the worker drains its
                    # bounded queue and publishes the terminal evidence once.
                    if self._stop.is_set() and self._queue.empty() and not self._gap.is_set():
                        break
                    self._stop.wait(0.1)
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            _LOG.warning("Navigation inspector stopped: %s", self.error)
        finally:
            self._stop.set()


@contextmanager
def optional_session(position_reader):
    """A panel arms the exact client; an environment flag can also enable a session.

    The default path has no worker/observer when the inspector is unarmed. Missing
    diagnostics never prevent an otherwise valid movement command from starting.
    """
    session = None
    forced = os.environ.get("SHADOWBANE_NAV_INSPECTOR") == "1"
    try:
        if os.name == "nt":
            # The profile names original source bytes. The verified reader owns
            # the actual loaded/patched process identity accepted by that profile.
            process_id = position_reader.process_id
            executable_sha256 = position_reader.executable_sha256
            targets = discover_graphics_targets(
                identity_validator=lambda candidate: (
                    candidate.process_id == process_id
                    and candidate.executable_sha256 == executable_sha256
                )
            )
            if len(targets) == 1:
                with Channel(targets[0]) as probe:
                    controls = probe.startup_controls()
                if forced or (controls is not None and controls.enabled):
                    settings = controls or Controls(2, 0)
                    session = Session(
                        targets[0], replace(settings, enabled=True) if forced else settings
                    )
            elif forced:
                _LOG.warning("Navigation inspector: no unique verified full-profile client channel")
    except Exception as error:
        if forced:
            _LOG.warning("Navigation inspector unavailable: %s", error)
    try:
        yield session
    finally:
        if session is not None:
            session.close()


class ObservedPositionSource:
    """Read the original position once; optional zone diagnostics cannot fail it."""

    def __init__(
        self, source, observer, *, zone_reader=None, map_zone=None, provenance="unavailable"
    ):
        self.source, self.observer = source, observer
        self.zone_reader, self.map_zone, self.provenance = zone_reader, map_zone, provenance

    def observe(self):
        position = self.source.observe()
        try:
            zone = self.zone_reader.observe() if self.zone_reader is not None else None
            token = zone.zone_token if zone is not None else None
            provenance = self.provenance
            if self.map_zone is not None and token != self.map_zone:
                provenance = "unavailable: active navigation map belongs to a different zone"
            self.observer(ContextEvent("context", token, self.map_zone or "direct", provenance))

        except Exception:
            try:
                self.observer(
                    ContextEvent("context", None, "unavailable", "zone observation failed")
                )
            except Exception:
                pass
        return position


def pve_trace_sink(journal, observer):
    """Preserve the existing journal's semantics and isolate optional diagnostics."""
    if journal is None and observer is None:
        return None

    def record(step):
        if journal is not None:
            journal.append_step(step.as_dict())
        if observer is None:
            return
        try:
            now = step.decision.now_ms
            position = step.player_position
            if position is not None:
                observer(
                    MotionEvent(
                        "motion",
                        "observation",
                        "runtime",
                        now,
                        position=(position.lt, position.lg, position.altitude),
                    )
                )
            for accepted, reason, prefix in (
                (step.approach_input_accepted, step.approach_input_reason, "input"),
                (step.movement_stop_accepted, step.movement_stop_reason, "stop"),
                (step.input_accepted, step.input_reason, "pve_input"),
            ):
                if accepted is not None:
                    observer(
                        MotionEvent(
                            "motion",
                            prefix + ("_accepted" if accepted else "_rejected"),
                            "runtime",
                            now,
                            reason=reason,
                        )
                    )
            if step.movement_arrival_confirmed is not None:
                observer(
                    MotionEvent(
                        "motion",
                        "arrival_confirmed" if step.movement_arrival_confirmed else "failure",
                        "runtime",
                        now,
                        reason=None if step.movement_arrival_confirmed else "arrival_not_settled",
                    )
                )
            if step.decision.terminal:
                reason = step.decision.terminal_reason
                observer(
                    MotionEvent(
                        "motion",
                        "completion"
                        if step.decision.phase.value == "complete"
                        else "cancelled"
                        if reason == "emergency_stop"
                        else "failure",
                        "runtime",
                        now,
                        reason=reason,
                    )
                )
        except Exception:
            pass

    return record
