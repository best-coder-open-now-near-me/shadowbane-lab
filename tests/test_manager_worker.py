import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.manager.manifest import parse_manager_manifest
from shadowbane_lab.manager.supervisor import ProcessLifetimeSnapshot
from shadowbane_lab.manager.worker import (
    WorkerDispatchGate,
    WorkerHealthState,
    WorkerHeartbeat,
    WorkerHeartbeatFormatError,
    WorkerHeartbeatLedger,
    WorkerHeartbeatPublisher,
    WorkerRuntimeState,
    WorkerSupervisor,
    loads_worker_heartbeat,
)

NODE_ID = "gaming-pc-east"
CLIENT_ID = "client-01"
INSTANCE_ID = "client-0123456789abcdef"
WORKER_ID = "worker-0123456789abcdef0123456789abcdef"
PROCESS_STARTED_AT = 133_700_000_000_000_101


def _manifest():
    return parse_manager_manifest(
        {
            "schema_version": 1,
            "node_id": NODE_ID,
            "clients": [
                {
                    "client_id": CLIENT_ID,
                    "launch": {
                        "executable": r"C:\Games\Shadowbane\sb.exe",
                        "arguments": [],
                        "working_directory": r"C:\Games\Shadowbane",
                    },
                    "expected_process_directory": r"C:\Games\Shadowbane",
                    "expected_executable_names": ["sb.exe"],
                }
            ],
        }
    )


def _heartbeat(
    *,
    worker_id: str = WORKER_ID,
    process_id: int = 101,
    process_started_at_100ns: int = PROCESS_STARTED_AT,
    sequence: int = 1,
    observed_at: float = 1_000.0,
    instance_id: str = INSTANCE_ID,
    runtime_state: WorkerRuntimeState = WorkerRuntimeState.RUNNING,
    dispatch_ready: bool = True,
    emergency_stop: bool = False,
) -> WorkerHeartbeat:
    return WorkerHeartbeat(
        node_id=NODE_ID,
        client_id=CLIENT_ID,
        instance_id=instance_id,
        worker_id=worker_id,
        process_id=process_id,
        process_started_at_100ns=process_started_at_100ns,
        sequence=sequence,
        observed_at=observed_at,
        runtime_state=runtime_state,
        dispatch_ready=dispatch_ready,
        emergency_stop=emergency_stop,
    )


class _ProcessInspector:
    def __init__(self, *processes: ProcessLifetimeSnapshot) -> None:
        self.processes = {process.process_id: process for process in processes}

    def inspect(self, process_id: int) -> ProcessLifetimeSnapshot | None:
        return self.processes.get(process_id)


class ManagerWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.ledger = WorkerHeartbeatLedger(_manifest(), Path(self.temporary.name))
        self.process = ProcessLifetimeSnapshot(
            process_id=101,
            process_started_at_100ns=PROCESS_STARTED_AT,
        )

    def _supervisor(
        self,
        *processes: ProcessLifetimeSnapshot,
        now: float = 1_001.0,
        timeout: float = 5.0,
    ) -> WorkerSupervisor:
        return WorkerSupervisor(
            self.ledger,
            _ProcessInspector(*(processes or (self.process,))),
            clock=lambda: now,
            heartbeat_timeout_seconds=timeout,
        )

    def test_strict_round_trip_rejects_duplicate_and_unknown_fields(self) -> None:
        heartbeat = _heartbeat()
        encoded = json.dumps(heartbeat.to_dict(), sort_keys=True)

        self.assertEqual(heartbeat, loads_worker_heartbeat(encoded))
        with self.assertRaisesRegex(WorkerHeartbeatFormatError, "duplicate"):
            loads_worker_heartbeat(encoded[:-1] + ', "client_id": "client-01"}')
        payload = heartbeat.to_dict()
        payload["tactical_role"] = "caller"
        with self.assertRaisesRegex(WorkerHeartbeatFormatError, "unknown"):
            loads_worker_heartbeat(json.dumps(payload))

    def test_healthy_worker_is_bound_to_exact_process_and_game_instance(self) -> None:
        self.ledger.publish(_heartbeat())
        supervisor = self._supervisor()

        health = supervisor.inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )

        self.assertEqual(WorkerHealthState.HEALTHY, health.state)
        self.assertTrue(health.dispatch_allowed)
        self.assertEqual(1, health.active_worker_count)
        self.assertEqual(WORKER_ID, health.heartbeat.worker_id)
        permit = self.ledger.inspect_permit(CLIENT_ID)
        self.assertIsNotNone(permit)
        assert permit is not None
        self.assertTrue(permit.allowed)
        self.assertEqual(INSTANCE_ID, permit.instance_id)
        gate = WorkerDispatchGate(
            self.ledger,
            node_id=NODE_ID,
            client_id=CLIENT_ID,
            instance_id=INSTANCE_ID,
            worker_id=WORKER_ID,
            process=self.process,
            clock=lambda: 1_001.5,
        )
        self.assertTrue(gate.allows_dispatch())
        self.assertFalse(gate.is_set())

    def test_worker_record_replace_retries_transient_reader_lock(self) -> None:
        self.ledger.publish(_heartbeat())
        original_replace = Path.replace
        attempts = 0

        def intermittently_locked(source: Path, target: Path) -> Path:
            nonlocal attempts
            if source.name.startswith(".dispatch."):
                attempts += 1
                if attempts < 3:
                    raise PermissionError(13, "record is transiently locked", str(target))
            return original_replace(source, target)

        with (
            patch.object(Path, "replace", intermittently_locked),
            patch("shadowbane_lab.manager.worker.sleep") as retry_sleep,
        ):
            health = self._supervisor().inspect(
                CLIENT_ID,
                instance_id=INSTANCE_ID,
                lifecycle_dispatch_enabled=True,
            )

        self.assertTrue(health.dispatch_allowed)
        self.assertEqual(3, attempts)
        self.assertEqual([0.01, 0.02], [call.args[0] for call in retry_sleep.call_args_list])
        permit = self.ledger.inspect_permit(CLIENT_ID)
        self.assertIsNotNone(permit)
        assert permit is not None
        self.assertTrue(permit.allowed)

    def test_lifecycle_pause_blocks_dispatch_without_hiding_worker_health(self) -> None:
        self.ledger.publish(_heartbeat())

        health = self._supervisor().inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=False,
        )

        self.assertEqual(WorkerHealthState.HEALTHY, health.state)
        self.assertFalse(health.dispatch_allowed)
        self.assertIn("lifecycle", health.detail)
        permit = self.ledger.inspect_permit(CLIENT_ID)
        self.assertIsNotNone(permit)
        assert permit is not None
        self.assertFalse(permit.allowed)

    def test_dispatch_permit_expires_and_rejects_near_match_identities(self) -> None:
        self.ledger.publish(_heartbeat())
        self._supervisor().inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )
        now = [1_001.5]
        exact_gate = WorkerDispatchGate(
            self.ledger,
            node_id=NODE_ID,
            client_id=CLIENT_ID,
            instance_id=INSTANCE_ID,
            worker_id=WORKER_ID,
            process=self.process,
            clock=lambda: now[0],
        )
        wrong_worker = WorkerDispatchGate(
            self.ledger,
            node_id=NODE_ID,
            client_id=CLIENT_ID,
            instance_id=INSTANCE_ID,
            worker_id="worker-abcdefabcdefabcdefabcdefabcdefab",
            process=self.process,
            clock=lambda: now[0],
        )

        self.assertTrue(exact_gate.allows_dispatch())
        self.assertFalse(wrong_worker.allows_dispatch())
        now[0] = 1_003.0
        self.assertFalse(exact_gate.allows_dispatch())

    def test_synchronous_revocation_blocks_a_previously_allowed_worker(self) -> None:
        self.ledger.publish(_heartbeat())
        supervisor = self._supervisor()
        supervisor.inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )
        gate = WorkerDispatchGate(
            self.ledger,
            node_id=NODE_ID,
            client_id=CLIENT_ID,
            instance_id=INSTANCE_ID,
            worker_id=WORKER_ID,
            process=self.process,
            clock=lambda: 1_001.1,
        )
        self.assertTrue(gate.allows_dispatch())

        supervisor.revoke(CLIENT_ID, reason="operator paused this slot")

        self.assertFalse(gate.allows_dispatch())
        self.assertTrue(gate.is_set())

    def test_corrupt_dispatch_permit_is_a_dynamic_stop(self) -> None:
        self.ledger.publish(_heartbeat())
        self._supervisor().inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )
        gate = WorkerDispatchGate(
            self.ledger,
            node_id=NODE_ID,
            client_id=CLIENT_ID,
            instance_id=INSTANCE_ID,
            worker_id=WORKER_ID,
            process=self.process,
            clock=lambda: 1_001.1,
        )
        permit_path = self.ledger.root / NODE_ID / CLIENT_ID / "dispatch.permit"
        permit_path.write_text("{", encoding="utf-8")

        self.assertFalse(gate.allows_dispatch())
        self.assertTrue(gate.is_set())

    def test_missing_and_unbound_slots_fail_closed(self) -> None:
        supervisor = self._supervisor()

        missing = supervisor.inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )
        unbound = supervisor.inspect(
            CLIENT_ID,
            instance_id=None,
            lifecycle_dispatch_enabled=False,
        )

        self.assertEqual(WorkerHealthState.MISSING, missing.state)
        self.assertEqual(WorkerHealthState.UNBOUND, unbound.state)
        self.assertFalse(missing.dispatch_allowed)
        self.assertFalse(unbound.dispatch_allowed)

    def test_stale_future_and_exited_process_lifetimes_fail_closed(self) -> None:
        self.ledger.publish(_heartbeat())
        stale = self._supervisor(now=1_006.0).inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )
        exited = WorkerSupervisor(
            self.ledger,
            _ProcessInspector(),
            clock=lambda: 1_001.0,
        ).inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )
        self.ledger.publish(_heartbeat(sequence=2, observed_at=1_010.0))
        future = self._supervisor(now=1_001.0).inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )
        reused_pid = self._supervisor(
            ProcessLifetimeSnapshot(
                process_id=101,
                process_started_at_100ns=PROCESS_STARTED_AT + 99,
            ),
            now=1_011.0,
        ).inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )

        self.assertEqual(WorkerHealthState.STALE, stale.state)
        self.assertEqual(WorkerHealthState.EXITED, exited.state)
        self.assertEqual(WorkerHealthState.INVALID, future.state)
        self.assertEqual(WorkerHealthState.EXITED, reused_pid.state)

    @unittest.skipUnless(os.name == "nt", "UNC roots are a Windows boundary")
    def test_shared_unc_heartbeat_roots_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "node-local"):
            WorkerHeartbeatLedger(_manifest(), r"\\VBOXSVR\codexdiag\workers")

    def test_worker_bound_to_replaced_game_instance_fails_closed(self) -> None:
        self.ledger.publish(_heartbeat(instance_id="client-deadbeef"))

        health = self._supervisor().inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )

        self.assertEqual(WorkerHealthState.IDENTITY_MISMATCH, health.state)
        self.assertFalse(health.dispatch_allowed)

    def test_multiple_live_worker_lifetimes_are_a_conflict(self) -> None:
        second_process = ProcessLifetimeSnapshot(
            process_id=202,
            process_started_at_100ns=PROCESS_STARTED_AT + 1,
        )
        self.ledger.publish(_heartbeat())
        self.ledger.publish(
            _heartbeat(
                worker_id="worker-abcdefabcdefabcdefabcdefabcdefab",
                process_id=202,
                process_started_at_100ns=PROCESS_STARTED_AT + 1,
            )
        )

        health = self._supervisor(self.process, second_process).inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )

        self.assertEqual(WorkerHealthState.CONFLICT, health.state)
        self.assertEqual(2, health.active_worker_count)
        self.assertFalse(health.dispatch_allowed)

    def test_corrupt_record_blocks_dispatch_even_beside_valid_record(self) -> None:
        self.ledger.publish(_heartbeat())
        directory = self.ledger.root / NODE_ID / CLIENT_ID
        (directory / "worker-bad.json").write_text("{}", encoding="utf-8")

        health = self._supervisor().inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )

        self.assertEqual(WorkerHealthState.INVALID, health.state)
        self.assertFalse(health.dispatch_allowed)
        self.assertEqual(1, len(health.issues))

    def test_sequence_regression_and_emergency_stop_reset_are_rejected(self) -> None:
        self.ledger.publish(_heartbeat(sequence=2, observed_at=1_001.0))
        supervisor = self._supervisor(now=1_002.0)
        first = supervisor.inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )
        self.ledger.publish(_heartbeat(sequence=1, observed_at=1_002.0))
        replay = supervisor.inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )
        self.ledger.publish(
            _heartbeat(
                sequence=3,
                observed_at=1_003.0,
                dispatch_ready=False,
                emergency_stop=True,
            )
        )
        tripped = self._supervisor(now=1_004.0)
        self.assertEqual(
            WorkerHealthState.EMERGENCY_STOPPED,
            tripped.inspect(
                CLIENT_ID,
                instance_id=INSTANCE_ID,
                lifecycle_dispatch_enabled=True,
            ).state,
        )
        self.ledger.publish(_heartbeat(sequence=4, observed_at=1_004.0))
        cleared = tripped.inspect(
            CLIENT_ID,
            instance_id=INSTANCE_ID,
            lifecycle_dispatch_enabled=True,
        )

        self.assertEqual(WorkerHealthState.HEALTHY, first.state)
        self.assertEqual(WorkerHealthState.INVALID, replay.state)
        self.assertEqual(WorkerHealthState.INVALID, cleared.state)

    def test_publisher_sequences_atomically_and_latches_emergency_stop(self) -> None:
        publisher = WorkerHeartbeatPublisher(
            self.ledger,
            node_id=NODE_ID,
            client_id=CLIENT_ID,
            instance_id=INSTANCE_ID,
            process=self.process,
            clock=lambda: 1_000.0,
        )

        first = publisher.publish(WorkerRuntimeState.STARTING)
        tripped = publisher.publish(
            WorkerRuntimeState.RUNNING,
            dispatch_ready=True,
            emergency_stop=True,
        )
        latched = publisher.publish(WorkerRuntimeState.RUNNING, dispatch_ready=True)
        final = publisher.close(detail="worker shutdown complete")

        self.assertEqual(
            (1, 2, 3, 4), tuple(item.sequence for item in (first, tripped, latched, final))
        )
        self.assertLess(first.observed_at, tripped.observed_at)
        self.assertTrue(tripped.emergency_stop)
        self.assertTrue(latched.emergency_stop)
        self.assertFalse(latched.dispatch_ready)
        self.assertEqual(WorkerRuntimeState.STOPPED, final.runtime_state)


if __name__ == "__main__":
    unittest.main()
