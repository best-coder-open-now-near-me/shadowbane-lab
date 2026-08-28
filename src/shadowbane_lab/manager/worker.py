"""Durable, fail-closed health supervision for per-client bot workers.

Workers remain local to one PC, but their identity is not the PC or a tactical
role.  A heartbeat binds one exact worker process lifetime to one exact game
client instance in one manifest slot.  The manager only permits effective
dispatch while all three identities still agree and the heartbeat is healthy.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from pathlib import Path
from time import time
from typing import NoReturn

from .manifest import ManagerManifest
from .supervisor import ProcessLifetimeInspector, ProcessLifetimeSnapshot

WORKER_HEARTBEAT_SCHEMA_VERSION = 1
WORKER_DISPATCH_PERMIT_SCHEMA_VERSION = 1
DEFAULT_WORKER_HEARTBEAT_TIMEOUT_SECONDS = 5.0
DEFAULT_WORKER_FUTURE_TOLERANCE_SECONDS = 2.0
DEFAULT_WORKER_DISPATCH_PERMIT_TTL_SECONDS = 2.0
DEFAULT_MAX_WORKER_RECORD_BYTES = 16_384
DEFAULT_MAX_WORKER_RECORDS_PER_SLOT = 256

_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_WORKER_ID_PATTERN = re.compile(r"worker-[0-9a-f]{32}\Z")
_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "node_id",
        "client_id",
        "instance_id",
        "worker_id",
        "process_id",
        "process_started_at_100ns",
        "sequence",
        "observed_at",
        "runtime_state",
        "dispatch_ready",
        "emergency_stop",
        "detail",
        "evidence_sequence",
    }
)
_PERMIT_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "node_id",
        "client_id",
        "instance_id",
        "worker_id",
        "process_id",
        "process_started_at_100ns",
        "heartbeat_sequence",
        "health_state",
        "allowed",
        "issued_at",
        "expires_at",
        "reason",
    }
)


class WorkerHeartbeatError(RuntimeError):
    """Base class for worker heartbeat contract and persistence failures."""


class WorkerHeartbeatFormatError(WorkerHeartbeatError, ValueError):
    """Raised when a heartbeat does not conform to the strict schema."""


class WorkerHeartbeatLedgerError(WorkerHeartbeatError):
    """Raised when the local heartbeat ledger cannot be inspected or written."""


class WorkerRuntimeState(StrEnum):
    """Worker-reported lifecycle, independent of game-client lifecycle state."""

    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class WorkerHealthState(StrEnum):
    """Manager-derived state for one manifest slot."""

    UNBOUND = "unbound"
    MISSING = "missing"
    STARTING = "starting"
    HEALTHY = "healthy"
    BLOCKED = "blocked"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    STALE = "stale"
    EXITED = "exited"
    EMERGENCY_STOPPED = "emergency_stopped"
    IDENTITY_MISMATCH = "identity_mismatch"
    CONFLICT = "conflict"
    INVALID = "invalid"


def _fail(message: str) -> NoReturn:
    raise WorkerHeartbeatFormatError(message)


def _require_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        _fail(
            f"{field_name} must start with an ASCII letter or digit and contain only "
            "letters, digits, '.', '_', or '-' (maximum 128 characters)"
        )
    return value


def _require_worker_id(value: object) -> str:
    if not isinstance(value, str) or not _WORKER_ID_PATTERN.fullmatch(value):
        _fail("worker_id must use the canonical worker-<32 lowercase hex digits> form")
    return value


def _require_optional_identifier(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_identifier(value, field_name)


def _require_optional_worker_id(value: object) -> str | None:
    if value is None:
        return None
    return _require_worker_id(value)


def _require_positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{field_name} must be a positive integer")
    return value


def _require_optional_non_negative_integer(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"{field_name} must be a non-negative integer or null")
    return value


def _require_time(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{field_name} must be a finite non-negative number")
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0:
        _fail(f"{field_name} must be a finite non-negative number")
    return parsed


def _require_optional_detail(value: object) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 512
        or any(character in value for character in "\0\r\n")
    ):
        _fail("detail must be null or canonical text of at most 512 characters")
    return value


def _require_exact_fields(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail("worker heartbeat must be a JSON object")
    keys = set(value)
    if any(not isinstance(key, str) for key in keys):
        _fail("worker heartbeat field names must be strings")
    unknown = keys - _REQUIRED_FIELDS
    missing = _REQUIRED_FIELDS - keys
    if unknown:
        _fail(f"worker heartbeat contains unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        _fail(f"worker heartbeat is missing fields: {', '.join(sorted(missing))}")
    return value


@dataclass(frozen=True, slots=True)
class WorkerHeartbeat:
    """Latest exact ownership and health declaration from one worker process."""

    node_id: str
    client_id: str
    instance_id: str
    worker_id: str
    process_id: int
    process_started_at_100ns: int
    sequence: int
    observed_at: float
    runtime_state: WorkerRuntimeState
    dispatch_ready: bool
    emergency_stop: bool
    detail: str | None = None
    evidence_sequence: int | None = None
    schema_version: int = field(default=WORKER_HEARTBEAT_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.node_id, "node_id")
        _require_identifier(self.client_id, "client_id")
        _require_identifier(self.instance_id, "instance_id")
        _require_worker_id(self.worker_id)
        _require_positive_integer(self.process_id, "process_id")
        _require_positive_integer(
            self.process_started_at_100ns,
            "process_started_at_100ns",
        )
        _require_positive_integer(self.sequence, "sequence")
        _require_time(self.observed_at, "observed_at")
        if not isinstance(self.runtime_state, WorkerRuntimeState):
            _fail("runtime_state must be WorkerRuntimeState")
        if not isinstance(self.dispatch_ready, bool):
            _fail("dispatch_ready must be a boolean")
        if not isinstance(self.emergency_stop, bool):
            _fail("emergency_stop must be a boolean")
        _require_optional_detail(self.detail)
        _require_optional_non_negative_integer(self.evidence_sequence, "evidence_sequence")
        if self.dispatch_ready and self.runtime_state is not WorkerRuntimeState.RUNNING:
            _fail("dispatch_ready may be true only while runtime_state is running")
        if self.dispatch_ready and self.emergency_stop:
            _fail("dispatch_ready must be false after emergency stop")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "client_id": self.client_id,
            "instance_id": self.instance_id,
            "worker_id": self.worker_id,
            "process_id": self.process_id,
            "process_started_at_100ns": self.process_started_at_100ns,
            "sequence": self.sequence,
            "observed_at": self.observed_at,
            "runtime_state": self.runtime_state.value,
            "dispatch_ready": self.dispatch_ready,
            "emergency_stop": self.emergency_stop,
            "detail": self.detail,
            "evidence_sequence": self.evidence_sequence,
        }


@dataclass(frozen=True, slots=True)
class WorkerDispatchPermit:
    """Short-lived manager decision consumed by a worker before guarded input."""

    node_id: str
    client_id: str
    health_state: WorkerHealthState
    allowed: bool
    issued_at: float
    expires_at: float
    reason: str
    instance_id: str | None = None
    worker_id: str | None = None
    process_id: int | None = None
    process_started_at_100ns: int | None = None
    heartbeat_sequence: int | None = None
    schema_version: int = field(default=WORKER_DISPATCH_PERMIT_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.node_id, "node_id")
        _require_identifier(self.client_id, "client_id")
        _require_optional_identifier(self.instance_id, "instance_id")
        _require_optional_worker_id(self.worker_id)
        for value, field_name in (
            (self.process_id, "process_id"),
            (self.process_started_at_100ns, "process_started_at_100ns"),
            (self.heartbeat_sequence, "heartbeat_sequence"),
        ):
            if value is not None:
                _require_positive_integer(value, field_name)
        if not isinstance(self.health_state, WorkerHealthState):
            _fail("health_state must be WorkerHealthState")
        if not isinstance(self.allowed, bool):
            _fail("allowed must be a boolean")
        _require_time(self.issued_at, "issued_at")
        _require_time(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            _fail("expires_at must be later than issued_at")
        if _require_optional_detail(self.reason) is None:
            _fail("reason must be canonical non-empty text")
        identity = (
            self.instance_id,
            self.worker_id,
            self.process_id,
            self.process_started_at_100ns,
            self.heartbeat_sequence,
        )
        if self.allowed and any(value is None for value in identity):
            _fail("allowed permits require exact game, worker, process, and heartbeat identity")
        if self.allowed and self.health_state is not WorkerHealthState.HEALTHY:
            _fail("allowed permits require healthy worker state")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "client_id": self.client_id,
            "instance_id": self.instance_id,
            "worker_id": self.worker_id,
            "process_id": self.process_id,
            "process_started_at_100ns": self.process_started_at_100ns,
            "heartbeat_sequence": self.heartbeat_sequence,
            "health_state": self.health_state.value,
            "allowed": self.allowed,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "reason": self.reason,
        }


def parse_worker_heartbeat(value: object) -> WorkerHeartbeat:
    """Parse one strict schema-v1 heartbeat object."""

    payload = _require_exact_fields(value)
    schema_version = payload["schema_version"]
    if schema_version != WORKER_HEARTBEAT_SCHEMA_VERSION:
        _fail(
            "schema_version must be "
            f"{WORKER_HEARTBEAT_SCHEMA_VERSION}, got {schema_version!r}"
        )
    runtime_value = payload["runtime_state"]
    if not isinstance(runtime_value, str):
        _fail("runtime_state must be a string")
    try:
        runtime_state = WorkerRuntimeState(runtime_value)
    except ValueError as exc:
        _fail(f"runtime_state is unsupported: {runtime_value!r}")
        raise AssertionError from exc
    dispatch_ready = payload["dispatch_ready"]
    emergency_stop = payload["emergency_stop"]
    if not isinstance(dispatch_ready, bool):
        _fail("dispatch_ready must be a boolean")
    if not isinstance(emergency_stop, bool):
        _fail("emergency_stop must be a boolean")
    return WorkerHeartbeat(
        node_id=_require_identifier(payload["node_id"], "node_id"),
        client_id=_require_identifier(payload["client_id"], "client_id"),
        instance_id=_require_identifier(payload["instance_id"], "instance_id"),
        worker_id=_require_worker_id(payload["worker_id"]),
        process_id=_require_positive_integer(payload["process_id"], "process_id"),
        process_started_at_100ns=_require_positive_integer(
            payload["process_started_at_100ns"],
            "process_started_at_100ns",
        ),
        sequence=_require_positive_integer(payload["sequence"], "sequence"),
        observed_at=_require_time(payload["observed_at"], "observed_at"),
        runtime_state=runtime_state,
        dispatch_ready=dispatch_ready,
        emergency_stop=emergency_stop,
        detail=_require_optional_detail(payload["detail"]),
        evidence_sequence=_require_optional_non_negative_integer(
            payload["evidence_sequence"],
            "evidence_sequence",
        ),
    )


def loads_worker_heartbeat(source: str) -> WorkerHeartbeat:
    """Decode strict JSON while rejecting duplicate keys and non-finite numbers."""

    if not isinstance(source, str):
        raise WorkerHeartbeatFormatError("worker heartbeat JSON source must be text")

    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise WorkerHeartbeatFormatError(
                    f"worker heartbeat JSON contains duplicate field {key!r}"
                )
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise WorkerHeartbeatFormatError(
            f"worker heartbeat JSON contains non-finite number {value}"
        )

    try:
        decoded = json.loads(
            source,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except WorkerHeartbeatFormatError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise WorkerHeartbeatFormatError(f"worker heartbeat is not valid JSON: {exc}") from exc
    return parse_worker_heartbeat(decoded)


def parse_worker_dispatch_permit(value: object) -> WorkerDispatchPermit:
    """Parse one strict schema-v1 manager-to-worker dispatch decision."""

    if not isinstance(value, Mapping):
        _fail("worker dispatch permit must be a JSON object")
    keys = set(value)
    if any(not isinstance(key, str) for key in keys):
        _fail("worker dispatch permit field names must be strings")
    unknown = keys - _PERMIT_REQUIRED_FIELDS
    missing = _PERMIT_REQUIRED_FIELDS - keys
    if unknown:
        _fail(f"worker dispatch permit contains unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        _fail(f"worker dispatch permit is missing fields: {', '.join(sorted(missing))}")
    if value["schema_version"] != WORKER_DISPATCH_PERMIT_SCHEMA_VERSION:
        _fail(f"dispatch permit schema_version must be {WORKER_DISPATCH_PERMIT_SCHEMA_VERSION}")
    health_value = value["health_state"]
    if not isinstance(health_value, str):
        _fail("health_state must be a string")
    try:
        health_state = WorkerHealthState(health_value)
    except ValueError as exc:
        _fail(f"health_state is unsupported: {health_value!r}")
        raise AssertionError from exc
    allowed = value["allowed"]
    if not isinstance(allowed, bool):
        _fail("allowed must be a boolean")
    reason = _require_optional_detail(value["reason"])
    if reason is None:
        _fail("reason must be canonical non-empty text")
    return WorkerDispatchPermit(
        node_id=_require_identifier(value["node_id"], "node_id"),
        client_id=_require_identifier(value["client_id"], "client_id"),
        instance_id=_require_optional_identifier(value["instance_id"], "instance_id"),
        worker_id=_require_optional_worker_id(value["worker_id"]),
        process_id=(
            None
            if value["process_id"] is None
            else _require_positive_integer(value["process_id"], "process_id")
        ),
        process_started_at_100ns=(
            None
            if value["process_started_at_100ns"] is None
            else _require_positive_integer(
                value["process_started_at_100ns"],
                "process_started_at_100ns",
            )
        ),
        heartbeat_sequence=(
            None
            if value["heartbeat_sequence"] is None
            else _require_positive_integer(
                value["heartbeat_sequence"],
                "heartbeat_sequence",
            )
        ),
        health_state=health_state,
        allowed=allowed,
        issued_at=_require_time(value["issued_at"], "issued_at"),
        expires_at=_require_time(value["expires_at"], "expires_at"),
        reason=reason,
    )


def loads_worker_dispatch_permit(source: str) -> WorkerDispatchPermit:
    """Decode a strict dispatch permit while rejecting duplicate and non-finite JSON."""

    if not isinstance(source, str):
        raise WorkerHeartbeatFormatError("worker dispatch permit JSON source must be text")

    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise WorkerHeartbeatFormatError(
                    f"worker dispatch permit JSON contains duplicate field {key!r}"
                )
            result[key] = item
        return result

    def reject_constant(item: str) -> NoReturn:
        raise WorkerHeartbeatFormatError(
            f"worker dispatch permit JSON contains non-finite number {item}"
        )

    try:
        decoded = json.loads(
            source,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except WorkerHeartbeatFormatError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise WorkerHeartbeatFormatError(
            f"worker dispatch permit is not valid JSON: {exc}"
        ) from exc
    return parse_worker_dispatch_permit(decoded)


@dataclass(frozen=True, slots=True)
class WorkerLedgerIssue:
    """Bounded operator-safe description of one unreadable ledger entry."""

    file_name: str
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"file_name": self.file_name, "code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class WorkerLedgerSnapshot:
    """All parseable records and bounded issues for one manifest slot."""

    client_id: str
    records: tuple[WorkerHeartbeat, ...]
    issues: tuple[WorkerLedgerIssue, ...] = ()


class WorkerHeartbeatLedger:
    """Atomic file ledger shared by the manager and independent local workers."""

    def __init__(
        self,
        manifest: ManagerManifest,
        root: str | Path,
        *,
        max_record_bytes: int = DEFAULT_MAX_WORKER_RECORD_BYTES,
        max_records_per_slot: int = DEFAULT_MAX_WORKER_RECORDS_PER_SLOT,
    ) -> None:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        if isinstance(max_record_bytes, bool) or not isinstance(max_record_bytes, int):
            raise ValueError("max_record_bytes must be an integer")
        if max_record_bytes < 1_024:
            raise ValueError("max_record_bytes must be at least 1024")
        if (
            isinstance(max_records_per_slot, bool)
            or not isinstance(max_records_per_slot, int)
            or max_records_per_slot <= 0
        ):
            raise ValueError("max_records_per_slot must be a positive integer")
        requested_root = Path(root)
        if os.name == "nt" and str(requested_root).startswith("\\\\"):
            raise ValueError("worker heartbeat root must be node-local, not a UNC share")
        resolved_root = requested_root.resolve(strict=False)
        self._manifest = manifest
        self._root = resolved_root
        self._max_record_bytes = max_record_bytes
        self._max_records_per_slot = max_records_per_slot
        self._client_ids = {
            config.client_id.casefold(): config.client_id for config in manifest.clients
        }

    @property
    def root(self) -> Path:
        return self._root

    @property
    def node_id(self) -> str:
        return self._manifest.node_id

    def _canonical_client_id(self, client_id: str) -> str:
        _require_identifier(client_id, "client_id")
        canonical = self._client_ids.get(client_id.casefold())
        if canonical is None:
            raise WorkerHeartbeatLedgerError(f"unknown manifest client_id {client_id!r}")
        return canonical

    def _slot_directory(self, client_id: str) -> Path:
        canonical = self._canonical_client_id(client_id)
        root = self._root.resolve(strict=False)
        directory = root / self._manifest.node_id / canonical
        if not directory.resolve(strict=False).is_relative_to(root):
            raise WorkerHeartbeatLedgerError("worker heartbeat path escaped its state root")
        return directory

    def publish(self, heartbeat: WorkerHeartbeat) -> Path:
        """Atomically replace only this worker identity's latest heartbeat."""

        if not isinstance(heartbeat, WorkerHeartbeat):
            raise ValueError("heartbeat must be WorkerHeartbeat")
        canonical = self._canonical_client_id(heartbeat.client_id)
        if heartbeat.node_id != self._manifest.node_id or heartbeat.client_id != canonical:
            raise WorkerHeartbeatLedgerError(
                "heartbeat node_id and client_id must exactly match the manager manifest"
            )
        directory = self._slot_directory(canonical)
        target = directory / f"{heartbeat.worker_id}.json"
        temporary = directory / f".{heartbeat.worker_id}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        payload = json.dumps(
            heartbeat.to_dict(),
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(payload) > self._max_record_bytes:
            raise WorkerHeartbeatLedgerError("serialized worker heartbeat exceeds size limit")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with temporary.open("xb") as destination:
                destination.write(payload)
                destination.flush()
                os.fsync(destination.fileno())
            temporary.replace(target)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise WorkerHeartbeatLedgerError(f"could not persist worker heartbeat: {exc}") from exc
        return target

    def publish_permit(self, permit: WorkerDispatchPermit) -> Path:
        """Atomically replace the manager's short-lived decision for one slot."""

        if not isinstance(permit, WorkerDispatchPermit):
            raise ValueError("permit must be WorkerDispatchPermit")
        canonical = self._canonical_client_id(permit.client_id)
        if permit.node_id != self._manifest.node_id or permit.client_id != canonical:
            raise WorkerHeartbeatLedgerError(
                "dispatch permit node_id and client_id must exactly match the manifest"
            )
        directory = self._slot_directory(canonical)
        target = directory / "dispatch.permit"
        temporary = directory / f".dispatch.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        payload = json.dumps(
            permit.to_dict(),
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(payload) > self._max_record_bytes:
            raise WorkerHeartbeatLedgerError("serialized worker dispatch permit exceeds size limit")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with temporary.open("xb") as destination:
                destination.write(payload)
                destination.flush()
                os.fsync(destination.fileno())
            temporary.replace(target)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise WorkerHeartbeatLedgerError(
                f"could not persist worker dispatch permit: {exc}"
            ) from exc
        return target

    def inspect_permit(self, client_id: str) -> WorkerDispatchPermit | None:
        """Read the latest permit for worker-side fail-closed dispatch checks."""

        canonical = self._canonical_client_id(client_id)
        target = self._slot_directory(canonical) / "dispatch.permit"
        try:
            if not target.exists():
                return None
            if target.is_symlink() or not target.is_file():
                raise WorkerHeartbeatFormatError("dispatch permit must be a regular file")
            source = target.read_bytes()
        except OSError as exc:
            raise WorkerHeartbeatLedgerError(
                f"could not read worker dispatch permit: {exc}"
            ) from exc
        if len(source) > self._max_record_bytes:
            raise WorkerHeartbeatFormatError("worker dispatch permit exceeds size limit")
        try:
            permit = loads_worker_dispatch_permit(source.decode("utf-8", errors="strict"))
        except UnicodeDecodeError as exc:
            raise WorkerHeartbeatFormatError("worker dispatch permit must be UTF-8") from exc
        if permit.node_id != self._manifest.node_id or permit.client_id != canonical:
            raise WorkerHeartbeatFormatError(
                "worker dispatch permit identity does not match its manifest slot"
            )
        return permit

    def inspect(self, client_id: str) -> WorkerLedgerSnapshot:
        """Read one slot without trusting file names or record contents."""

        canonical = self._canonical_client_id(client_id)
        directory = self._slot_directory(canonical)
        try:
            if not directory.exists():
                return WorkerLedgerSnapshot(client_id=canonical, records=())
            if directory.is_symlink() or not directory.is_dir():
                issue = WorkerLedgerIssue(
                    file_name="*",
                    code="invalid-slot-directory",
                    detail="worker heartbeat slot path must be a regular directory",
                )
                return WorkerLedgerSnapshot(client_id=canonical, records=(), issues=(issue,))
            entries = sorted(
                (entry for entry in directory.iterdir() if entry.name.endswith(".json")),
                key=lambda entry: entry.name,
            )
        except OSError as exc:
            raise WorkerHeartbeatLedgerError(
                f"could not inspect heartbeat directory for {canonical}: {exc}"
            ) from exc
        if len(entries) > self._max_records_per_slot:
            issue = WorkerLedgerIssue(
                file_name="*",
                code="record-limit-exceeded",
                detail=(
                    f"slot contains {len(entries)} heartbeat records; "
                    f"limit is {self._max_records_per_slot}"
                ),
            )
            return WorkerLedgerSnapshot(client_id=canonical, records=(), issues=(issue,))

        records: list[WorkerHeartbeat] = []
        issues: list[WorkerLedgerIssue] = []
        for entry in entries:
            try:
                if entry.is_symlink() or not entry.is_file():
                    raise WorkerHeartbeatFormatError("heartbeat entry must be a regular file")
                source = entry.read_bytes()
                if len(source) > self._max_record_bytes:
                    raise WorkerHeartbeatFormatError("heartbeat record exceeds size limit")
                heartbeat = loads_worker_heartbeat(source.decode("utf-8", errors="strict"))
                if heartbeat.node_id != self._manifest.node_id:
                    raise WorkerHeartbeatFormatError("heartbeat node_id does not match this node")
                if heartbeat.client_id != canonical:
                    raise WorkerHeartbeatFormatError("heartbeat client_id does not match its slot")
                if entry.name != f"{heartbeat.worker_id}.json":
                    raise WorkerHeartbeatFormatError("heartbeat file name does not match worker_id")
                records.append(heartbeat)
            except (OSError, UnicodeDecodeError, WorkerHeartbeatFormatError) as exc:
                issues.append(
                    WorkerLedgerIssue(
                        file_name=entry.name[:160],
                        code="invalid-record",
                        detail=str(exc)[:512],
                    )
                )
        records.sort(key=lambda item: (item.observed_at, item.worker_id), reverse=True)
        issues.sort(key=lambda item: (item.file_name, item.code, item.detail))
        return WorkerLedgerSnapshot(
            client_id=canonical,
            records=tuple(records),
            issues=tuple(issues),
        )


