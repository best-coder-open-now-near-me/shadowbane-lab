"""Durable manager startup ownership, separate from worker readiness/dispatch."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from shadowbane_lab.record_store import (
    exclusive_record_lock,
    publish_atomic_record,
    read_record_bytes,
)


class StartupError(RuntimeError):
    """Startup ownership or listener identity could not be verified."""


def canonical(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


@dataclass(frozen=True)
class StartupConfig:
    manifest: str
    node_id: str
    port: int
    worker_directory: str
    token_file: str
    pid_file: str | None
    interpreter: str

    @classmethod
    def create(cls, manifest, node_id, port, workers, token, pid_file, interpreter):
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("Invalid manager port")
        return cls(
            canonical(manifest),
            node_id,
            port,
            canonical(workers),
            canonical(token),
            None if pid_file is None else canonical(pid_file),
            canonical(interpreter),
        )


def process_identity(snapshot):
    if snapshot is None:
        raise StartupError("Manager process identity is unavailable")
    return dict(pid=snapshot.process_id, creation=snapshot.process_started_at_100ns)


def same_process(snapshot, identity):
    return snapshot is not None and process_identity(snapshot) == identity


def _process(value):
    return value is None or (
        type(value) is dict
        and set(value) == {"pid", "creation"}
        and all(type(v) is int and v > 0 for v in value.values())
    )


def validate_record(value):
    fields = {"schema_version", "config", "generation", "manifest_sha256", "launcher", "manager"}
    if (
        type(value) is not dict
        or set(value) != fields
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or type(value["generation"]) is not str
        or re.fullmatch("[0-9a-f]{32}", value["generation"]) is None
        or type(value["manifest_sha256"]) is not str
        or re.fullmatch("[0-9a-f]{64}", value["manifest_sha256"]) is None
        or type(value["config"]) is not dict
        or set(value["config"]) != set(StartupConfig.__dataclass_fields__)
        or not _process(value["launcher"])
        or not _process(value["manager"])
    ):
        raise StartupError("Manager startup record is invalid; inspect the existing attempt")
    return value


class StartupStore:
    """One launch lock and immutable generation; unknown attempts never authorize a retry."""

    def __init__(self, directory: Path, inspector):
        self.path = directory / "manager-startup.json"
        self.lock = directory / "manager-startup.lock"
        self.inspector = inspector

    def read(self):
        try:
            raw = read_record_bytes(self.path, 16384)
        except FileNotFoundError:
            return None
        if len(raw) > 16384:
            raise StartupError("Manager startup record is oversized")
        try:

            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate startup field")
                    result[key] = value
                return result

            return validate_record(json.loads(raw, object_pairs_hook=unique))
        except (ValueError, TypeError) as exc:
            raise StartupError(
                "Manager startup record is unreadable; inspect the existing attempt"
            ) from exc

    def write(self, record):
        validate_record(record)
        publish_atomic_record(
            self.path,
            (json.dumps(record, sort_keys=True) + "\n").encode(),
            temporary_label="manager-startup",
        )

    def live(self, record):
        identities = [record[k] for k in ("launcher", "manager") if record[k] is not None]
        if not identities:
            return True  # Spawn may have happened before its identity could be published.
        return any(same_process(self.inspector.inspect(v["pid"]), v) for v in identities)

    def new(self, config):
        return dict(
            schema_version=1,
            config=asdict(config),
            generation=uuid.uuid4().hex,
            manifest_sha256=hashlib.sha256(Path(config.manifest).read_bytes()).hexdigest(),
            launcher=None,
            manager=None,
        )

    def launch_or_reuse(self, config, spawn, *, listener_present, timeout_seconds=5.0):
        """Return one owned attempt. The lock never covers HTTP or worker startup."""
        with exclusive_record_lock(self.lock, timeout_seconds=timeout_seconds):
            record = self.read()
            if record is not None and self.live(record):
                if record["config"] != asdict(config):
                    raise StartupError("Another manager configuration owns this startup")
                return record
            if listener_present():
                raise StartupError(
                    "An unverified listener owns the dashboard port; no manager was started"
                )
            record = self.new(config)
            self.write(
                record
            )  # Persist intent BEFORE spawn; a crash cannot authorize duplicate launch.
            process = spawn(record["generation"])
            record["launcher"] = process_identity(self.inspector.inspect(process.pid))
            self.write(record)
            return record

    def claim(self, config, generation, process_id, *, manifest_sha256=None):
        """Called by the actual manager interpreter before application recovery starts."""
        with exclusive_record_lock(self.lock):
            record = self.read()
            current = self.inspector.inspect(process_id)
            identity = process_identity(current)
            loaded_sha = (
                manifest_sha256 or hashlib.sha256(Path(config.manifest).read_bytes()).hexdigest()
            )
            if generation is not None:
                if (
                    record is None
                    or record["generation"] != generation
                    or record["config"] != asdict(config)
                    or record["manager"] is not None
                    or record["launcher"] is None
                    or record["manifest_sha256"] != loaded_sha
                ):
                    raise StartupError("Manager startup generation differs from its owned launch")
                launcher = record["launcher"]
                if not same_process(self.inspector.inspect(launcher["pid"]), launcher):
                    raise StartupError("Manager launcher lifetime is no longer current")
                if identity != launcher and (
                    current.parent_process_id != launcher["pid"]
                    or identity["creation"] < launcher["creation"]
                ):
                    raise StartupError(
                        "Manager interpreter is not the exact launched process or direct child"
                    )
            else:
                if record is not None and self.live(record):
                    raise StartupError("A manager startup already owns this configuration")
                record = self.new(config)
            record["manifest_sha256"] = loaded_sha
            record["manager"] = identity
            self.write(record)
            return record

    def verify_listener(self, config, generation, payload):
        record = self.read()
        if (
            record is None
            or record["generation"] != generation
            or record["config"] != asdict(config)
            or record["manager"] is None
            or payload != startup_payload(record)
        ):
            raise StartupError("The dashboard listener does not match the exact manager startup")
        manager = record["manager"]
        if not same_process(self.inspector.inspect(manager["pid"]), manager):
            raise StartupError("The dashboard manager process lifetime has changed")
        return record


def startup_payload(record):
    """Only listener/manager identity; never claims worker attachment or gameplay readiness."""
    if record["manager"] is None:
        raise StartupError("Manager interpreter has not claimed startup")
    return dict(
        schema_version=1,
        state="listener_ready",
        generation=record["generation"],
        manager=record["manager"],
        manifest=record["config"]["manifest"],
        node_id=record["config"]["node_id"],
        manifest_sha256=record["manifest_sha256"],
    )
