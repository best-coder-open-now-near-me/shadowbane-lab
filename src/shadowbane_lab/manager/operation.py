"""Immutable node-local operation channel for exact per-client workers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import NoReturn

from shadowbane_lab.record_store import (
    exclusive_record_lock,
    publish_atomic_record,
    read_record_bytes,
)

from .manifest import ManagerManifest
from .worker import WorkerDispatchPermit

WORKER_OPERATION_SCHEMA_VERSION = 1
WORKER_OPERATION_RECEIPT_SCHEMA_VERSION = 1
DEFAULT_WORKER_OPERATION_TTL_SECONDS = 8.0
DEFAULT_WORKER_OPERATION_ACK_TIMEOUT_SECONDS = 2.0
DEFAULT_MAX_WORKER_OPERATION_BYTES = 16_384
DEFAULT_MAX_WORKER_OPERATIONS_PER_SLOT = 256
DEFAULT_WORKER_OPERATION_TERMINAL_RETENTION_SECONDS = 7 * 24 * 60 * 60

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_WORKER_ID = re.compile(r"worker-[0-9a-f]{32}\Z")
_OPERATION_ID = re.compile(r"operation-[0-9a-f]{32}\Z")
_DEDUPLICATION_ID = re.compile(r"dedup-[0-9a-f]{64}\Z")
_OPERATION_FIELDS = frozenset(
    {
        "schema_version",
        "node_id",
        "client_id",
        "instance_id",
        "worker_id",
        "worker_process_id",
        "worker_process_started_at_100ns",
        "operation_id",
        "deduplication_id",
        "kind",
        "command",
        "destination",
        "issued_at",
        "expires_at",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "node_id",
        "client_id",
        "instance_id",
        "worker_id",
        "worker_process_id",
        "worker_process_started_at_100ns",
        "operation_id",
        "deduplication_id",
        "kind",
        "state",
        "observed_at",
        "detail",
    }
)


class WorkerOperationError(RuntimeError):
    """Base class for operation channel failures."""


class WorkerOperationFormatError(WorkerOperationError, ValueError):
    """Raised when an operation or receipt violates its strict schema."""


class WorkerOperationLedgerError(WorkerOperationError):
    """Raised when the node-local operation ledger cannot be used safely."""


class WorkerOperationKind(StrEnum):
    TRAVEL = "travel"
    PVE = "pve"
    VENDOR = "vendor"
    GUARD = "guard"
    CONDEMN = "condemn"
    CANCEL = "cancel"
    STOP = "stop"


class WorkerOperationState(StrEnum):
    ACCEPTED = "accepted"
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"

    @property
    def terminal(self) -> bool:
        return self in {
            WorkerOperationState.SUCCEEDED,
            WorkerOperationState.FAILED,
            WorkerOperationState.CANCELLED,
            WorkerOperationState.EXPIRED,
            WorkerOperationState.REJECTED,
        }


def _fail(message: str) -> NoReturn:
    raise WorkerOperationFormatError(message)


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        _fail(f"{field_name} must be a canonical identifier")
    return value


def _pattern(value: object, field_name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        _fail(f"{field_name} is not canonical")
    return value


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{field_name} must be a positive integer")
    return value


def _finite_time(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{field_name} must be a finite non-negative number")
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0:
        _fail(f"{field_name} must be a finite non-negative number")
    return parsed


def _detail(value: object) -> str | None:
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


def _command(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 512
        or any(character in value for character in "\0\r\n")
    ):
        _fail("command must be canonical text of at most 512 characters")
    return value


def _exact_mapping(value: object, fields: frozenset[str], description: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(f"{description} must be a JSON object")
    keys = set(value)
    if any(not isinstance(key, str) for key in keys):
        _fail(f"{description} field names must be strings")
    unknown = keys - fields
    missing = fields - keys
    if unknown:
        _fail(f"{description} contains unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        _fail(f"{description} is missing fields: {', '.join(sorted(missing))}")
    return value


@dataclass(frozen=True, slots=True)
class WorkerTravelDestination:
    lt: float
    lg: float
    radius: float | None = None

    def __post_init__(self) -> None:
        _finite_time(self.lt, "destination.lt")
        _finite_time(self.lg, "destination.lg")
        if self.radius is not None:
            radius = _finite_time(self.radius, "destination.radius")
            if radius <= 0:
                _fail("destination.radius must be positive when present")

    def to_dict(self) -> dict[str, float | None]:
        return {"lt": self.lt, "lg": self.lg, "radius": self.radius}


@dataclass(frozen=True, slots=True)
class WorkerOperation:
    node_id: str
    client_id: str
    instance_id: str
    worker_id: str
    worker_process_id: int
    worker_process_started_at_100ns: int
    operation_id: str
    deduplication_id: str
    kind: WorkerOperationKind
    command: str
    destination: WorkerTravelDestination | None
    issued_at: float
    expires_at: float
    schema_version: int = field(default=WORKER_OPERATION_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _identifier(self.node_id, "node_id")
        _identifier(self.client_id, "client_id")
        _identifier(self.instance_id, "instance_id")
        _pattern(self.worker_id, "worker_id", _WORKER_ID)
        _positive_integer(self.worker_process_id, "worker_process_id")
        _positive_integer(
            self.worker_process_started_at_100ns,
            "worker_process_started_at_100ns",
        )
        _pattern(self.operation_id, "operation_id", _OPERATION_ID)
        _pattern(self.deduplication_id, "deduplication_id", _DEDUPLICATION_ID)
        if not isinstance(self.kind, WorkerOperationKind):
            _fail("kind must be WorkerOperationKind")
        _command(self.command)
        if self.kind is WorkerOperationKind.VENDOR and re.fullmatch(
            r"vendor (?:start(?: [0-9a-f]{32})?|discover|recipes|"
            r"recipe [0-9a-f]{32} [1-9][0-9]{0,9}|resume [0-9a-f]{32})", self.command
        ) is None:
            _fail("invalid vendor job command")
        if self.kind is WorkerOperationKind.GUARD and re.fullmatch(
            r"guard (?:discover|(?:start|resume|continue) operation-[0-9a-f]{32})", self.command
        ) is None:
            _fail("invalid guard job command")
        if self.kind is WorkerOperationKind.CONDEMN and re.fullmatch(
            r"condemn (?:prepare|(?:start|resume) operation-[0-9a-f]{32})", self.command
        ) is None:
            _fail("invalid Condemn job command")
        if self.destination is not None and not isinstance(
            self.destination, WorkerTravelDestination
        ):
            _fail("destination must be WorkerTravelDestination or null")
        if self.kind is not WorkerOperationKind.TRAVEL and self.destination is not None:
            _fail("only travel operations may carry a destination")
        issued = _finite_time(self.issued_at, "issued_at")
        expires = _finite_time(self.expires_at, "expires_at")
        if expires <= issued:
            _fail("expires_at must be later than issued_at")

    @property
    def priority(self) -> int:
        if self.kind is WorkerOperationKind.STOP:
            return 200
        return 100 if self.kind is WorkerOperationKind.CANCEL else 0

    def target_identity(self) -> tuple[object, ...]:
        return (
            self.node_id,
            self.client_id,
            self.instance_id,
            self.worker_id,
            self.worker_process_id,
            self.worker_process_started_at_100ns,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "client_id": self.client_id,
            "instance_id": self.instance_id,
            "worker_id": self.worker_id,
            "worker_process_id": self.worker_process_id,
            "worker_process_started_at_100ns": self.worker_process_started_at_100ns,
            "operation_id": self.operation_id,
            "deduplication_id": self.deduplication_id,
            "kind": self.kind.value,
            "command": self.command,
            "destination": None if self.destination is None else self.destination.to_dict(),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True, slots=True)
class WorkerOperationReceipt:
    node_id: str
    client_id: str
    instance_id: str
    worker_id: str
    worker_process_id: int
    worker_process_started_at_100ns: int
    operation_id: str
    deduplication_id: str
    kind: WorkerOperationKind
    state: WorkerOperationState
    observed_at: float
    detail: str | None = None
    schema_version: int = field(default=WORKER_OPERATION_RECEIPT_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _identifier(self.node_id, "node_id")
        _identifier(self.client_id, "client_id")
        _identifier(self.instance_id, "instance_id")
        _pattern(self.worker_id, "worker_id", _WORKER_ID)
        _positive_integer(self.worker_process_id, "worker_process_id")
        _positive_integer(
            self.worker_process_started_at_100ns,
            "worker_process_started_at_100ns",
        )
        _pattern(self.operation_id, "operation_id", _OPERATION_ID)
        _pattern(self.deduplication_id, "deduplication_id", _DEDUPLICATION_ID)
        if not isinstance(self.kind, WorkerOperationKind):
            _fail("kind must be WorkerOperationKind")
        if not isinstance(self.state, WorkerOperationState):
            _fail("state must be WorkerOperationState")
        _finite_time(self.observed_at, "observed_at")
        _detail(self.detail)

    @classmethod
    def for_operation(
        cls,
        operation: WorkerOperation,
        state: WorkerOperationState,
        *,
        observed_at: float,
        detail: str | None = None,
    ) -> WorkerOperationReceipt:
        return cls(
            node_id=operation.node_id,
            client_id=operation.client_id,
            instance_id=operation.instance_id,
            worker_id=operation.worker_id,
            worker_process_id=operation.worker_process_id,
            worker_process_started_at_100ns=operation.worker_process_started_at_100ns,
            operation_id=operation.operation_id,
            deduplication_id=operation.deduplication_id,
            kind=operation.kind,
            state=state,
            observed_at=observed_at,
            detail=detail,
        )

    def operation_identity(self) -> tuple[object, ...]:
        return (
            self.node_id,
            self.client_id,
            self.instance_id,
            self.worker_id,
            self.worker_process_id,
            self.worker_process_started_at_100ns,
            self.operation_id,
            self.deduplication_id,
            self.kind,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "client_id": self.client_id,
            "instance_id": self.instance_id,
            "worker_id": self.worker_id,
            "worker_process_id": self.worker_process_id,
            "worker_process_started_at_100ns": self.worker_process_started_at_100ns,
            "operation_id": self.operation_id,
            "deduplication_id": self.deduplication_id,
            "kind": self.kind.value,
            "state": self.state.value,
            "observed_at": self.observed_at,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class WorkerOperationSubmission:
    operation: WorkerOperation
    duplicate: bool


@dataclass(frozen=True, slots=True)
class WorkerOperationExecution:
    """Terminal outcome returned by an exact worker's operation executor."""

    state: WorkerOperationState
    detail: str | None = None
    native_cleanup_confirmed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.state, WorkerOperationState) or not self.state.terminal:
            raise ValueError("execution state must be terminal")
        if self.state in {
            WorkerOperationState.EXPIRED,
            WorkerOperationState.REJECTED,
        }:
            raise ValueError("executor may return only succeeded, failed, or cancelled")
        _detail(self.detail)
        if type(self.native_cleanup_confirmed) is not bool:
            raise ValueError("native cleanup proof must be boolean")


