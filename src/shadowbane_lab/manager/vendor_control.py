"""Dashboard admission and worker execution for bounded vendor jobs."""

from __future__ import annotations

import json
import time
from pathlib import Path

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_completion import _read_record
from shadowbane_lab.client_extension.vendor_session import NativeVendorSession
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from shadowbane_lab.record_store import exclusive_record_lock

from .operation import (
    WorkerOperationExecution,
    WorkerOperationKind,
    WorkerOperationState,
    new_worker_operation,
)
from .vendor_job import TERMINAL, VendorJobStore, _write, run_vendor_job


class ManagerVendorControl:
    """Submit through the same exact worker ledger as travel and combat."""

    def __init__(self, root, node_id, permits, operations, *, clock=time.time):
        self.root, self.node_id = Path(root), node_id
        self.permits, self.operations, self.clock = permits, operations, clock

    def store(self, client_id, instance_id):
        return VendorJobStore(self.root, self.node_id, client_id, instance_id)

    def summary(self, client_id, instance_id):
        return self.store(client_id, instance_id).summary() if instance_id else None

    def execute(self, action, client_id, instance_id, *, job_id=None):
        store = self.store(client_id, instance_id)
        with exclusive_record_lock(store.root / "admission.lock"):
            current = store.current()
            if action != "vendor-start" and (not current or current["job_id"] != job_id):
                raise VendorBatchStopped("the selected vendor batch changed; refresh its controls")
            if action in {"vendor-pause", "vendor-stop"}:
                if not current:
                    raise VendorBatchStopped("no current vendor job")
                store.request(current["job_id"], "pause" if action == "vendor-pause" else "stop")
                if action == "vendor-stop":
                    # An idle worker cannot acknowledge a stop. Acquiring the
                    # execution lock proves no runner can still submit actions.
                    try:
                        with exclusive_record_lock(
                            store.root / "execution.lock", timeout_seconds=0.1
                        ):
                            current = store.current()
                            if current["state"] in TERMINAL:
                                return
                            directory = store.directory(current["job_id"])
                            for name in ("create.json", "keep.json"):
                                path = directory / name
                                if (
                                    path.exists()
                                    and json.loads(_read_record(path))["state"] != "complete"
                                ):
                                    current.update(
                                        state="review", detail="Interrupted action requires review."
                                    )
                                    store.save(current)
                                    return
                            current.update(state="stopped", detail="Vendor job stopped.")
                            store.save(current)
                    except TimeoutError:
                        pass
                return
            if action not in {"vendor-start", "vendor-resume"}:
                raise ValueError("unknown vendor action")
            permit = self.permits.inspect_permit(client_id)
            now = self.clock()
            if (
                permit is None
                or not permit.allowed
                or permit.instance_id != instance_id
                or permit.node_id != self.node_id
                or permit.client_id != client_id
                or not permit.issued_at <= now < permit.expires_at
            ):
                raise VendorBatchStopped("resume client dispatch and wait for a healthy worker")
            expected_capability = {
                "schema_version": 1,
                "capability": "vendor_batch_v1",
                "worker_id": permit.worker_id,
                "process_id": permit.process_id,
                "process_started_at_100ns": permit.process_started_at_100ns,
            }
            capability_path = store.root / "worker-capability.json"
            if (
                not capability_path.exists()
                or json.loads(_read_record(capability_path, 1024)) != expected_capability
            ):
                raise VendorBatchStopped("restart this client worker with the vendor-capable host")
            target = (
                permit.node_id,
                permit.client_id,
                permit.instance_id,
                permit.worker_id,
                permit.process_id,
                permit.process_started_at_100ns,
            )
            inflight = [
                s
                for s in self.operations.inspect_slot(client_id)
                if s.operation.target_identity() == target
                and (
                    s.receipt is None
                    and s.operation.expires_at > now
                    or s.receipt is not None
                    and not s.receipt.state.terminal
                )
            ]
            if action == "vendor-start":
                if inflight or current and current["state"] not in {"complete", "stopped"}:
                    raise VendorBatchStopped(
                        "finish, resume, or review the current operation first"
                    )
                command = "vendor start"
            else:
                if not current or current["state"] in TERMINAL:
                    raise VendorBatchStopped("no resumable vendor job")
                if inflight:
                    if (
                        len(inflight) != 1
                        or inflight[0].operation.kind is not WorkerOperationKind.VENDOR
                    ):
                        raise VendorBatchStopped("another operation owns this worker")
                    store.request(current["job_id"], "run")
                    return
                store.request(current["job_id"], "run")
                command = "vendor resume " + current["job_id"]
            self.operations.submit(
                new_worker_operation(
                    permit,
                    WorkerOperationKind.VENDOR,
                    command,
                    now=now,
                )
            )


def open_vendor_session(binding):
    memory = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", binding.game_process_id)
    try:
        if (
            memory.process_creation_filetime_utc != binding.game_process_started_at_100ns
            or memory.executable_sha256
            != "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87"
        ):
            raise VendorBatchStopped("the vendor client lifetime or executable is unqualified")
    finally:
        memory.close()
    return NativeVendorSession(
        NativeClientProcessIdentity(
            binding.game_process_id,
            binding.game_process_started_at_100ns,
        ),
        binding.game_window_handle,
    )


class VendorWorkerExecutor:
    def __init__(self, root, node_id, binding, *, session_factory=open_vendor_session):
        self.node_id = node_id
        self.root, self.binding, self.session_factory = Path(root), binding, session_factory

    def initialize(self, worker_id, process):
        store = VendorJobStore(
            self.root,
            self.node_id,
            self.binding.client_id,
            self.binding.instance_id,
        )
        _write(
            store.root / "worker-capability.json",
            {
                "schema_version": 1,
                "capability": "vendor_batch_v1",
                "worker_id": worker_id,
                "process_id": process.process_id,
                "process_started_at_100ns": process.process_started_at_100ns,
            },
        )

    def execute(self, operation, *, stop_signal):
        binding = self.binding
        if (
            operation.kind is not WorkerOperationKind.VENDOR
            or operation.instance_id != binding.instance_id
            or operation.client_id != binding.client_id
            or operation.node_id != self.node_id
            or binding.worker_id is not None
            and operation.worker_id != binding.worker_id
        ):
            raise VendorBatchStopped("vendor operation does not own this exact worker")
        store = VendorJobStore(
            self.root,
            self.node_id,
            binding.client_id,
            binding.instance_id,
        )
        resume = operation.command.startswith("vendor resume ")
        if resume:
            current = store.current()
            if not current or current["job_id"] != operation.command.removeprefix("vendor resume "):
                raise VendorBatchStopped("the requested vendor job is no longer current")
        if stop_signal.is_set():
            return WorkerOperationExecution(
                WorkerOperationState.CANCELLED, "Vendor dispatch paused."
            )
        session = self.session_factory(binding)
        try:
            record = run_vendor_job(
                store,
                session,
                binding.game_window_handle,
                resume=resume,
                cancelled=stop_signal.is_set,
            )
        finally:
            session.close()
        return WorkerOperationExecution(
            WorkerOperationState.SUCCEEDED
            if record["state"] == "complete"
            else WorkerOperationState.CANCELLED,
            record["detail"],
        )
