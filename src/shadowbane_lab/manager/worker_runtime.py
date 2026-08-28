"""Exact game-instance worker bootstrap and local lifecycle control.

The manager owns assignment, while each worker owns one immutable game process/window
lifetime.  This module intentionally contains no strategy: it is the permanent safety
host into which travel, PvE, and later group tactics are composed.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Protocol

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


@dataclass(frozen=True, slots=True)
class ExactClientWorkerBinding:
    """Only the immutable game identity needed by a per-client worker."""

    client_id: str
    instance_id: str
    game_process_id: int
    game_process_started_at_100ns: int
    game_window_handle: int

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
        if self._local.is_set() or self._dispatch_gate.is_set():
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
            return True
        return any(operation.kind is WorkerOperationKind.STOP for operation in pending)


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
        if not callable(sleeper):
            raise ValueError("sleeper must be callable")
        if (operation_ledger is None) != (operation_executor is None):
            raise ValueError(
                "operation_ledger and operation_executor must be configured together"
            )
        if operation_ledger is not None and not isinstance(
            operation_ledger, WorkerOperationLedger
        ):
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
        )
        publisher.publish(
            WorkerRuntimeState.STARTING,
            detail="verifying exact game process and window identity",
        )
        final_detail = "worker runtime stopped"
        active_operation: _ActiveWorkerOperation | None = None
        evidence_sequence = 0
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
                self._sleep(self._interval)
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
        observed_at = time.time()
        ledger.publish_receipt(
            WorkerOperationReceipt.for_operation(
                operation,
                WorkerOperationState.ACCEPTED,
                observed_at=observed_at,
                detail="accepted by exact per-client worker",
            )
        )
        ledger.publish_receipt(
            WorkerOperationReceipt.for_operation(
                operation,
                WorkerOperationState.ACTIVE,
                observed_at=max(time.time(), observed_at),
                detail="executing through the exact worker dispatch gate",
            )
        )
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
            raise ExactClientWorkerError(f"could not launch exact client worker: {exc}") from exc
        return process.pid


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
        if reusable:
            return None
        return self._launcher.launch(binding)

    def request_stop(self, client_id: str, *, reason: str) -> int:
        if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
            raise ValueError("reason must be canonical non-empty text")
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
        return stopped

    def _is_live(self, heartbeat: WorkerHeartbeat) -> bool:
        if self._clock() - heartbeat.observed_at >= self._timeout:
            return False
        process = self._process_inspector.inspect(heartbeat.process_id)
        return (
            isinstance(process, ProcessLifetimeSnapshot)
            and (process.process_started_at_100ns == heartbeat.process_started_at_100ns)
            and heartbeat.runtime_state
            not in {
                WorkerRuntimeState.STOPPED,
                WorkerRuntimeState.FAILED,
            }
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
