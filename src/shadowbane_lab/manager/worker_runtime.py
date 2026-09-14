"""Exact game-instance worker bootstrap and local lifecycle control.

The manager owns assignment, while each worker owns one immutable game process/window
lifetime.  This module intentionally contains no strategy: it is the permanent safety
host into which travel, PvE, and later group tactics are composed.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from typing import Protocol

from shadowbane_lab.record_store import exclusive_record_lock, publish_atomic_record

from .manifest import ManagerManifest
from .model import ClientInstanceSnapshot, ClientRegistrySnapshot
from .operation import (
    WorkerOperation,
    WorkerOperationExecution,
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationReceipt,
    WorkerOperationState,
)
from .registry import derive_client_instance_id
from .supervisor import ProcessLifetimeInspector, ProcessLifetimeSnapshot
from .worker import (
    DEFAULT_WORKER_HEARTBEAT_TIMEOUT_SECONDS,
    WorkerHeartbeat,
    WorkerHeartbeatLedger,
    WorkerHeartbeatPublisher,
    WorkerRuntimeState,
    WorkerStopRequest,
)


class ExactClientWorkerError(RuntimeError):
    """Raised when exact worker ownership cannot be established safely."""


class _WorkerNotLaunched(ExactClientWorkerError):
    """The launcher failed before creating a process."""


@dataclass(frozen=True, slots=True)
class ExactClientWorkerBinding:
    """Only the immutable game identity needed by a per-client worker."""

    client_id: str
    instance_id: str
    game_process_id: int
    game_process_started_at_100ns: int
    game_window_handle: int
    worker_id: str | None = None

    @classmethod
    def from_client(
        cls,
        client_id: str,
        client: ClientInstanceSnapshot,
    ) -> ExactClientWorkerBinding:
        if not isinstance(client, ClientInstanceSnapshot):
            raise ValueError("client must be ClientInstanceSnapshot")
        return cls(
            client_id=client_id,
            instance_id=client.instance_id,
            game_process_id=client.process_id,
            game_process_started_at_100ns=client.process_started_at_100ns,
            game_window_handle=client.window_handle,
        )

    def validate_for(self, manifest: ManagerManifest) -> None:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        if (
            self.worker_id is not None
            and re.fullmatch(r"worker-[0-9a-f]{32}", self.worker_id) is None
        ):
            raise ExactClientWorkerError("invalid reserved worker identity")
        known = {config.client_id for config in manifest.clients}
        if self.client_id not in known:
            raise ExactClientWorkerError(f"unknown manifest client_id {self.client_id!r}")
        expected = derive_client_instance_id(
            manifest.node_id,
            self.game_process_id,
            self.game_process_started_at_100ns,
            self.game_window_handle,
        )
        if self.instance_id != expected:
            raise ExactClientWorkerError(
                "worker instance_id does not match its PID, process creation time, and HWND"
            )


class RegistryProvider(Protocol):
    def inspect(self) -> ClientRegistrySnapshot: ...


class StopSignal(Protocol):
    def is_set(self) -> bool: ...


class WorkerProcessLauncher(Protocol):
    def launch(self, binding: ExactClientWorkerBinding) -> int: ...


class WorkerOperationExecutor(Protocol):
    def execute(
        self,
        operation: WorkerOperation,
        *,
        stop_signal: StopSignal,
    ) -> WorkerOperationExecution: ...


class _OperationStopSignal:
    def __init__(
        self,
        dispatch_gate: StopSignal,
        operation_ledger: WorkerOperationLedger,
        binding: ExactClientWorkerBinding,
        worker_id: str,
        worker_process_id: int,
        worker_process_started_at_100ns: int,
    ) -> None:
        self._dispatch_gate = dispatch_gate
        self._ledger = operation_ledger
        self._binding = binding
        self._worker_id = worker_id
        self._worker_process_id = worker_process_id
        self._worker_process_started_at_100ns = worker_process_started_at_100ns
        self._local = threading.Event()

    def trip(self) -> None:
        self._local.set()

    def is_set(self) -> bool:
        if self._local.is_set():
            return True
        if self._dispatch_gate.is_set():
            self.trip()
            return True
        try:
            pending = self._ledger.pending_for(
                client_id=self._binding.client_id,
                instance_id=self._binding.instance_id,
                worker_id=self._worker_id,
                worker_process_id=self._worker_process_id,
                worker_process_started_at_100ns=self._worker_process_started_at_100ns,
                now=time.time(),
            )
        except (OSError, RuntimeError, ValueError):
            self.trip()
            return True
        interrupted = any(
            operation.kind
            in {
                WorkerOperationKind.CANCEL,
                WorkerOperationKind.STOP,
            }
            for operation in pending
        )
        if interrupted:
            self.trip()
        return interrupted


@dataclass(slots=True)
class _ActiveWorkerOperation:
    operation: WorkerOperation
    thread: threading.Thread
    stop_signal: _OperationStopSignal
    results: queue.Queue[WorkerOperationExecution]


class ExactClientWorkerRuntime:
    """Publish health only while one exact visible game identity remains current."""

    def __init__(
        self,
        manifest: ManagerManifest,
        binding: ExactClientWorkerBinding,
        ledger: WorkerHeartbeatLedger,
        registry: RegistryProvider,
        process_inspector: ProcessLifetimeInspector,
        *,
        operation_ledger: WorkerOperationLedger | None = None,
        operation_executor: WorkerOperationExecutor | None = None,
        operation_maintenance: Callable[[WorkerOperation, StopSignal], None] | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
        process_id: int | None = None,
        heartbeat_interval_seconds: float = 1.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        if not isinstance(binding, ExactClientWorkerBinding):
            raise ValueError("binding must be ExactClientWorkerBinding")
        if not isinstance(ledger, WorkerHeartbeatLedger):
            raise ValueError("ledger must be WorkerHeartbeatLedger")
        if not callable(getattr(registry, "inspect", None)):
            raise ValueError("registry must provide inspect()")
        if not callable(getattr(process_inspector, "inspect", None)):
            raise ValueError("process_inspector must provide inspect(process_id)")
        if (
            isinstance(heartbeat_interval_seconds, bool)
            or not isinstance(heartbeat_interval_seconds, (int, float))
            or not isfinite(heartbeat_interval_seconds)
            or heartbeat_interval_seconds <= 0
        ):
            raise ValueError("heartbeat_interval_seconds must be finite and positive")
        if operation_maintenance is not None and not callable(operation_maintenance):
            raise ValueError("operation_maintenance must be callable")
        if not callable(monotonic_clock):
            raise ValueError("monotonic_clock must be callable")
        if not callable(sleeper):
            raise ValueError("sleeper must be callable")
        if (operation_ledger is None) != (operation_executor is None):
            raise ValueError("operation_ledger and operation_executor must be configured together")
        if operation_ledger is not None and not isinstance(operation_ledger, WorkerOperationLedger):
            raise ValueError("operation_ledger must be WorkerOperationLedger")
        if operation_executor is not None and not callable(
            getattr(operation_executor, "execute", None)
        ):
            raise ValueError("operation_executor must provide execute()")
        binding.validate_for(manifest)
        if ledger.node_id != manifest.node_id:
            raise ExactClientWorkerError("worker ledger belongs to a different manager node")
        resolved_process_id = os.getpid() if process_id is None else process_id
        if (
            isinstance(resolved_process_id, bool)
            or not isinstance(resolved_process_id, int)
            or resolved_process_id <= 0
        ):
            raise ValueError("process_id must be a positive integer")
        process = process_inspector.inspect(resolved_process_id)
        if not isinstance(process, ProcessLifetimeSnapshot):
            raise ExactClientWorkerError("exact worker process lifetime could not be verified")
        self._manifest = manifest
        self._binding = binding
        self._ledger = ledger
        self._registry = registry
        self._process = process
        self._interval = float(heartbeat_interval_seconds)
        self._sleep = sleeper
        self._operation_ledger = operation_ledger
        self._operation_executor = operation_executor
        self._operation_maintenance = operation_maintenance
        self._monotonic = monotonic_clock

    @property
    def process(self) -> ProcessLifetimeSnapshot:
        return self._process

    def serve(self, *, stop_signal: StopSignal | None = None) -> int:
        """Run until an exact stop request, local stop, or game identity loss."""

        publisher = WorkerHeartbeatPublisher(
            self._ledger,
            node_id=self._manifest.node_id,
            client_id=self._binding.client_id,
            instance_id=self._binding.instance_id,
            process=self._process,
            worker_id=self._binding.worker_id,
        )
        publisher.publish(
            WorkerRuntimeState.STARTING,
            detail="verifying exact game process and window identity",
        )
        final_detail = "worker runtime stopped"
        active_operation: _ActiveWorkerOperation | None = None
        evidence_sequence = 0
        next_heartbeat = self._monotonic()
        try:
            while stop_signal is None or not stop_signal.is_set():
                request = self._ledger.inspect_stop_request(
                    self._binding.client_id,
                    publisher.worker_id,
                )
                if request is not None:
                    self._require_matching_stop_request(request, publisher)
                    final_detail = request.reason
                    if active_operation is not None:
                        self._cancel_active_operation(
                            active_operation,
                            detail=request.reason,
                        )
                    publisher.publish(
                        WorkerRuntimeState.STOPPING,
                        detail=request.reason,
                    )
                    return 0

                self._require_exact_game_identity()
                if active_operation is not None and not active_operation.thread.is_alive():
                    self._complete_active_operation(active_operation)
                    evidence_sequence += 1
                    active_operation = None
                if active_operation is None:
                    active_operation = self._start_next_operation(publisher)
                if active_operation is not None and self._operation_maintenance is not None:
                    # Renewal is independent of heartbeat publication and runs on
                    # this worker's supervision thread, never the strategy thread.
                    # A revoked permit is latched before any maintenance callback.
                    if not active_operation.stop_signal.is_set():
                        self._operation_maintenance(
                            active_operation.operation, active_operation.stop_signal
                        )
                now = self._monotonic()
                if self._operation_maintenance is None or now >= next_heartbeat:
                    publisher.publish(
                        WorkerRuntimeState.RUNNING,
                        dispatch_ready=True,
                        detail=(
                            "exact game identity and guarded dispatch boundary are ready"
                            if active_operation is None
                            else (
                                f"{active_operation.operation.kind.value} operation "
                                f"{active_operation.operation.operation_id} is active"
                            )
                        ),
                        evidence_sequence=evidence_sequence,
                    )
                    next_heartbeat = now + self._interval
                delay = self._interval if self._operation_maintenance is None else min(
                    0.25, max(0.0, next_heartbeat - self._monotonic())
                )
                self._sleep(delay)
            final_detail = "local worker stop signal was set"
            if active_operation is not None:
                self._cancel_active_operation(
                    active_operation,
                    detail=final_detail,
                )
            publisher.publish(
                WorkerRuntimeState.STOPPING,
                detail=final_detail,
            )
            return 0
        except KeyboardInterrupt:
            final_detail = "worker interrupted locally"
            if active_operation is not None:
                self._cancel_active_operation(
                    active_operation,
                    detail=final_detail,
                )
            publisher.publish(
                WorkerRuntimeState.STOPPING,
                detail=final_detail,
            )
            return 0
        except Exception as exc:
            final_detail = str(exc)[:512] or "worker runtime failed"
            if active_operation is not None:
                self._cancel_active_operation(
                    active_operation,
                    detail=final_detail,
                )
            publisher.publish(
                WorkerRuntimeState.FAILED,
                emergency_stop=True,
                detail=final_detail,
            )
            return 1
        finally:
            publisher.close(detail=final_detail)

    def _start_next_operation(
        self,
        publisher: WorkerHeartbeatPublisher,
    ) -> _ActiveWorkerOperation | None:
        ledger = self._operation_ledger
        executor = self._operation_executor
        if ledger is None or executor is None:
            return None
        pending = ledger.pending_for(
            client_id=self._binding.client_id,
            instance_id=self._binding.instance_id,
            worker_id=publisher.worker_id,
            worker_process_id=self._process.process_id,
            worker_process_started_at_100ns=self._process.process_started_at_100ns,
            now=time.time(),
        )
        if not pending:
            return None
        operation = pending[0]
        if not ledger.claim_for_execution(operation, now=time.time()):
            return None
        operation_stop = _OperationStopSignal(
            publisher.dispatch_gate(),
            ledger,
            self._binding,
            publisher.worker_id,
            self._process.process_id,
            self._process.process_started_at_100ns,
        )
        results: queue.Queue[WorkerOperationExecution] = queue.Queue(maxsize=1)

        def execute() -> None:
            try:
                result = executor.execute(operation, stop_signal=operation_stop)
                if not isinstance(result, WorkerOperationExecution):
                    raise ExactClientWorkerError(
                        "worker operation executor returned an invalid result"
                    )
            except Exception as exc:
                result = WorkerOperationExecution(
                    WorkerOperationState.FAILED,
                    detail=(str(exc)[:512] or "worker operation failed"),
                )
            results.put(result)

        thread = threading.Thread(
            target=execute,
            name=f"shadowbane-{self._binding.client_id}-{operation.kind.value}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception as exc:
            ledger.publish_receipt(
                WorkerOperationReceipt.for_operation(
                    operation,
                    WorkerOperationState.FAILED,
                    observed_at=time.time(),
                    detail=(str(exc)[:512] or "operation thread failed to start"),
                )
            )
            return None
        return _ActiveWorkerOperation(operation, thread, operation_stop, results)

    def _complete_active_operation(self, active: _ActiveWorkerOperation) -> None:
        ledger = self._operation_ledger
        if ledger is None:
            raise ExactClientWorkerError("active operation has no operation ledger")
        try:
            result = active.results.get_nowait()
        except queue.Empty as exc:
            raise ExactClientWorkerError(
                "operation thread exited without a terminal result"
            ) from exc
        ledger.publish_receipt(
            WorkerOperationReceipt.for_operation(
                active.operation,
                result.state,
                observed_at=time.time(),
                detail=result.detail,
            )
        )

    def _cancel_active_operation(
        self,
        active: _ActiveWorkerOperation,
        *,
        detail: str,
    ) -> None:
        ledger = self._operation_ledger
        if ledger is None:
            raise ExactClientWorkerError("active operation has no operation ledger")
        active.stop_signal.trip()
        active.thread.join(timeout=max(2.0, self._interval * 2.0))
        if active.thread.is_alive():
            ledger.publish_receipt(
                WorkerOperationReceipt.for_operation(
                    active.operation,
                    WorkerOperationState.FAILED,
                    observed_at=time.time(),
                    detail="operation did not stop before its worker runtime exited",
                )
            )
            return
        try:
            result = active.results.get_nowait()
        except queue.Empty:
            result = WorkerOperationExecution(
                WorkerOperationState.CANCELLED,
                detail=detail[:512],
            )
        if result.state is WorkerOperationState.SUCCEEDED:
            result = WorkerOperationExecution(
                WorkerOperationState.CANCELLED,
                detail=detail[:512],
            )
        ledger.publish_receipt(
            WorkerOperationReceipt.for_operation(
                active.operation,
                result.state,
                observed_at=time.time(),
                detail=result.detail,
            )
        )

    def _require_exact_game_identity(self) -> ClientInstanceSnapshot:
        snapshot = self._registry.inspect()
        if not isinstance(snapshot, ClientRegistrySnapshot):
            raise ExactClientWorkerError("worker registry returned an invalid snapshot")
        if snapshot.node_id != self._manifest.node_id:
            raise ExactClientWorkerError("worker registry returned the wrong manager node")
        matches = tuple(
            client for client in snapshot.clients if client.instance_id == self._binding.instance_id
        )
        if len(matches) != 1:
            raise ExactClientWorkerError(
                "exact game process/window identity is no longer uniquely visible"
            )
        client = matches[0]
        observed = (
            client.process_id,
            client.process_started_at_100ns,
            client.window_handle,
        )
        expected = (
            self._binding.game_process_id,
            self._binding.game_process_started_at_100ns,
            self._binding.game_window_handle,
        )
        if observed != expected:
            raise ExactClientWorkerError("immutable game process/window identity changed")
        return client

    def _require_matching_stop_request(
        self,
        request: WorkerStopRequest,
        publisher: WorkerHeartbeatPublisher,
    ) -> None:
        expected = (
            self._manifest.node_id,
            self._binding.client_id,
            publisher.worker_id,
            self._process.process_id,
            self._process.process_started_at_100ns,
        )
        observed = (
            request.node_id,
            request.client_id,
            request.worker_id,
            request.process_id,
            request.process_started_at_100ns,
        )
        if observed != expected:
            raise ExactClientWorkerError(
                "worker stop request does not own this exact process lifetime"
            )


class SubprocessWorkerLauncher:
    """Launch the exact worker CLI directly, with local append-only diagnostics."""

    def __init__(
        self,
        *,
        manifest_path: Path,
        worker_state_directory: Path,
        log_directory: Path,
        python_executable: Path | None = None,
        heartbeat_interval_ms: int = 1_000,
    ) -> None:
        if (
            isinstance(heartbeat_interval_ms, bool)
            or not isinstance(heartbeat_interval_ms, int)
            or not 100 <= heartbeat_interval_ms <= 4_000
        ):
            raise ValueError("heartbeat_interval_ms must be in [100, 4000]")
        self._manifest_path = Path(manifest_path).resolve(strict=False)
        self._worker_state_directory = Path(worker_state_directory).resolve(strict=False)
        self._log_directory = Path(log_directory).resolve(strict=False)
        self._python_executable = Path(
            sys.executable if python_executable is None else python_executable
        ).resolve(strict=False)
        self._heartbeat_interval_ms = heartbeat_interval_ms
        self._children: dict[str, subprocess.Popen[bytes]] = {}
        self._durable_children: set[str] = set()
        self._children_lock = threading.Lock()

    def launch(self, binding: ExactClientWorkerBinding) -> int:
        if not isinstance(binding, ExactClientWorkerBinding):
            raise ValueError("binding must be ExactClientWorkerBinding")
        self._log_directory.mkdir(parents=True, exist_ok=True)
        stdout_path = self._log_directory / f"worker-{binding.client_id}.stdout.log"
        stderr_path = self._log_directory / f"worker-{binding.client_id}.stderr.log"
        argv = (
            str(self._python_executable),
            "-u",
            "-m",
            "shadowbane_lab.cli",
            "manager",
            "worker",
            str(self._manifest_path),
            "--worker-state-directory",
            str(self._worker_state_directory),
            "--client-id",
            binding.client_id,
            "--instance-id",
            binding.instance_id,
            "--game-process-id",
            str(binding.game_process_id),
            "--game-process-started-at-100ns",
            str(binding.game_process_started_at_100ns),
            "--game-window-handle",
            str(binding.game_window_handle),
            "--heartbeat-ms",
            str(self._heartbeat_interval_ms),
            "--live",
        )
        if binding.worker_id is not None:
            argv += ("--worker-id", binding.worker_id)
        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            with (
                stdout_path.open("ab") as stdout,
                stderr_path.open("ab") as stderr,
            ):
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    close_fds=True,
                    creationflags=creation_flags,
                )
        except OSError as exc:
            raise _WorkerNotLaunched(f"could not launch exact client worker: {exc}") from exc
        with self._children_lock:
            finished = {
                token
                for token, child in self._children.items()
                if token in self._durable_children and child.poll() is not None
            }
            for token in finished:
                del self._children[token]
            self._durable_children.difference_update(finished)
            self._children[binding.worker_id or f"unreserved-{uuid.uuid4().hex}"] = process
        return process.pid

    def recover(
        self, process_id: int, inspector: ProcessLifetimeInspector, *, worker_id: str
    ) -> ProcessLifetimeSnapshot | None:
        """Reinspect a retained child; None proves that this child exited."""
        with self._children_lock:
            child = self._children.get(worker_id)
        if child is None or child.pid != process_id:
            raise ExactClientWorkerError("worker launch has no retained process ownership")
        if child.poll() is not None:
            return None
        process = inspector.inspect(process_id)
        if child.poll() is not None:
            return None
        if not isinstance(process, ProcessLifetimeSnapshot) or process.process_id != process_id:
            raise ExactClientWorkerError(
                f"launched worker {process_id} requires attachment recovery"
            )
        return process

    def acknowledge_reservation(self, worker_id: str) -> None:
        """Allow reaping only after the controller durably recorded or retired ownership."""
        with self._children_lock:
            if worker_id in self._children:
                self._durable_children.add(worker_id)


class ManagedWorkerController:
    """Ensure one live worker per exact slot and issue identity-bound stop requests."""

    def __init__(
        self,
        manifest: ManagerManifest,
        ledger: WorkerHeartbeatLedger,
        process_inspector: ProcessLifetimeInspector,
        launcher: WorkerProcessLauncher,
        *,
        clock: Callable[[], float] = time.time,
        heartbeat_timeout_seconds: float = DEFAULT_WORKER_HEARTBEAT_TIMEOUT_SECONDS,
    ) -> None:
        if not isinstance(manifest, ManagerManifest):
            raise ValueError("manifest must be ManagerManifest")
        if not isinstance(ledger, WorkerHeartbeatLedger):
            raise ValueError("ledger must be WorkerHeartbeatLedger")
        if not callable(getattr(process_inspector, "inspect", None)):
            raise ValueError("process_inspector must provide inspect(process_id)")
        if not callable(getattr(launcher, "launch", None)):
            raise ValueError("launcher must provide launch(binding)")
        if not callable(clock):
            raise ValueError("clock must be callable")
        if (
            isinstance(heartbeat_timeout_seconds, bool)
            or not isinstance(heartbeat_timeout_seconds, (int, float))
            or not isfinite(heartbeat_timeout_seconds)
            or heartbeat_timeout_seconds <= 0
        ):
            raise ValueError("heartbeat_timeout_seconds must be finite and positive")
        self._manifest = manifest
        self._ledger = ledger
        self._process_inspector = process_inspector
        self._launcher = launcher
        self._clock = clock
        self._timeout = float(heartbeat_timeout_seconds)

    def ensure_started(
        self,
        client_id: str,
        client: ClientInstanceSnapshot,
    ) -> int | None:
        directory = self._ledger.root / self._manifest.node_id / client_id
        # Validate the slot before constructing any filesystem transaction path.
        ExactClientWorkerBinding.from_client(client_id, client).validate_for(self._manifest)
        with exclusive_record_lock(directory / ".launch.lock"):
            return self._ensure_started_owned(client_id, client, directory / ".launch-reservation")

    def _ensure_started_owned(
        self,
        client_id: str,
        client: ClientInstanceSnapshot,
        reservation_path: Path,
    ) -> int | None:
        binding = ExactClientWorkerBinding.from_client(client_id, client)
        binding.validate_for(self._manifest)
        snapshot = self._ledger.inspect(client_id)
        if snapshot.issues:
            raise ExactClientWorkerError(
                "invalid worker heartbeat records must be reviewed before launch"
            )
        live = tuple(record for record in snapshot.records if self._is_live(record))
        exact = tuple(record for record in live if record.instance_id == client.instance_id)
        if len(exact) > 1:
            raise ExactClientWorkerError(
                "multiple live workers already claim this exact client instance"
            )
        reusable = tuple(
            record
            for record in exact
            if not record.emergency_stop
            and record.runtime_state
            in {
                WorkerRuntimeState.STARTING,
                WorkerRuntimeState.RUNNING,
                WorkerRuntimeState.DEGRADED,
            }
        )
        for record in live:
            if record not in reusable:
                self._request_record_stop(
                    record,
                    reason="worker is bound to a replaced or stopping game instance",
                )
        if live:
            return None
        if reservation_path.exists():
            reservation = self._read_reservation(reservation_path)
            process_id = reservation["process_id"]
            started = reservation["process_started_at_100ns"]
            if process_id is not None and started is None:
                recover = getattr(self._launcher, "recover", None)
                if callable(recover):
                    process = recover(
                        process_id, self._process_inspector, worker_id=reservation["worker_id"]
                    )
                    if process is not None:
                        reservation["process_started_at_100ns"] = process.process_started_at_100ns
                        reservation["state"] = "started"
                        publish_atomic_record(
                            reservation_path,
                            json.dumps(reservation).encode(),
                            temporary_label="worker-launch",
                        )
                        self._acknowledge_reservation(reservation["worker_id"])
                        return None
                    # Only the retained child handle can establish exit before attachment.
                    reservation_path.unlink()
                    self._acknowledge_reservation(reservation["worker_id"])
                    return self._ensure_started_owned(client_id, client, reservation_path)
            if process_id is None or started is None:
                raise ExactClientWorkerError("previous worker launch requires explicit recovery")
            process = self._process_inspector.inspect(process_id)
            if process is not None and process.process_started_at_100ns == started:
                return None
            # Only verified exit/PID replacement retires the reservation.
            reservation_path.unlink()
        binding = replace(binding, worker_id=f"worker-{uuid.uuid4().hex}")
        reservation = {
            "schema_version": 1,
            "worker_id": binding.worker_id,
            "instance_id": client.instance_id,
            "process_id": None,
            "process_started_at_100ns": None,
            "state": "launching",
        }
        publish_atomic_record(
            reservation_path, json.dumps(reservation).encode(), temporary_label="worker-launch"
        )
        try:
            process_id = self._launcher.launch(binding)
        except _WorkerNotLaunched:
            # This exception is emitted only before Popen returned a child.
            reservation_path.unlink()
            raise
        reservation["process_id"] = process_id
        reservation["state"] = "unverified"
        publish_atomic_record(
            reservation_path, json.dumps(reservation).encode(), temporary_label="worker-launch"
        )
        recover = getattr(self._launcher, "recover", None)
        process = (
            recover(process_id, self._process_inspector, worker_id=reservation["worker_id"])
            if callable(recover)
            else self._process_inspector.inspect(process_id)
        )
        if not isinstance(process, ProcessLifetimeSnapshot) or process.process_id != process_id:
            raise ExactClientWorkerError(
                f"launched worker {process_id} requires attachment recovery"
            )
        reservation["process_started_at_100ns"] = process.process_started_at_100ns
        reservation["state"] = "started"
        publish_atomic_record(
            reservation_path, json.dumps(reservation).encode(), temporary_label="worker-launch"
        )
        self._acknowledge_reservation(reservation["worker_id"])
        return process_id

    def _acknowledge_reservation(self, worker_id: str) -> None:
        acknowledge = getattr(self._launcher, "acknowledge_reservation", None)
        if callable(acknowledge):
            acknowledge(worker_id)

    def request_stop(self, client_id: str, *, reason: str) -> int:
        if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
            raise ValueError("reason must be canonical non-empty text")
        # Share launch ownership across processes: a stop arriving while Popen or
        # initial verification is in flight must observe the completed reservation.
        canonical = self._ledger.inspect(client_id).client_id
        directory = self._ledger.root / self._manifest.node_id / canonical
        with exclusive_record_lock(directory / ".launch.lock"):
            return self._request_stop_owned(canonical, reason=reason)

    def _request_stop_owned(self, client_id: str, *, reason: str) -> int:
        snapshot = self._ledger.inspect(client_id)
        if snapshot.issues:
            raise ExactClientWorkerError(
                "invalid worker heartbeat records prevent an exact stop request"
            )
        stopped = 0
        for record in snapshot.records:
            if self._is_live(record):
                self._request_record_stop(record, reason=reason)
                stopped += 1
        path = self._ledger.root / self._manifest.node_id / client_id / ".launch-reservation"
        if path.exists():
            reservation = self._read_reservation(path)
            pid, started = (
                reservation.get("process_id"),
                reservation.get("process_started_at_100ns"),
            )
            worker_id = reservation.get("worker_id")
            if pid is not None and started is not None and worker_id is not None:
                process = self._process_inspector.inspect(pid)
                if (
                    isinstance(process, ProcessLifetimeSnapshot)
                    and process.process_started_at_100ns == started
                    and all(record.worker_id != worker_id for record in snapshot.records)
                ):
                    self._ledger.publish_stop_request(
                        WorkerStopRequest(
                            node_id=self._manifest.node_id,
                            client_id=client_id,
                            worker_id=worker_id,
                            process_id=pid,
                            process_started_at_100ns=started,
                            requested_at=self._clock(),
                            reason=reason,
                        )
                    )
                    stopped += 1
        return stopped

    @staticmethod
    def _read_reservation(path: Path) -> dict:
        try:
            if path.is_symlink() or path.stat().st_size > 4096:
                raise ValueError("reservation must be a bounded regular file")
            value = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(value, dict)
                or set(value)
                != {
                    "schema_version",
                    "worker_id",
                    "instance_id",
                    "process_id",
                    "process_started_at_100ns",
                    "state",
                }
                or type(value["schema_version"]) is not int
                or value["schema_version"] != 1
            ):
                raise ValueError("invalid reservation schema")
            if re.fullmatch(r"worker-[0-9a-f]{32}", value.get("worker_id", "")) is None:
                raise ValueError("invalid reserved worker identity")
            if not isinstance(value.get("instance_id"), str) or not value["instance_id"]:
                raise ValueError("missing reserved instance")
            for name in ("process_id", "process_started_at_100ns"):
                number = value.get(name)
                if number is not None and (type(number) is not int or number <= 0):
                    raise ValueError("invalid reserved process lifetime")
            if value.get("state") not in {"launching", "unverified", "started"}:
                raise ValueError("invalid reservation state")
            if (
                value.get("process_started_at_100ns") is not None
                and value.get("process_id") is None
            ):
                raise ValueError("incomplete reserved process lifetime")
            return value
        except (OSError, ValueError, TypeError) as exc:
            raise ExactClientWorkerError(f"invalid worker launch reservation: {exc}") from exc

    def _is_live(self, heartbeat: WorkerHeartbeat) -> bool:
        process = self._process_inspector.inspect(heartbeat.process_id)
        return isinstance(process, ProcessLifetimeSnapshot) and (
            process.process_started_at_100ns == heartbeat.process_started_at_100ns
        )

    def _request_record_stop(self, heartbeat: WorkerHeartbeat, *, reason: str) -> None:
        self._ledger.publish_stop_request(
            WorkerStopRequest(
                node_id=self._manifest.node_id,
                client_id=heartbeat.client_id,
                worker_id=heartbeat.worker_id,
                process_id=heartbeat.process_id,
                process_started_at_100ns=heartbeat.process_started_at_100ns,
                requested_at=self._clock(),
                reason=reason,
            )
        )


__all__ = [
    "ExactClientWorkerBinding",
    "ExactClientWorkerError",
    "ExactClientWorkerRuntime",
    "ManagedWorkerController",
    "RegistryProvider",
    "StopSignal",
    "SubprocessWorkerLauncher",
    "WorkerProcessLauncher",
]