@dataclass(frozen=True, slots=True)
class WorkerOperationSnapshot:
    operation: WorkerOperation
    receipt: WorkerOperationReceipt | None

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation.to_dict(),
            "receipt": None if self.receipt is None else self.receipt.to_dict(),
        }


def new_worker_operation(
    permit: WorkerDispatchPermit,
    kind: WorkerOperationKind,
    command: str,
    *,
    destination: WorkerTravelDestination | None = None,
    now: float | None = None,
    ttl_seconds: float = DEFAULT_WORKER_OPERATION_TTL_SECONDS,
    operation_id: str | None = None,
    deduplication_id: str | None = None,
) -> WorkerOperation:
    """Create one exact operation from a current manager-issued dispatch permit."""

    if not isinstance(permit, WorkerDispatchPermit) or not permit.allowed:
        raise WorkerOperationFormatError("an allowed exact dispatch permit is required")
    if any(
        value is None
        for value in (
            permit.instance_id,
            permit.worker_id,
            permit.process_id,
            permit.process_started_at_100ns,
        )
    ):
        raise WorkerOperationFormatError("dispatch permit lacks exact worker identity")
    issued_at = time.time() if now is None else _finite_time(now, "now")
    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, (int, float))
        or not isfinite(ttl_seconds)
        or ttl_seconds <= 0
    ):
        raise WorkerOperationFormatError("ttl_seconds must be finite and positive")
    resolved_operation_id = operation_id or f"operation-{uuid.uuid4().hex}"
    if deduplication_id is None:
        canonical = json.dumps(
            {
                "node_id": permit.node_id,
                "client_id": permit.client_id,
                "instance_id": permit.instance_id,
                "worker_id": permit.worker_id,
                "operation_id": resolved_operation_id,
                "kind": kind.value,
                "command": command,
                "destination": None if destination is None else destination.to_dict(),
            },
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        deduplication_id = f"dedup-{hashlib.sha256(canonical).hexdigest()}"
    return WorkerOperation(
        node_id=permit.node_id,
        client_id=permit.client_id,
        instance_id=permit.instance_id,
        worker_id=permit.worker_id,
        worker_process_id=permit.process_id,
        worker_process_started_at_100ns=permit.process_started_at_100ns,
        operation_id=resolved_operation_id,
        deduplication_id=deduplication_id,
        kind=kind,
        command=command,
        destination=destination,
        issued_at=issued_at,
        expires_at=issued_at + float(ttl_seconds),
    )


def parse_worker_operation(value: object) -> WorkerOperation:
    payload = _exact_mapping(value, _OPERATION_FIELDS, "worker operation")
    if payload["schema_version"] != WORKER_OPERATION_SCHEMA_VERSION:
        _fail(f"operation schema_version must be {WORKER_OPERATION_SCHEMA_VERSION}")
    try:
        kind = WorkerOperationKind(payload["kind"])
    except (TypeError, ValueError) as exc:
        raise WorkerOperationFormatError("operation kind is unsupported") from exc
    destination_value = payload["destination"]
    destination = None
    if destination_value is not None:
        destination_payload = _exact_mapping(
            destination_value,
            frozenset({"lt", "lg", "radius"}),
            "travel destination",
        )
        destination = WorkerTravelDestination(
            lt=_finite_time(destination_payload["lt"], "destination.lt"),
            lg=_finite_time(destination_payload["lg"], "destination.lg"),
            radius=(
                None
                if destination_payload["radius"] is None
                else _finite_time(destination_payload["radius"], "destination.radius")
            ),
        )
    return WorkerOperation(
        node_id=_identifier(payload["node_id"], "node_id"),
        client_id=_identifier(payload["client_id"], "client_id"),
        instance_id=_identifier(payload["instance_id"], "instance_id"),
        worker_id=_pattern(payload["worker_id"], "worker_id", _WORKER_ID),
        worker_process_id=_positive_integer(payload["worker_process_id"], "worker_process_id"),
        worker_process_started_at_100ns=_positive_integer(
            payload["worker_process_started_at_100ns"],
            "worker_process_started_at_100ns",
        ),
        operation_id=_pattern(payload["operation_id"], "operation_id", _OPERATION_ID),
        deduplication_id=_pattern(
            payload["deduplication_id"], "deduplication_id", _DEDUPLICATION_ID
        ),
        kind=kind,
        command=_command(payload["command"]),
        destination=destination,
        issued_at=_finite_time(payload["issued_at"], "issued_at"),
        expires_at=_finite_time(payload["expires_at"], "expires_at"),
    )


def parse_worker_operation_receipt(value: object) -> WorkerOperationReceipt:
    payload = _exact_mapping(value, _RECEIPT_FIELDS, "worker operation receipt")
    if payload["schema_version"] != WORKER_OPERATION_RECEIPT_SCHEMA_VERSION:
        _fail(f"receipt schema_version must be {WORKER_OPERATION_RECEIPT_SCHEMA_VERSION}")
    try:
        kind = WorkerOperationKind(payload["kind"])
        state = WorkerOperationState(payload["state"])
    except (TypeError, ValueError) as exc:
        raise WorkerOperationFormatError("receipt kind or state is unsupported") from exc
    return WorkerOperationReceipt(
        node_id=_identifier(payload["node_id"], "node_id"),
        client_id=_identifier(payload["client_id"], "client_id"),
        instance_id=_identifier(payload["instance_id"], "instance_id"),
        worker_id=_pattern(payload["worker_id"], "worker_id", _WORKER_ID),
        worker_process_id=_positive_integer(payload["worker_process_id"], "worker_process_id"),
        worker_process_started_at_100ns=_positive_integer(
            payload["worker_process_started_at_100ns"],
            "worker_process_started_at_100ns",
        ),
        operation_id=_pattern(payload["operation_id"], "operation_id", _OPERATION_ID),
        deduplication_id=_pattern(
            payload["deduplication_id"], "deduplication_id", _DEDUPLICATION_ID
        ),
        kind=kind,
        state=state,
        observed_at=_finite_time(payload["observed_at"], "observed_at"),
        detail=_detail(payload["detail"]),
    )


def _loads(source: str, parser: Callable[[object], object], description: str) -> object:
    if not isinstance(source, str):
        raise WorkerOperationFormatError(f"{description} JSON source must be text")

    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise WorkerOperationFormatError(
                    f"{description} JSON contains duplicate field {key!r}"
                )
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise WorkerOperationFormatError(f"{description} JSON contains non-finite number {value}")

    try:
        decoded = json.loads(
            source,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except WorkerOperationFormatError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise WorkerOperationFormatError(f"{description} is not valid JSON: {exc}") from exc
    return parser(decoded)


def loads_worker_operation(source: str) -> WorkerOperation:
    return _loads(source, parse_worker_operation, "worker operation")  # type: ignore[return-value]


def loads_worker_operation_receipt(source: str) -> WorkerOperationReceipt:
    return _loads(  # type: ignore[return-value]
        source,
        parse_worker_operation_receipt,
        "worker operation receipt",
    )


class WorkerOperationLedger:
    """Bounded transactional inbox and status store shared by ingress and workers."""

    def __init__(
        self,
        manifest: ManagerManifest,
        root: str | Path,
        *,
        max_record_bytes: int = DEFAULT_MAX_WORKER_OPERATION_BYTES,
        max_records_per_slot: int = DEFAULT_MAX_WORKER_OPERATIONS_PER_SLOT,
        terminal_retention_seconds: float = (DEFAULT_WORKER_OPERATION_TERMINAL_RETENTION_SECONDS),
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        requested = Path(root)
        if os.name == "nt" and str(requested).startswith("\\\\"):
            raise ValueError("worker operation root must be node-local, not a UNC share")
        if (
            isinstance(max_record_bytes, bool)
            or not isinstance(max_record_bytes, int)
            or max_record_bytes < 1_024
        ):
            raise ValueError("max_record_bytes must be an integer of at least 1024")
        if (
            isinstance(max_records_per_slot, bool)
            or not isinstance(max_records_per_slot, int)
            or max_records_per_slot <= 0
        ):
            raise ValueError("max_records_per_slot must be a positive integer")
        retention = _finite_time(
            terminal_retention_seconds,
            "terminal_retention_seconds",
        )
        if retention <= 0:
            raise ValueError("terminal_retention_seconds must be positive")
        if not callable(clock):
            raise ValueError("clock must be callable")
        self._manifest = manifest
        self._root = requested.resolve(strict=False)
        self._max_bytes = max_record_bytes
        self._max_records = max_records_per_slot
        self._terminal_retention_seconds = retention
        self._clock = clock
        self._client_ids = {
            config.client_id.casefold(): config.client_id for config in manifest.clients
        }

    @property
    def root(self) -> Path:
        return self._root

    def _client_id(self, value: str) -> str:
        _identifier(value, "client_id")
        canonical = self._client_ids.get(value.casefold())
        if canonical is None:
            raise WorkerOperationLedgerError(f"unknown manifest client_id {value!r}")
        return canonical

    def _directory(self, client_id: str) -> Path:
        canonical = self._client_id(client_id)
        directory = self._root / self._manifest.node_id / canonical / "operations"
        if not directory.resolve(strict=False).is_relative_to(self._root):
            raise WorkerOperationLedgerError("worker operation path escaped its state root")
        return directory

    @contextmanager
    def _transaction(self, directory: Path) -> Iterator[None]:
        try:
            with exclusive_record_lock(directory / ".ledger.lock"):
                yield
        except (OSError, TimeoutError) as exc:
            raise WorkerOperationLedgerError(
                f"could not lock worker operation ledger: {exc}"
            ) from exc

    def _read(
        self, path: Path, parser: Callable[[str], object], *, max_bytes: int | None = None
    ) -> object:
        limit = self._max_bytes if max_bytes is None else max_bytes
        try:
            if path.is_symlink() or not path.is_file():
                raise WorkerOperationFormatError("operation record must be a regular file")
            source = read_record_bytes(path, limit)
        except OSError as exc:
            raise WorkerOperationLedgerError(f"could not read operation record: {exc}") from exc
        if len(source) > limit:
            raise WorkerOperationFormatError("operation record exceeds size limit")
        try:
            text = source.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise WorkerOperationFormatError("operation record must be UTF-8") from exc
        return parser(text)

    def _encode(self, value: Mapping[str, object], *, max_bytes: int | None = None) -> bytes:
        limit = self._max_bytes if max_bytes is None else max_bytes
        payload = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(payload) > limit:
            raise WorkerOperationLedgerError("serialized operation record exceeds size limit")
        return payload

    def publish_pve_progress(self, record) -> None:
        """Replace one exact-operation progress record; never grant dispatch authority."""
        from .pve_status import WorkerPvEProgress
        if not isinstance(record, WorkerPvEProgress):
            raise ValueError("progress record must be typed")
        operation = record.operation
        directory = self._directory(operation.client_id)
        with self._transaction(directory):
            stored = self._read(
                directory / f"{operation.operation_id}.json", loads_worker_operation)
            receipt = self._inspect_receipt_unlocked(directory, operation.operation_id)
            if (stored != operation or receipt is None or receipt.state.terminal
                    or receipt.state not in {
                        WorkerOperationState.ACCEPTED, WorkerOperationState.ACTIVE}):
                raise WorkerOperationLedgerError(
                    "progress does not own an active immutable operation")
            acknowledged = tuple(s for s in self._inspect_slot_unlocked(directory)
                                 if s.receipt is not None)
            # Match manager selection ordering across worker replacement, including
            # newer terminal stop/travel operations. An abandoned ACTIVE receipt
            # never permits an older writer to replace the current slot snapshot.
            if not acknowledged or acknowledged[-1].operation != operation:
                raise WorkerOperationLedgerError("progress writer was superseded")
            target = directory / "pve-progress.json"
            if target.is_symlink():
                raise WorkerOperationLedgerError("progress must not be a symlink")
            publish_atomic_record(target, self._encode(record.to_dict(), max_bytes=65_536),
                                  temporary_label="pve-progress")

    def inspect_pve_progress(self, client_id: str):
        from .pve_status import WorkerPvEProgress
        directory = self._directory(client_id)
        with self._transaction(directory):
            path = directory / "pve-progress.json"
            if not path.exists():
                return None
            record = self._read(
                path, lambda raw: _loads(raw, WorkerPvEProgress.parse, "PvE progress"),
                max_bytes=65_536)
            if (record.operation.node_id != self._manifest.node_id
                    or record.operation.client_id != self._client_id(client_id)):
                raise WorkerOperationLedgerError("progress record belongs to another slot")
            return record

    def publish_preparation_status(self, record):
        from .preparation_status import WorkerPreparationStatus
        if not isinstance(record, WorkerPreparationStatus):
            raise ValueError("preparation status must be typed")
        heartbeat = record.heartbeat
        if heartbeat.node_id != self._manifest.node_id:
            raise WorkerOperationLedgerError("preparation status belongs to another node")
        directory = self._directory(heartbeat.client_id)
        with self._transaction(directory):
            target = directory / "preparation-status.json"
            if target.exists():
                prior = self._read(target, lambda raw: _loads(
                    raw, WorkerPreparationStatus.parse, "preparation status"))
                old = prior.heartbeat
                if (old.process_started_at_100ns > heartbeat.process_started_at_100ns
                        or (old.worker_id == heartbeat.worker_id
                            and old.sequence >= heartbeat.sequence)):
                    raise WorkerOperationLedgerError("preparation reporter was superseded")
            publish_atomic_record(target, self._encode(record.to_dict()),
                                  temporary_label="preparation-status")

    def inspect_preparation_status(self, client_id):
        from .preparation_status import WorkerPreparationStatus
        directory = self._directory(client_id)
        with self._transaction(directory):
            target = directory / "preparation-status.json"
            if not target.exists():
                return None
            record = self._read(target, lambda raw: _loads(
                raw, WorkerPreparationStatus.parse, "preparation status"))
            if (record.heartbeat.node_id != self._manifest.node_id
                    or record.heartbeat.client_id != self._client_id(client_id)):
                raise WorkerOperationLedgerError("preparation status belongs to another slot")
            return record

    def _operation_paths(self, directory: Path) -> list[Path]:
        try:
            return sorted(directory.glob("operation-*.json"))
        except OSError as exc:
            raise WorkerOperationLedgerError(f"could not inspect operation inbox: {exc}") from exc

    def _inspect_receipt_unlocked(
        self,
        directory: Path,
        operation_id: str,
    ) -> WorkerOperationReceipt | None:
        target = directory / f"{operation_id}.receipt"
        try:
            if not target.exists():
                return None
        except OSError as exc:
            raise WorkerOperationLedgerError(f"could not inspect receipt: {exc}") from exc
        receipt = self._read(target, loads_worker_operation_receipt)
        assert isinstance(receipt, WorkerOperationReceipt)
        return receipt

    def _publish_receipt_unlocked(
        self,
        directory: Path,
        receipt: WorkerOperationReceipt,
    ) -> Path:
        operation_path = directory / f"{receipt.operation_id}.json"
        operation = self._read(operation_path, loads_worker_operation)
        assert isinstance(operation, WorkerOperation)
        expected_identity = (
            *operation.target_identity(),
            operation.operation_id,
            operation.deduplication_id,
            operation.kind,
        )
        if receipt.operation_identity() != expected_identity:
            raise WorkerOperationLedgerError("receipt does not own its immutable operation")
        target = directory / f"{receipt.operation_id}.receipt"
        current = self._inspect_receipt_unlocked(directory, receipt.operation_id)
        if current is not None:
            if current.operation_identity() != receipt.operation_identity():
                raise WorkerOperationLedgerError("receipt identity changed")
            if receipt.observed_at < current.observed_at:
                raise WorkerOperationLedgerError("receipt time moved backwards")
            allowed = {
                WorkerOperationState.ACCEPTED: {
                    WorkerOperationState.ACCEPTED,
                    WorkerOperationState.ACTIVE,
                    WorkerOperationState.CANCELLED,
                    WorkerOperationState.EXPIRED,
                    WorkerOperationState.REJECTED,
                    WorkerOperationState.FAILED,
                },
                WorkerOperationState.ACTIVE: {
                    WorkerOperationState.ACTIVE,
                    WorkerOperationState.SUCCEEDED,
                    WorkerOperationState.CANCELLED,
                    WorkerOperationState.FAILED,
                },
            }
            if current.state.terminal and receipt != current:
                raise WorkerOperationLedgerError("terminal operation receipt is immutable")
            if not current.state.terminal and receipt.state not in allowed[current.state]:
                raise WorkerOperationLedgerError(
                    f"invalid operation transition {current.state.value} -> {receipt.state.value}"
                )
        payload = self._encode(receipt.to_dict())
        try:
            publish_atomic_record(
                target,
                payload,
                temporary_label=receipt.operation_id,
            )
        except OSError as exc:
            raise WorkerOperationLedgerError(f"could not persist receipt: {exc}") from exc
        return target

    def _inspect_slot_unlocked(
        self,
        directory: Path,
    ) -> tuple[WorkerOperationSnapshot, ...]:
        paths = self._operation_paths(directory)
        if len(paths) > self._max_records:
            raise WorkerOperationLedgerError("worker operation inbox exceeds its bounded limit")
        snapshots = []
        for path in paths:
            operation = self._read(path, loads_worker_operation)
            assert isinstance(operation, WorkerOperation)
            receipt = self._inspect_receipt_unlocked(directory, operation.operation_id)
            snapshots.append(WorkerOperationSnapshot(operation, receipt))
        return tuple(
            sorted(
                snapshots,
                key=lambda item: (item.operation.issued_at, item.operation.operation_id),
            )
        )

    def _prune_terminal_unlocked(self, directory: Path, observed_at: float) -> int:
        cutoff = observed_at - self._terminal_retention_seconds
        if cutoff < 0:
            return 0
        removed = 0
        for path in self._operation_paths(directory):
            operation = self._read(path, loads_worker_operation)
            assert isinstance(operation, WorkerOperation)
            receipt_path = directory / f"{operation.operation_id}.receipt"
            receipt = self._inspect_receipt_unlocked(directory, operation.operation_id)
            if receipt is None or not receipt.state.terminal or receipt.observed_at > cutoff:
                continue
            try:
                path.unlink()
                receipt_path.unlink(missing_ok=True)
            except OSError as exc:
                raise WorkerOperationLedgerError(
                    f"could not prune terminal operation: {exc}"
                ) from exc
            removed += 1
        try:
            orphan_receipts = sorted(directory.glob("operation-*.receipt"))
        except OSError as exc:
            raise WorkerOperationLedgerError(
                f"could not inspect orphan operation receipts: {exc}"
            ) from exc
        for receipt_path in orphan_receipts:
            operation_path = receipt_path.with_suffix(".json")
            if operation_path.exists():
                continue
            receipt = self._read(receipt_path, loads_worker_operation_receipt)
            assert isinstance(receipt, WorkerOperationReceipt)
            if not receipt.state.terminal or receipt.observed_at > cutoff:
                continue
            try:
                receipt_path.unlink()
            except OSError as exc:
                raise WorkerOperationLedgerError(
                    f"could not prune orphan operation receipt: {exc}"
                ) from exc
        return removed

    def submit(self, operation: WorkerOperation) -> WorkerOperationSubmission:
        if not isinstance(operation, WorkerOperation):
            raise ValueError("operation must be WorkerOperation")
        canonical = self._client_id(operation.client_id)
        if operation.node_id != self._manifest.node_id or operation.client_id != canonical:
            raise WorkerOperationLedgerError("operation identity does not match the manifest")
        directory = self._directory(canonical)
        with self._transaction(directory):
            existing_paths = self._operation_paths(directory)
            for path in existing_paths:
                existing = self._read(path, loads_worker_operation)
                assert isinstance(existing, WorkerOperation)
                if existing.deduplication_id != operation.deduplication_id:
                    continue
                # A transport retry may regenerate its envelope ID/timestamps.
                # Compare exact target and requested work, then retain the first
                # envelope, deadline and receipt; a retry cannot extend or replay it.
                retry = replace(
                    operation,
                    operation_id=existing.operation_id,
                    issued_at=existing.issued_at,
                    expires_at=existing.expires_at,
                )
                if existing != retry:
                    raise WorkerOperationLedgerError(
                        "deduplication_id is already owned by a different immutable operation"
                    )
                return WorkerOperationSubmission(existing, duplicate=True)
            observed_at = _finite_time(self._clock(), "clock result")
            self._prune_terminal_unlocked(directory, observed_at)
            if len(self._operation_paths(directory)) >= self._max_records:
                raise WorkerOperationLedgerError("worker operation inbox reached its bounded limit")
            target = directory / f"{operation.operation_id}.json"
            payload = self._encode(operation.to_dict())
            try:
                with target.open("xb") as destination:
                    destination.write(payload)
                    destination.flush()
                    os.fsync(destination.fileno())
            except FileExistsError as exc:
                existing = self._read(target, loads_worker_operation)
                if existing != operation:
                    raise WorkerOperationLedgerError(
                        "operation_id is already owned by different immutable content"
                    ) from exc
                return WorkerOperationSubmission(operation, duplicate=True)
            except OSError as exc:
                raise WorkerOperationLedgerError(f"could not persist operation: {exc}") from exc
            return WorkerOperationSubmission(operation, duplicate=False)

    def inspect_receipt(
        self,
        client_id: str,
        operation_id: str,
    ) -> WorkerOperationReceipt | None:
        _pattern(operation_id, "operation_id", _OPERATION_ID)
        directory = self._directory(client_id)
        with self._transaction(directory):
            return self._inspect_receipt_unlocked(directory, operation_id)

    def publish_receipt(self, receipt: WorkerOperationReceipt) -> Path:
        if not isinstance(receipt, WorkerOperationReceipt):
            raise ValueError("receipt must be WorkerOperationReceipt")
        canonical = self._client_id(receipt.client_id)
        if receipt.node_id != self._manifest.node_id or receipt.client_id != canonical:
            raise WorkerOperationLedgerError("receipt identity does not match the manifest")
        directory = self._directory(canonical)
        with self._transaction(directory):
            return self._publish_receipt_unlocked(directory, receipt)

    def inspect_slot(self, client_id: str) -> tuple[WorkerOperationSnapshot, ...]:
        directory = self._directory(client_id)
        with self._transaction(directory):
            return self._inspect_slot_unlocked(directory)

    def _preparation_control_path(self, directory, instance_id):
        _identifier(instance_id, "instance_id")
        key = hashlib.sha256(instance_id.encode("utf-8")).hexdigest()
        return directory / f"preparation-control-{key}.json"

    def _preparation_control_unlocked(self, directory, instance_id):
        from .preparation_control import PreparationControl
        path = self._preparation_control_path(directory, instance_id)
        if not path.exists():
            return None
        record = self._read(path, PreparationControl.loads)
        if (record.node_id != self._manifest.node_id
                or record.client_id != directory.parent.name or record.instance_id != instance_id):
            raise WorkerOperationLedgerError("preparation control belongs to another slot")
        return record

    def inspect_preparation_control(self, client_id, instance_id):
        directory = self._directory(client_id)
        with self._transaction(directory):
            return self._preparation_control_unlocked(directory, instance_id)

    def set_preparation_enabled(
        self, client_id, *, instance_id, worker_id, worker_process_id,
        worker_process_creation, enabled, expected_revision,
    ):
        """Publish explicit manager intent after the caller verifies current attachment.

        Resume and operation submission share this transaction. Exact STOP IDs
        already retained at Resume cannot later reapply an older user request.
        No clock ordering or fresh dispatch authority is inferred from this record.
        """
        from .preparation_control import PreparationControl
        directory = self._directory(client_id)
        with self._transaction(directory):
            current = self._preparation_control_unlocked(directory, instance_id)
            revision = 0 if current is None else current.revision
            if type(expected_revision) is not int or expected_revision != revision:
                raise WorkerOperationLedgerError("preparation control changed; refresh and retry")
            superseded = tuple(
                item.operation.operation_id for item in self._inspect_slot_unlocked(directory)
                if item.operation.instance_id == instance_id and item.operation.kind in {
                    WorkerOperationKind.STOP, WorkerOperationKind.CANCEL}
            ) if enabled else (() if current is None else current.superseded_stops)
            record = PreparationControl(
                self._manifest.node_id, self._client_id(client_id), instance_id,
                revision + 1, enabled, worker_id, worker_process_id,
                worker_process_creation, superseded,
            )
            self._publish_preparation_control(directory, record)
            return record

    def latch_preparation_stop(self, operation):
        """Latch an exact retained STOP/CANCEL unless a later Resume superseded it."""
        from .preparation_control import PreparationControl
        if not isinstance(operation, WorkerOperation) or operation.kind not in {
                WorkerOperationKind.STOP, WorkerOperationKind.CANCEL}:
            raise WorkerOperationLedgerError("preparation stop requires an exact stop operation")
        directory = self._directory(operation.client_id)
        with self._transaction(directory):
            stored = self._read(
                directory / f"{operation.operation_id}.json", loads_worker_operation)
            if stored != operation or operation.node_id != self._manifest.node_id:
                raise WorkerOperationLedgerError("preparation stop does not own its operation")
            current = self._preparation_control_unlocked(directory, operation.instance_id)
            if (current is not None and current.instance_id == operation.instance_id
                    and operation.operation_id in current.superseded_stops):
                return current
            if current is not None and not current.enabled:
                return current
            record = PreparationControl(
                operation.node_id, operation.client_id, operation.instance_id,
                1 if current is None else current.revision + 1, False,
                operation.worker_id, operation.worker_process_id,
                operation.worker_process_started_at_100ns,
                () if current is None else current.superseded_stops,
            )
            self._publish_preparation_control(directory, record)
            return record

    def _publish_preparation_control(self, directory, record):
        target = self._preparation_control_path(directory, record.instance_id)
        if target.is_symlink():
            raise WorkerOperationLedgerError("preparation control must not be a symlink")
        publish_atomic_record(target, self._encode(record.to_dict()),
                              temporary_label="preparation-control")

    def prune_terminal(self, client_id: str, *, now: float) -> int:
        """Remove terminal operation pairs older than the configured retention."""

        directory = self._directory(client_id)
        observed_at = _finite_time(now, "now")
        with self._transaction(directory):
            return self._prune_terminal_unlocked(directory, observed_at)

    def claim_for_execution(self, operation: WorkerOperation, *, now: float) -> bool:
        """Atomically activate one immutable operation, once across worker contenders.

        A crashed ACTIVE claimant is never replayed implicitly: its exact worker
        lifetime and receipt remain evidence for explicit interruption/recovery.
        """
        if not isinstance(operation, WorkerOperation):
            raise ValueError("operation must be WorkerOperation")
        observed_at = _finite_time(now, "now")
        directory = self._directory(operation.client_id)
        with self._transaction(directory):
            stored = self._read(
                directory / f"{operation.operation_id}.json", loads_worker_operation
            )
            if stored != operation:
                raise WorkerOperationLedgerError("claim does not own its immutable operation")
            current = self._inspect_receipt_unlocked(directory, operation.operation_id)
            if current is not None and (
                current.state is WorkerOperationState.ACTIVE or current.state.terminal
            ):
                return False
            if operation.expires_at <= observed_at:
                self._publish_receipt_unlocked(
                    directory,
                    WorkerOperationReceipt.for_operation(
                        operation,
                        WorkerOperationState.EXPIRED,
                        observed_at=observed_at,
                        detail="operation expired before worker activation",
                    ),
                )
                return False
            if current is None:
                self._publish_receipt_unlocked(
                    directory,
                    WorkerOperationReceipt.for_operation(
                        operation,
                        WorkerOperationState.ACCEPTED,
                        observed_at=observed_at,
                        detail="accepted by exact per-client worker",
                    ),
                )
            self._publish_receipt_unlocked(
                directory,
                WorkerOperationReceipt.for_operation(
                    operation,
                    WorkerOperationState.ACTIVE,
                    observed_at=observed_at,
                    detail="executing through the exact worker dispatch gate",
                ),
            )
            return True

    def pending_for(
        self,
        *,
        client_id: str,
        instance_id: str,
        worker_id: str,
        worker_process_id: int,
        worker_process_started_at_100ns: int,
        now: float,
    ) -> tuple[WorkerOperation, ...]:
        canonical = self._client_id(client_id)
        target = (
            self._manifest.node_id,
            canonical,
            _identifier(instance_id, "instance_id"),
            _pattern(worker_id, "worker_id", _WORKER_ID),
            _positive_integer(worker_process_id, "worker_process_id"),
            _positive_integer(
                worker_process_started_at_100ns,
                "worker_process_started_at_100ns",
            ),
        )
        observed_at = _finite_time(now, "now")
        directory = self._directory(canonical)
        pending = []
        with self._transaction(directory):
            for snapshot in self._inspect_slot_unlocked(directory):
                operation = snapshot.operation
                if operation.target_identity() != target:
                    continue
                receipt = snapshot.receipt
                if receipt is not None and (
                    receipt.state is WorkerOperationState.ACTIVE or receipt.state.terminal
                ):
                    continue
                if operation.expires_at <= observed_at:
                    self._publish_receipt_unlocked(
                        directory,
                        WorkerOperationReceipt.for_operation(
                            operation,
                            WorkerOperationState.EXPIRED,
                            observed_at=observed_at,
                            detail="operation expired before worker activation",
                        ),
                    )
                    continue
                pending.append(operation)
        return tuple(
            sorted(
                pending,
                key=lambda item: (-item.priority, item.issued_at, item.operation_id),
            )
        )

    def wait_for_acknowledgement(
        self,
        operation: WorkerOperation,
        *,
        timeout_seconds: float = DEFAULT_WORKER_OPERATION_ACK_TIMEOUT_SECONDS,
        poll_seconds: float = 0.05,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> WorkerOperationReceipt | None:
        if not isinstance(operation, WorkerOperation):
            raise ValueError("operation must be WorkerOperation")
        if timeout_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("acknowledgement timeout and poll interval must be positive")
        deadline = clock() + timeout_seconds
        while True:
            receipt = self.inspect_receipt(operation.client_id, operation.operation_id)
            if receipt is not None:
                return receipt
            remaining = deadline - clock()
            if remaining <= 0:
                return None
            sleeper(min(poll_seconds, remaining))


__all__ = [
    "DEFAULT_WORKER_OPERATION_ACK_TIMEOUT_SECONDS",
    "DEFAULT_WORKER_OPERATION_TERMINAL_RETENTION_SECONDS",
    "DEFAULT_WORKER_OPERATION_TTL_SECONDS",
    "WORKER_OPERATION_RECEIPT_SCHEMA_VERSION",
    "WORKER_OPERATION_SCHEMA_VERSION",
    "WorkerOperation",
    "WorkerOperationError",
    "WorkerOperationExecution",
    "WorkerOperationFormatError",
    "WorkerOperationKind",
    "WorkerOperationLedger",
    "WorkerOperationLedgerError",
    "WorkerOperationReceipt",
    "WorkerOperationSnapshot",
    "WorkerOperationState",
    "WorkerOperationSubmission",
    "WorkerTravelDestination",
    "loads_worker_operation",
    "loads_worker_operation_receipt",
    "new_worker_operation",
    "parse_worker_operation",
    "parse_worker_operation_receipt",
]
