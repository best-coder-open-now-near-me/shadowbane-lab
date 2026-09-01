"""Immutable node-local operation channel for exact per-client workers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import NoReturn

from .manifest import ManagerManifest
from .worker import WorkerDispatchPermit

WORKER_OPERATION_SCHEMA_VERSION = 1
WORKER_OPERATION_RECEIPT_SCHEMA_VERSION = 1
DEFAULT_WORKER_OPERATION_TTL_SECONDS = 8.0
DEFAULT_WORKER_OPERATION_ACK_TIMEOUT_SECONDS = 2.0
DEFAULT_MAX_WORKER_OPERATION_BYTES = 16_384
DEFAULT_MAX_WORKER_OPERATIONS_PER_SLOT = 256

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

    def __post_init__(self) -> None:
        if not isinstance(self.state, WorkerOperationState) or not self.state.terminal:
            raise ValueError("execution state must be terminal")
        if self.state in {
            WorkerOperationState.EXPIRED,
            WorkerOperationState.REJECTED,
        }:
            raise ValueError("executor may return only succeeded, failed, or cancelled")
        _detail(self.detail)


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
    """Bounded atomic inbox and status store shared by ingress and exact workers."""

    def __init__(
        self,
        manifest: ManagerManifest,
        root: str | Path,
        *,
        max_record_bytes: int = DEFAULT_MAX_WORKER_OPERATION_BYTES,
        max_records_per_slot: int = DEFAULT_MAX_WORKER_OPERATIONS_PER_SLOT,
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
        self._manifest = manifest
        self._root = requested.resolve(strict=False)
        self._max_bytes = max_record_bytes
        self._max_records = max_records_per_slot
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

    def _read(self, path: Path, parser: Callable[[str], object]) -> object:
        try:
            if path.is_symlink() or not path.is_file():
                raise WorkerOperationFormatError("operation record must be a regular file")
            source = path.read_bytes()
        except OSError as exc:
            raise WorkerOperationLedgerError(f"could not read operation record: {exc}") from exc
        if len(source) > self._max_bytes:
            raise WorkerOperationFormatError("operation record exceeds size limit")
        try:
            text = source.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise WorkerOperationFormatError("operation record must be UTF-8") from exc
        return parser(text)

    def _encode(self, value: Mapping[str, object]) -> bytes:
        payload = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(payload) > self._max_bytes:
            raise WorkerOperationLedgerError("serialized operation record exceeds size limit")
        return payload

    def submit(self, operation: WorkerOperation) -> WorkerOperationSubmission:
        if not isinstance(operation, WorkerOperation):
            raise ValueError("operation must be WorkerOperation")
        canonical = self._client_id(operation.client_id)
        if operation.node_id != self._manifest.node_id or operation.client_id != canonical:
            raise WorkerOperationLedgerError("operation identity does not match the manifest")
        directory = self._directory(canonical)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            existing_paths = sorted(directory.glob("operation-*.json"))
        except OSError as exc:
            raise WorkerOperationLedgerError(f"could not inspect operation inbox: {exc}") from exc
        if len(existing_paths) >= self._max_records:
            raise WorkerOperationLedgerError("worker operation inbox reached its bounded limit")
        for path in existing_paths:
            existing = self._read(path, loads_worker_operation)
            assert isinstance(existing, WorkerOperation)
            if existing.deduplication_id != operation.deduplication_id:
                continue
            if existing != operation:
                raise WorkerOperationLedgerError(
                    "deduplication_id is already owned by a different immutable operation"
                )
            return WorkerOperationSubmission(existing, duplicate=True)
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
        target = self._directory(client_id) / f"{operation_id}.receipt"
        try:
            if not target.exists():
                return None
        except OSError as exc:
            raise WorkerOperationLedgerError(f"could not inspect receipt: {exc}") from exc
        receipt = self._read(target, loads_worker_operation_receipt)
        assert isinstance(receipt, WorkerOperationReceipt)
        return receipt

    def publish_receipt(self, receipt: WorkerOperationReceipt) -> Path:
        if not isinstance(receipt, WorkerOperationReceipt):
            raise ValueError("receipt must be WorkerOperationReceipt")
        canonical = self._client_id(receipt.client_id)
        if receipt.node_id != self._manifest.node_id or receipt.client_id != canonical:
            raise WorkerOperationLedgerError("receipt identity does not match the manifest")
        directory = self._directory(canonical)
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
        current = self.inspect_receipt(canonical, receipt.operation_id)
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
        temporary = directory / f".{receipt.operation_id}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
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
            raise WorkerOperationLedgerError(f"could not persist receipt: {exc}") from exc
        return target

    def inspect_slot(self, client_id: str) -> tuple[WorkerOperationSnapshot, ...]:
        directory = self._directory(client_id)
        try:
            if not directory.exists():
                return ()
            paths = sorted(directory.glob("operation-*.json"))
        except OSError as exc:
            raise WorkerOperationLedgerError(f"could not inspect operation inbox: {exc}") from exc
        if len(paths) > self._max_records:
            raise WorkerOperationLedgerError("worker operation inbox exceeds its bounded limit")
        snapshots = []
        for path in paths:
            operation = self._read(path, loads_worker_operation)
            assert isinstance(operation, WorkerOperation)
            receipt = self.inspect_receipt(operation.client_id, operation.operation_id)
            snapshots.append(WorkerOperationSnapshot(operation, receipt))
        return tuple(
            sorted(
                snapshots,
                key=lambda item: (item.operation.issued_at, item.operation.operation_id),
            )
        )

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
        target = (
            self._manifest.node_id,
            self._client_id(client_id),
            _identifier(instance_id, "instance_id"),
            _pattern(worker_id, "worker_id", _WORKER_ID),
            _positive_integer(worker_process_id, "worker_process_id"),
            _positive_integer(
                worker_process_started_at_100ns,
                "worker_process_started_at_100ns",
            ),
        )
        observed_at = _finite_time(now, "now")
        pending = []
        for snapshot in self.inspect_slot(client_id):
            operation = snapshot.operation
            if operation.target_identity() != target:
                continue
            receipt = snapshot.receipt
            if receipt is not None and (
                receipt.state is WorkerOperationState.ACTIVE or receipt.state.terminal
            ):
                continue
            if operation.expires_at <= observed_at and receipt is None:
                self.publish_receipt(
                    WorkerOperationReceipt.for_operation(
                        operation,
                        WorkerOperationState.EXPIRED,
                        observed_at=observed_at,
                        detail="operation expired before worker acknowledgement",
                    )
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
