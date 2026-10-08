"""Append-only tester timelines using the shared capture-record/evidence contracts."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections import Counter
from pathlib import Path

from shadowbane_lab.cases.capture import CaptureRecord, CaptureRecordKind
from shadowbane_lab.evidence import (
    ArtifactKind,
    ArtifactStore,
    EvidenceManifest,
    ManifestTerminalState,
    create_bundle,
    save_contract,
)
from shadowbane_lab.integrity import create_only_json

from .transfer import _now

VERSION = "1.0.0"


class RecordingLimit(RuntimeError):
    pass


class Recording:
    """Single writer; producers queue timestamped events to the owning worker."""

    def __init__(
        self,
        root,
        source,
        *,
        maximum_bytes=128 * 1024 * 1024,
        maximum_seconds=7200,
        clock=time.monotonic_ns,
    ):
        if not 1024 <= maximum_bytes <= 1024**3 or not 1 <= maximum_seconds <= 28800:
            raise ValueError("Recording limits are outside the supported bounds.")
        self.clock = clock
        self.started = clock()
        self.maximum_bytes = maximum_bytes
        self.deadline = self.started + int(maximum_seconds * 1e9)
        self.run_id = "watch-" + uuid.uuid4().hex
        self.path = Path(root).resolve() / self.run_id
        self.path.mkdir(parents=True, exist_ok=False)
        self.source = source
        self.sequences = Counter()
        self.counts = Counter()
        self.last_times = {}
        self.incidents = {}
        self.bytes = 0
        self.losses = {}
        self.speech_records = {}
        self.closed = False
        self.stream = (self.path / "timeline.jsonl").open("xb")
        self.metadata = {
            "schema_version": 1,
            "format": "shadowbane.tester-recording",
            "run_id": self.run_id,
            "producer_version": VERSION,
            "source": source,
            "started_at_utc": _now(),
            "started_monotonic_ns": self.started,
            "maximum_seconds": maximum_seconds,
            "maximum_bytes": maximum_bytes,
            "clock_domain_id": self.run_id,
            "database_import_ready": False,
        }
        create_only_json(self.path / "session.json", self.metadata)

    def emit(
        self,
        channel,
        payload,
        *,
        kind=CaptureRecordKind.OBSERVATION,
        at=None,
        correlation=None,
        quality=(),
    ):
        if self.closed:
            raise RuntimeError("Recording is closed.")
        now = self.clock()
        at = now if at is None else at
        if not self.started <= at <= now:
            raise ValueError("Event timestamp is outside this session.")
        if at < self.last_times.get(channel, self.started):
            raise ValueError("Producer clock moved backwards.")
        record = CaptureRecord(
            run_id=self.run_id,
            channel_id=channel,
            producer_id=channel,
            producer_version=VERSION,
            clock_domain_id=self.run_id,
            monotonic_ns=at,
            # UTC is an arrival-time aid only; no cross-machine clock synchronization claimed.
            utc_uncertainty_ns=86_400_000_000_000,
            captured_at_utc=_now(),
            producer_sequence=self.sequences[channel] + 1,
            kind=kind,
            payload=tuple(sorted(payload.items())),
            correlation_id=correlation,
            quality=quality,
        )
        raw = (json.dumps(record.as_dict(), sort_keys=True, allow_nan=False) + "\n").encode()
        if len(raw) > 262144 or self.bytes + len(raw) > self.maximum_bytes or now > self.deadline:
            raise RecordingLimit("Recording reached its time or byte limit.")
        self.stream.write(raw)
        self.stream.flush()
        self.bytes += len(raw)
        self.sequences[channel] += 1
        self.counts[channel] += 1
        self.last_times[channel] = at
        return record

    def mark(self, label, *, at=None):
        label = label.strip()
        if not label or len(label) > 256 or len(self.incidents) >= 256:
            raise ValueError("Use a 1-256 character label; at most 256 incidents per session.")
        at = self.clock() if at is None else at
        identifier = "incident-" + uuid.uuid4().hex
        event = self.emit(
            "tester-markers",
            {"label": label},
            at=at,
            kind=CaptureRecordKind.MARKER,
            correlation=identifier,
        )
        self.incidents[identifier] = {
            "incident_id": identifier,
            "marker_record_id": event.record_id,
            "label": label,
            "marked_monotonic_ns": at,
            "requested_start_ns": at - 60_000_000_000,
            "requested_end_ns": at + 30_000_000_000,
        }
        return identifier

    def annotate(self, incident_id, *, intent, expected, actual, at=None, transcript_ids=()):
        if incident_id not in self.incidents:
            raise ValueError("Select an incident from this session.")
        if any(self.speech_records.get(i) != incident_id for i in transcript_ids):
            raise ValueError("Transcript references must belong to this incident.")
        fields = {"intent": intent.strip(), "expected": expected.strip(), "actual": actual.strip()}
        if not any(fields.values()) or any(len(s) > 4000 for s in fields.values()):
            raise ValueError("Provide an answer; each answer is limited to 4000 characters.")
        return self.emit(
            "tester-narration",
            {**fields, "transcript_record_ids": list(transcript_ids)},
            at=at,
            kind=CaptureRecordKind.MARKER,
            correlation=incident_id,
        )

    def finish(self, reason, *, failed=False):
        if self.closed:
            raise RuntimeError("Recording was already sealed.")
        self.closed = True
        ended = self.clock()
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.stream.close()
        incidents = []
        for item in self.incidents.values():
            incidents.append(
                {
                    **item,
                    "retained_start_ns": max(self.started, item["requested_start_ns"]),
                    "retained_end_ns": min(ended, item["requested_end_ns"]),
                    "pre_window_complete": item["requested_start_ns"] >= self.started,
                    "post_window_complete": item["requested_end_ns"] <= ended,
                }
            )
        summary = {
            **self.metadata,
            "ended_at_utc": _now(),
            "ended_monotonic_ns": ended,
            "reason": str(reason)[:2048],
            "record_counts": dict(self.counts),
            "timeline_bytes": self.bytes,
            "producer_losses": self.losses,
            "incidents": incidents,
            "input_semantics": "physical input observations, not confirmed game actions",
            "sampling": "native snapshots and process counters approximately once per second",
            "omissions": [
                "server-authoritative-events",
                "microphone-audio",
                "base-attribute-allocation-mapping",
            ],
        }
        create_only_json(self.path / "summary.json", summary)
        store = ArtifactStore.initialize(self.path / "evidence")
        artifacts = []
        for name, artifact_kind in (
            ("session.json", ArtifactKind.RUNTIME_SNAPSHOT),
            ("summary.json", ArtifactKind.RUNTIME_SNAPSHOT),
            ("timeline.jsonl", ArtifactKind.NATIVE_EVENT_STREAM),
        ):
            with (self.path / name).open("rb") as stream:
                artifacts.append(
                    store.ingest_chunks(
                        iter(lambda: stream.read(1024 * 1024), b""),
                        artifact_kind=artifact_kind,
                        media_type="application/x-ndjson"
                        if name.endswith("jsonl")
                        else "application/json",
                        logical_name=name,
                        producer_id="character-watcher",
                        producer_version=VERSION,
                    )
                )
        manifest = EvidenceManifest(
            created_at_utc=_now(),
            artifacts=tuple(sorted(artifacts, key=lambda a: a.artifact_id)),
            terminal_state=ManifestTerminalState.FAILED
            if failed
            else ManifestTerminalState.INCOMPLETE,
            run_id=self.run_id,
            omissions=tuple(sorted(summary["omissions"])),
            warnings=("Client observations do not authorize database import.",),
        )
        save_contract(self.path / "manifest.json", manifest)
        bundle = create_bundle(store, manifest, self.path / "evidence.zip")
        digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
        (self.path / "evidence.zip.sha256").write_text(
            digest + "  evidence.zip\n", encoding="ascii"
        )
        return self.path
