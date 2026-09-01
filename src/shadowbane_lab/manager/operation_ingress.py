"""Foreground or captured-client ingress for immutable exact-worker operations."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .manifest import ManagerManifest
from .model import ClientInstanceSnapshot, ClientRegistrySnapshot
from .operation import (
    DEFAULT_WORKER_OPERATION_ACK_TIMEOUT_SECONDS,
    DEFAULT_WORKER_OPERATION_TTL_SECONDS,
    WorkerOperation,
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationReceipt,
    WorkerTravelDestination,
    new_worker_operation,
)
from .worker import WorkerDispatchPermit


class WorkerOperationIngressError(RuntimeError):
    """Raised when foreground ingress cannot safely identify an exact worker."""


class ClientRegistryProvider(Protocol):
    def inspect(self) -> ClientRegistrySnapshot: ...


class WorkerPermitProvider(Protocol):
    def inspect_permit(self, client_id: str) -> WorkerDispatchPermit | None: ...


@dataclass(frozen=True, slots=True)
class WorkerOperationDispatch:
    """One persisted operation and the worker's bounded acknowledgement."""

    client: ClientInstanceSnapshot
    operation: WorkerOperation
    acknowledgement: WorkerOperationReceipt | None
    duplicate: bool


class ForegroundWorkerOperationIngress:
    """Resolve a guarded foreground or exact captured lifetime to its worker permit."""

    def __init__(
        self,
        manifest: ManagerManifest,
        registry: ClientRegistryProvider,
        permits: WorkerPermitProvider,
        operations: WorkerOperationLedger,
        *,
        clock: Callable[[], float] = time.time,
        operation_ttl_seconds: float = DEFAULT_WORKER_OPERATION_TTL_SECONDS,
        acknowledgement_timeout_seconds: float = (DEFAULT_WORKER_OPERATION_ACK_TIMEOUT_SECONDS),
    ) -> None:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        if not callable(getattr(registry, "inspect", None)):
            raise ValueError("registry must provide inspect()")
        if not callable(getattr(permits, "inspect_permit", None)):
            raise ValueError("permits must provide inspect_permit()")
        if not isinstance(operations, WorkerOperationLedger):
            raise ValueError("operations must be WorkerOperationLedger")
        if not callable(clock):
            raise ValueError("clock must be callable")
        if operation_ttl_seconds <= 0 or acknowledgement_timeout_seconds <= 0:
            raise ValueError("operation and acknowledgement timeouts must be positive")
        self._manifest = manifest
        self._registry = registry
        self._permits = permits
        self._operations = operations
        self._clock = clock
        self._operation_ttl_seconds = float(operation_ttl_seconds)
        self._acknowledgement_timeout_seconds = float(acknowledgement_timeout_seconds)

    def dispatch(
        self,
        kind: WorkerOperationKind,
        command: str,
        *,
        destination: WorkerTravelDestination | None = None,
        expected_process_id: int | None = None,
        expected_window_handle: int | None = None,
        require_foreground: bool = True,
        operation_id: str | None = None,
        deduplication_id: str | None = None,
    ) -> WorkerOperationDispatch:
        now, client, permit = self._resolve_target(
            expected_process_id=expected_process_id,
            expected_window_handle=expected_window_handle,
            require_foreground=require_foreground,
        )
        return self._submit(
            client,
            new_worker_operation(
                permit,
                kind,
                command,
                destination=destination,
                now=now,
                ttl_seconds=self._operation_ttl_seconds,
                operation_id=operation_id,
                deduplication_id=deduplication_id,
            ),
        )

    def cancel_if_inflight(
        self,
        command: str,
        *,
        expected_process_id: int | None = None,
        expected_window_handle: int | None = None,
        require_foreground: bool = True,
        operation_id: str | None = None,
    ) -> WorkerOperationDispatch | None:
        """Cancel exact in-flight automation without issuing client input.

        Existing non-terminal cancellations are coalesced. Public ``/stop`` remains
        a separate physical movement-stop operation.
        """

        now, client, permit = self._resolve_target(
            expected_process_id=expected_process_id,
            expected_window_handle=expected_window_handle,
            require_foreground=require_foreground,
        )
        target_identity = (
            permit.node_id,
            permit.client_id,
            permit.instance_id,
            permit.worker_id,
            permit.process_id,
            permit.process_started_at_100ns,
        )
        has_inflight_automation = False
        for snapshot in self._operations.inspect_slot(permit.client_id):
            operation = snapshot.operation
            if operation.target_identity() != target_identity:
                continue
            receipt = snapshot.receipt
            if receipt is not None and receipt.state.terminal:
                continue
            if receipt is None and operation.expires_at <= now:
                continue
            if operation.kind is WorkerOperationKind.CANCEL:
                return None
            if operation.kind in {
                WorkerOperationKind.TRAVEL,
                WorkerOperationKind.PVE,
            }:
                has_inflight_automation = True
        if not has_inflight_automation:
            return None
        return self._submit(
            client,
            new_worker_operation(
                permit,
                WorkerOperationKind.CANCEL,
                command,
                now=now,
                ttl_seconds=self._operation_ttl_seconds,
                operation_id=operation_id,
            ),
        )

    def _resolve_target(
        self,
        *,
        expected_process_id: int | None,
        expected_window_handle: int | None,
        require_foreground: bool,
    ) -> tuple[float, ClientInstanceSnapshot, WorkerDispatchPermit]:
        if not isinstance(require_foreground, bool):
            raise ValueError("require_foreground must be a boolean")
        for value, field_name in (
            (expected_process_id, "expected_process_id"),
            (expected_window_handle, "expected_window_handle"),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ValueError(f"{field_name} must be a positive integer or None")
        if not require_foreground and (
            expected_process_id is None or expected_window_handle is None
        ):
            raise ValueError("non-foreground dispatch requires exact process and window identities")
        now = self._clock()
        client = self._resolve_client(
            expected_process_id=expected_process_id,
            expected_window_handle=expected_window_handle,
            require_foreground=require_foreground,
        )
        permit = self._exact_permit(client, now=now)
        return now, client, permit

    def _submit(
        self,
        client: ClientInstanceSnapshot,
        operation: WorkerOperation,
    ) -> WorkerOperationDispatch:
        submission = self._operations.submit(operation)
        acknowledgement = self._operations.wait_for_acknowledgement(
            submission.operation,
            timeout_seconds=self._acknowledgement_timeout_seconds,
        )
        return WorkerOperationDispatch(
            client=client,
            operation=submission.operation,
            acknowledgement=acknowledgement,
            duplicate=submission.duplicate,
        )

    def _resolve_client(
        self,
        *,
        expected_process_id: int | None,
        expected_window_handle: int | None,
        require_foreground: bool,
    ) -> ClientInstanceSnapshot:
        snapshot = self._registry.inspect()
        if not isinstance(snapshot, ClientRegistrySnapshot):
            raise WorkerOperationIngressError("client registry returned an invalid snapshot")
        if snapshot.node_id != self._manifest.node_id:
            raise WorkerOperationIngressError("client registry returned the wrong node")
        matches = tuple(
            client
            for client in snapshot.clients
            if client.is_visible
            and (client.is_foreground or not require_foreground)
            and (expected_process_id is None or client.process_id == expected_process_id)
            and (expected_window_handle is None or client.window_handle == expected_window_handle)
        )
        if len(matches) != 1:
            if require_foreground:
                detail = (
                    "foreground managed client is not uniquely identifiable"
                    if expected_process_id is None
                    else "foreground managed client does not match the guarded process"
                )
            else:
                detail = "managed client does not match the captured process and window"
            raise WorkerOperationIngressError(detail)
        return matches[0]

    def _exact_permit(
        self,
        client: ClientInstanceSnapshot,
        *,
        now: float,
    ) -> WorkerDispatchPermit:
        matches: list[WorkerDispatchPermit] = []
        for config in self._manifest.clients:
            permit = self._permits.inspect_permit(config.client_id)
            if permit is None or permit.instance_id != client.instance_id:
                continue
            if permit.node_id != self._manifest.node_id:
                raise WorkerOperationIngressError(
                    "worker dispatch permit belongs to the wrong node"
                )
            if not permit.allowed:
                raise WorkerOperationIngressError(
                    f"exact worker dispatch is disabled: {permit.reason}"
                )
            if permit.issued_at > now or permit.expires_at <= now:
                raise WorkerOperationIngressError(
                    "exact worker dispatch permit is not currently valid"
                )
            matches.append(permit)
        if len(matches) != 1:
            raise WorkerOperationIngressError(
                "foreground client is not owned by exactly one healthy worker"
            )
        return matches[0]


__all__ = [
    "ClientRegistryProvider",
    "ForegroundWorkerOperationIngress",
    "WorkerOperationDispatch",
    "WorkerOperationIngressError",
    "WorkerPermitProvider",
]