@dataclass(frozen=True, slots=True)
class WorkerSlotHealthSnapshot:
    """Manager-derived worker health and effective dispatch gate for one slot."""

    client_id: str
    state: WorkerHealthState
    dispatch_allowed: bool
    active_worker_count: int
    heartbeat: WorkerHeartbeat | None = None
    heartbeat_age_seconds: float | None = None
    detail: str | None = None
    issues: tuple[WorkerLedgerIssue, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "state": self.state.value,
            "dispatch_allowed": self.dispatch_allowed,
            "active_worker_count": self.active_worker_count,
            "heartbeat_age_seconds": self.heartbeat_age_seconds,
            "detail": self.detail,
            "heartbeat": None if self.heartbeat is None else self.heartbeat.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class _AssessedHeartbeat:
    heartbeat: WorkerHeartbeat
    state: WorkerHealthState
    age_seconds: float
    detail: str
    active: bool


class WorkerSupervisor:
    """Derive exact per-slot worker health from the durable local ledger."""

    def __init__(
        self,
        ledger: WorkerHeartbeatLedger,
        process_inspector: ProcessLifetimeInspector,
        *,
        clock: Callable[[], float] = time,
        heartbeat_timeout_seconds: float = DEFAULT_WORKER_HEARTBEAT_TIMEOUT_SECONDS,
        future_tolerance_seconds: float = DEFAULT_WORKER_FUTURE_TOLERANCE_SECONDS,
        permit_ttl_seconds: float = DEFAULT_WORKER_DISPATCH_PERMIT_TTL_SECONDS,
    ) -> None:
        if not isinstance(ledger, WorkerHeartbeatLedger):
            raise ValueError("ledger must be WorkerHeartbeatLedger")
        if not callable(getattr(process_inspector, "inspect", None)):
            raise ValueError("process_inspector must provide inspect(process_id)")
        if not callable(clock):
            raise ValueError("clock must be callable")
        for value, field_name in (
            (heartbeat_timeout_seconds, "heartbeat_timeout_seconds"),
            (future_tolerance_seconds, "future_tolerance_seconds"),
            (permit_ttl_seconds, "permit_ttl_seconds"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field_name} must be a finite non-negative number")
            if not isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be a finite non-negative number")
        if heartbeat_timeout_seconds <= 0:
            raise ValueError("heartbeat_timeout_seconds must be positive")
        if permit_ttl_seconds <= 0:
            raise ValueError("permit_ttl_seconds must be positive")
        self._ledger = ledger
        self._process_inspector = process_inspector
        self._clock = clock
        self._timeout = float(heartbeat_timeout_seconds)
        self._future_tolerance = float(future_tolerance_seconds)
        self._permit_ttl = float(permit_ttl_seconds)
        self._last_seen: dict[tuple[str, str], WorkerHeartbeat] = {}
        self._lock = threading.RLock()

    def inspect(
        self,
        client_id: str,
        *,
        instance_id: str | None,
        lifecycle_dispatch_enabled: bool,
    ) -> WorkerSlotHealthSnapshot:
        """Return health; effective dispatch is a conjunction, never an assumption."""

        if instance_id is not None:
            _require_identifier(instance_id, "instance_id")
        if not isinstance(lifecycle_dispatch_enabled, bool):
            raise ValueError("lifecycle_dispatch_enabled must be a boolean")
        with self._lock:
            now = _require_time(self._clock(), "clock result")
            ledger = self._ledger.inspect(client_id)
            if instance_id is None:
                return self._publish_health(
                    WorkerSlotHealthSnapshot(
                        client_id=ledger.client_id,
                        state=WorkerHealthState.UNBOUND,
                        dispatch_allowed=False,
                        active_worker_count=0,
                        heartbeat=ledger.records[0] if ledger.records else None,
                        detail="no current exact game-client binding owns this slot",
                        issues=ledger.issues,
                    ),
                    now=now,
                )
            if ledger.issues:
                return self._publish_health(
                    WorkerSlotHealthSnapshot(
                        client_id=ledger.client_id,
                        state=WorkerHealthState.INVALID,
                        dispatch_allowed=False,
                        active_worker_count=0,
                        heartbeat=ledger.records[0] if ledger.records else None,
                        detail="one or more local worker heartbeat records are invalid",
                        issues=ledger.issues,
                    ),
                    now=now,
                )
            if not ledger.records:
                return self._publish_health(
                    WorkerSlotHealthSnapshot(
                        client_id=ledger.client_id,
                        state=WorkerHealthState.MISSING,
                        dispatch_allowed=False,
                        active_worker_count=0,
                        detail="no worker heartbeat has claimed this exact slot",
                    ),
                    now=now,
                )

            assessments = tuple(
                self._assess(record, instance_id=instance_id, now=now)
                for record in ledger.records
            )
            active = tuple(item for item in assessments if item.active)
            if len(active) > 1:
                return self._publish_health(
                    WorkerSlotHealthSnapshot(
                        client_id=ledger.client_id,
                        state=WorkerHealthState.CONFLICT,
                        dispatch_allowed=False,
                        active_worker_count=len(active),
                        heartbeat=active[0].heartbeat,
                        heartbeat_age_seconds=active[0].age_seconds,
                        detail="multiple live worker process lifetimes claim this manifest slot",
                    ),
                    now=now,
                )
            selected = active[0] if active else assessments[0]
            dispatch_allowed = (
                lifecycle_dispatch_enabled
                and selected.state is WorkerHealthState.HEALTHY
                and selected.heartbeat.instance_id == instance_id
            )
            detail = selected.detail
            if selected.state is WorkerHealthState.HEALTHY and not lifecycle_dispatch_enabled:
                detail = "worker is healthy, but client lifecycle dispatch is paused"
            return self._publish_health(
                WorkerSlotHealthSnapshot(
                    client_id=ledger.client_id,
                    state=selected.state,
                    dispatch_allowed=dispatch_allowed,
                    active_worker_count=len(active),
                    heartbeat=selected.heartbeat,
                    heartbeat_age_seconds=selected.age_seconds,
                    detail=detail,
                ),
                now=now,
            )

    def revoke(self, client_id: str, *, reason: str) -> WorkerDispatchPermit:
        """Synchronously replace any prior allow decision with a short-lived denial."""

        parsed_reason = _require_optional_detail(reason)
        if parsed_reason is None:
            raise ValueError("reason must be canonical non-empty text")
        with self._lock:
            now = _require_time(self._clock(), "clock result")
            permit = WorkerDispatchPermit(
                node_id=self._ledger.node_id,
                client_id=client_id,
                health_state=WorkerHealthState.BLOCKED,
                allowed=False,
                issued_at=now,
                expires_at=now + self._permit_ttl,
                reason=parsed_reason,
            )
            self._ledger.publish_permit(permit)
            return permit

    def _publish_health(
        self,
        health: WorkerSlotHealthSnapshot,
        *,
        now: float,
    ) -> WorkerSlotHealthSnapshot:
        heartbeat = health.heartbeat
        expires_at = now + self._permit_ttl
        if health.dispatch_allowed:
            assert heartbeat is not None
            expires_at = min(expires_at, heartbeat.observed_at + self._timeout)
        permit = WorkerDispatchPermit(
            node_id=self._ledger.node_id,
            client_id=health.client_id,
            instance_id=None if heartbeat is None else heartbeat.instance_id,
            worker_id=None if heartbeat is None else heartbeat.worker_id,
            process_id=None if heartbeat is None else heartbeat.process_id,
            process_started_at_100ns=(
                None if heartbeat is None else heartbeat.process_started_at_100ns
            ),
            heartbeat_sequence=None if heartbeat is None else heartbeat.sequence,
            health_state=health.state,
            allowed=health.dispatch_allowed,
            issued_at=now,
            expires_at=expires_at,
            reason=health.detail or f"worker health is {health.state.value}",
        )
        self._ledger.publish_permit(permit)
        return health

    def _assess(
        self,
        heartbeat: WorkerHeartbeat,
        *,
        instance_id: str,
        now: float,
    ) -> _AssessedHeartbeat:
        age = max(0.0, now - heartbeat.observed_at)
        if heartbeat.observed_at > now + self._future_tolerance:
            return _AssessedHeartbeat(
                heartbeat,
                WorkerHealthState.INVALID,
                age,
                "worker heartbeat timestamp is implausibly in the future",
                False,
            )
        prior = self._last_seen.get((heartbeat.client_id, heartbeat.worker_id))
        if prior is not None:
            if heartbeat.sequence < prior.sequence or (
                heartbeat.sequence == prior.sequence and heartbeat != prior
            ):
                return _AssessedHeartbeat(
                    heartbeat,
                    WorkerHealthState.INVALID,
                    age,
                    "worker heartbeat sequence replay or collision was detected",
                    False,
                )
            if heartbeat.sequence > prior.sequence and heartbeat.observed_at <= prior.observed_at:
                return _AssessedHeartbeat(
                    heartbeat,
                    WorkerHealthState.INVALID,
                    age,
                    "worker heartbeat time did not advance with its sequence",
                    False,
                )
            if prior.emergency_stop and not heartbeat.emergency_stop:
                return _AssessedHeartbeat(
                    heartbeat,
                    WorkerHealthState.INVALID,
                    age,
                    "worker attempted to clear a one-way emergency stop without restarting",
                    False,
                )
        if prior is None or heartbeat.sequence > prior.sequence:
            self._last_seen[(heartbeat.client_id, heartbeat.worker_id)] = heartbeat

        if age >= self._timeout:
            return _AssessedHeartbeat(
                heartbeat,
                WorkerHealthState.STALE,
                age,
                "worker heartbeat expired",
                False,
            )
        try:
            process = self._process_inspector.inspect(heartbeat.process_id)
        except (OSError, RuntimeError, ValueError):
            return _AssessedHeartbeat(
                heartbeat,
                WorkerHealthState.INVALID,
                age,
                "worker process lifetime could not be verified",
                False,
            )
        if process is not None and not isinstance(process, ProcessLifetimeSnapshot):
            return _AssessedHeartbeat(
                heartbeat,
                WorkerHealthState.INVALID,
                age,
                "worker process inspector returned an invalid lifetime",
                False,
            )
        if process is None or (
            process.process_started_at_100ns != heartbeat.process_started_at_100ns
        ):
            return _AssessedHeartbeat(
                heartbeat,
                WorkerHealthState.EXITED,
                age,
                "exact worker process lifetime is no longer running",
                False,
            )
        if heartbeat.instance_id != instance_id:
            return _AssessedHeartbeat(
                heartbeat,
                WorkerHealthState.IDENTITY_MISMATCH,
                age,
                "worker is bound to a different exact game-client instance",
                True,
            )
        if heartbeat.emergency_stop:
            return _AssessedHeartbeat(
                heartbeat,
                WorkerHealthState.EMERGENCY_STOPPED,
                age,
                "worker emergency stop is tripped and cannot be cleared in this process",
                True,
            )
        state_map = {
            WorkerRuntimeState.STARTING: WorkerHealthState.STARTING,
            WorkerRuntimeState.DEGRADED: WorkerHealthState.DEGRADED,
            WorkerRuntimeState.STOPPING: WorkerHealthState.STOPPING,
            WorkerRuntimeState.STOPPED: WorkerHealthState.STOPPED,
            WorkerRuntimeState.FAILED: WorkerHealthState.FAILED,
        }
        if heartbeat.runtime_state is WorkerRuntimeState.RUNNING:
            if heartbeat.dispatch_ready:
                return _AssessedHeartbeat(
                    heartbeat,
                    WorkerHealthState.HEALTHY,
                    age,
                    heartbeat.detail or "worker heartbeat and process lifetime are healthy",
                    True,
                )
            return _AssessedHeartbeat(
                heartbeat,
                WorkerHealthState.BLOCKED,
                age,
                heartbeat.detail or "worker is running but has not enabled guarded dispatch",
                True,
            )
        derived = state_map[heartbeat.runtime_state]
        return _AssessedHeartbeat(
            heartbeat,
            derived,
            age,
            heartbeat.detail or f"worker reports {heartbeat.runtime_state.value}",
            derived not in {WorkerHealthState.STOPPED, WorkerHealthState.FAILED},
        )


class WorkerDispatchGate:
    """Worker-side dynamic stop signal backed by the manager's expiring permit."""

    def __init__(
        self,
        ledger: WorkerHeartbeatLedger,
        *,
        node_id: str,
        client_id: str,
        instance_id: str,
        worker_id: str,
        process: ProcessLifetimeSnapshot,
        clock: Callable[[], float] = time,
        future_tolerance_seconds: float = DEFAULT_WORKER_FUTURE_TOLERANCE_SECONDS,
    ) -> None:
        if not isinstance(ledger, WorkerHeartbeatLedger):
            raise ValueError("ledger must be WorkerHeartbeatLedger")
        if not isinstance(process, ProcessLifetimeSnapshot):
            raise ValueError("process must be ProcessLifetimeSnapshot")
        if not callable(clock):
            raise ValueError("clock must be callable")
        if (
            isinstance(future_tolerance_seconds, bool)
            or not isinstance(future_tolerance_seconds, (int, float))
            or not isfinite(future_tolerance_seconds)
            or future_tolerance_seconds < 0
        ):
            raise ValueError("future_tolerance_seconds must be finite and non-negative")
        self._ledger = ledger
        self._node_id = _require_identifier(node_id, "node_id")
        self._client_id = _require_identifier(client_id, "client_id")
        self._instance_id = _require_identifier(instance_id, "instance_id")
        self._worker_id = _require_worker_id(worker_id)
        self._process = process
        self._clock = clock
        self._future_tolerance = float(future_tolerance_seconds)

    def allows_dispatch(self) -> bool:
        """Return true only for a current permit matching every exact identity."""

        try:
            now = _require_time(self._clock(), "clock result")
            permit = self._ledger.inspect_permit(self._client_id)
        except (OSError, RuntimeError, ValueError, WorkerHeartbeatError):
            return False
        if permit is None or not permit.allowed:
            return False
        if permit.issued_at > now + self._future_tolerance or now >= permit.expires_at:
            return False
        return (
            permit.node_id == self._node_id
            and permit.client_id == self._client_id
            and permit.instance_id == self._instance_id
            and permit.worker_id == self._worker_id
            and permit.process_id == self._process.process_id
            and (
                permit.process_started_at_100ns
                == self._process.process_started_at_100ns
            )
            and permit.health_state is WorkerHealthState.HEALTHY
        )

    def is_set(self) -> bool:
        """Implement ``StopSignal`` semantics for ``GuardedInputExecutor``."""

        return not self.allows_dispatch()


class WorkerHeartbeatPublisher:
    """Worker-side sequencer that atomically publishes one exact process lease."""

    def __init__(
        self,
        ledger: WorkerHeartbeatLedger,
        *,
        node_id: str,
        client_id: str,
        instance_id: str,
        process: ProcessLifetimeSnapshot,
        worker_id: str | None = None,
        clock: Callable[[], float] = time,
    ) -> None:
        if not isinstance(ledger, WorkerHeartbeatLedger):
            raise ValueError("ledger must be WorkerHeartbeatLedger")
        if not isinstance(process, ProcessLifetimeSnapshot):
            raise ValueError("process must be ProcessLifetimeSnapshot")
        if not callable(clock):
            raise ValueError("clock must be callable")
        self._ledger = ledger
        self._node_id = _require_identifier(node_id, "node_id")
        self._client_id = _require_identifier(client_id, "client_id")
        self._instance_id = _require_identifier(instance_id, "instance_id")
        self._process = process
        self._worker_id = _require_worker_id(
            worker_id if worker_id is not None else f"worker-{uuid.uuid4().hex}"
        )
        self._clock = clock
        self._sequence = 0
        self._last_observed_at = -1.0
        self._emergency_stop = False
        self._closed = False
        self._last: WorkerHeartbeat | None = None
        self._lock = threading.Lock()

    @property
    def worker_id(self) -> str:
        return self._worker_id

    def dispatch_gate(self) -> WorkerDispatchGate:
        """Build the exact dynamic stop signal this worker must use for live input."""

        return WorkerDispatchGate(
            self._ledger,
            node_id=self._node_id,
            client_id=self._client_id,
            instance_id=self._instance_id,
            worker_id=self._worker_id,
            process=self._process,
            clock=self._clock,
        )

    def publish(
        self,
        runtime_state: WorkerRuntimeState,
        *,
        dispatch_ready: bool = False,
        emergency_stop: bool = False,
        detail: str | None = None,
        evidence_sequence: int | None = None,
    ) -> WorkerHeartbeat:
        with self._lock:
            if self._closed:
                raise WorkerHeartbeatError("worker heartbeat publisher is closed")
            if not isinstance(dispatch_ready, bool):
                raise ValueError("dispatch_ready must be a boolean")
            if not isinstance(emergency_stop, bool):
                raise ValueError("emergency_stop must be a boolean")
            self._emergency_stop = self._emergency_stop or emergency_stop
            observed_at = max(
                _require_time(self._clock(), "clock result"),
                self._last_observed_at + 0.000001,
            )
            self._sequence += 1
            heartbeat = WorkerHeartbeat(
                node_id=self._node_id,
                client_id=self._client_id,
                instance_id=self._instance_id,
                worker_id=self._worker_id,
                process_id=self._process.process_id,
                process_started_at_100ns=self._process.process_started_at_100ns,
                sequence=self._sequence,
                observed_at=observed_at,
                runtime_state=runtime_state,
                dispatch_ready=dispatch_ready and not self._emergency_stop,
                emergency_stop=self._emergency_stop,
                detail=detail,
                evidence_sequence=evidence_sequence,
            )
            self._ledger.publish(heartbeat)
            self._last_observed_at = observed_at
            self._last = heartbeat
            return heartbeat

    def close(self, *, detail: str | None = None) -> WorkerHeartbeat | None:
        with self._lock:
            if self._closed:
                return self._last
        final = self.publish(WorkerRuntimeState.STOPPED, detail=detail)
        with self._lock:
            self._closed = True
        return final


__all__ = [
    "DEFAULT_MAX_WORKER_RECORD_BYTES",
    "DEFAULT_MAX_WORKER_RECORDS_PER_SLOT",
    "DEFAULT_WORKER_FUTURE_TOLERANCE_SECONDS",
    "DEFAULT_WORKER_HEARTBEAT_TIMEOUT_SECONDS",
    "DEFAULT_WORKER_DISPATCH_PERMIT_TTL_SECONDS",
    "WORKER_DISPATCH_PERMIT_SCHEMA_VERSION",
    "WORKER_HEARTBEAT_SCHEMA_VERSION",
    "WorkerDispatchGate",
    "WorkerDispatchPermit",
    "WorkerHealthState",
    "WorkerHeartbeat",
    "WorkerHeartbeatError",
    "WorkerHeartbeatFormatError",
    "WorkerHeartbeatLedger",
    "WorkerHeartbeatLedgerError",
    "WorkerHeartbeatPublisher",
    "WorkerLedgerIssue",
    "WorkerLedgerSnapshot",
    "WorkerRuntimeState",
    "WorkerSlotHealthSnapshot",
    "WorkerSupervisor",
    "loads_worker_dispatch_permit",
    "loads_worker_heartbeat",
    "parse_worker_dispatch_permit",
    "parse_worker_heartbeat",
]
