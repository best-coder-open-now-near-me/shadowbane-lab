import json
import tempfile
import unittest

from shadowbane_lab.manager import parse_manager_manifest
from shadowbane_lab.manager.operation import (
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationLedgerError,
    WorkerOperationReceipt,
    WorkerOperationState,
    WorkerTravelDestination,
    loads_worker_operation,
    loads_worker_operation_receipt,
    new_worker_operation,
)
from shadowbane_lab.manager.worker import WorkerDispatchPermit, WorkerHealthState

NODE_ID = "gaming-pc-east"
CLIENT_ID = "client-01"
INSTANCE_ID = "instance-101"
WORKER_ID = "worker-0123456789abcdef0123456789abcdef"
WORKER_PROCESS_ID = 9001
WORKER_PROCESS_STARTED = 133_700_000_000_009_001


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


def _permit() -> WorkerDispatchPermit:
    return WorkerDispatchPermit(
        node_id=NODE_ID,
        client_id=CLIENT_ID,
        instance_id=INSTANCE_ID,
        worker_id=WORKER_ID,
        process_id=WORKER_PROCESS_ID,
        process_started_at_100ns=WORKER_PROCESS_STARTED,
        heartbeat_sequence=4,
        health_state=WorkerHealthState.HEALTHY,
        allowed=True,
        issued_at=100.0,
        expires_at=102.0,
        reason="exact worker is healthy",
    )


class WorkerOperationContractTests(unittest.TestCase):
    def test_operation_and_receipt_strictly_round_trip(self) -> None:
        operation = new_worker_operation(
            _permit(),
            WorkerOperationKind.TRAVEL,
            "/go 120000 60000",
            destination=WorkerTravelDestination(120_000.0, 60_000.0, 8.0),
            now=100.0,
            operation_id="operation-0123456789abcdef0123456789abcdef",
        )
        receipt = WorkerOperationReceipt.for_operation(
            operation,
            WorkerOperationState.ACCEPTED,
            observed_at=100.25,
            detail="accepted by exact worker",
        )

        self.assertEqual(operation, loads_worker_operation(json.dumps(operation.to_dict())))
        self.assertEqual(
            receipt,
            loads_worker_operation_receipt(json.dumps(receipt.to_dict())),
        )
        with self.assertRaisesRegex(ValueError, "duplicate field"):
            loads_worker_operation(
                json.dumps(operation.to_dict())[:-1] + ', "client_id": "client-01"}'
            )

    def test_submit_is_idempotent_only_for_identical_deduplication_content(self) -> None:
        operation = new_worker_operation(
            _permit(),
            WorkerOperationKind.PVE,
            "/pve",
            now=100.0,
            operation_id="operation-11111111111111111111111111111111",
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerOperationLedger(_manifest(), directory)

            first = ledger.submit(operation)
            duplicate = ledger.submit(operation)
            conflicting = new_worker_operation(
                _permit(),
                WorkerOperationKind.STOP,
                "/stop",
                now=100.0,
                operation_id="operation-22222222222222222222222222222222",
                deduplication_id=operation.deduplication_id,
            )
            with self.assertRaisesRegex(WorkerOperationLedgerError, "different immutable"):
                ledger.submit(conflicting)

        self.assertFalse(first.duplicate)
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(operation, duplicate.operation)

    def test_control_operations_precede_travel_and_expired_work_is_terminal(self) -> None:
        travel = new_worker_operation(
            _permit(),
            WorkerOperationKind.TRAVEL,
            "/go 1 2",
            destination=WorkerTravelDestination(1.0, 2.0),
            now=100.0,
            ttl_seconds=1.0,
            operation_id="operation-33333333333333333333333333333333",
        )
        stop = new_worker_operation(
            _permit(),
            WorkerOperationKind.STOP,
            "/stop",
            now=100.5,
            operation_id="operation-44444444444444444444444444444444",
        )
        cancel = new_worker_operation(
            _permit(),
            WorkerOperationKind.CANCEL,
            "physical-client-interaction",
            now=100.25,
            operation_id="operation-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerOperationLedger(_manifest(), directory)
            ledger.submit(travel)
            ledger.submit(cancel)
            ledger.submit(stop)

            pending = ledger.pending_for(
                client_id=CLIENT_ID,
                instance_id=INSTANCE_ID,
                worker_id=WORKER_ID,
                worker_process_id=WORKER_PROCESS_ID,
                worker_process_started_at_100ns=WORKER_PROCESS_STARTED,
                now=100.75,
            )
            self.assertEqual([stop, cancel, travel], list(pending))

            remaining = ledger.pending_for(
                client_id=CLIENT_ID,
                instance_id=INSTANCE_ID,
                worker_id=WORKER_ID,
                worker_process_id=WORKER_PROCESS_ID,
                worker_process_started_at_100ns=WORKER_PROCESS_STARTED,
                now=101.5,
            )
            receipt = ledger.inspect_receipt(CLIENT_ID, travel.operation_id)

        self.assertEqual((stop, cancel), remaining)
        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertEqual(WorkerOperationState.EXPIRED, receipt.state)

    def test_receipt_state_is_monotonic_and_terminal_is_immutable(self) -> None:
        operation = new_worker_operation(
            _permit(),
            WorkerOperationKind.PVE,
            "/pve",
            now=100.0,
            operation_id="operation-55555555555555555555555555555555",
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerOperationLedger(_manifest(), directory)
            ledger.submit(operation)
            for state, observed_at in (
                (WorkerOperationState.ACCEPTED, 100.1),
                (WorkerOperationState.ACTIVE, 100.2),
                (WorkerOperationState.SUCCEEDED, 101.0),
            ):
                ledger.publish_receipt(
                    WorkerOperationReceipt.for_operation(
                        operation,
                        state,
                        observed_at=observed_at,
                    )
                )
            with self.assertRaisesRegex(WorkerOperationLedgerError, "terminal"):
                ledger.publish_receipt(
                    WorkerOperationReceipt.for_operation(
                        operation,
                        WorkerOperationState.FAILED,
                        observed_at=102.0,
                    )
                )

            final = ledger.inspect_receipt(CLIENT_ID, operation.operation_id)

        self.assertIsNotNone(final)
        assert final is not None
        self.assertEqual(WorkerOperationState.SUCCEEDED, final.state)

    def test_acknowledgement_wait_is_bounded(self) -> None:
        operation = new_worker_operation(
            _permit(),
            WorkerOperationKind.STOP,
            "/stop",
            now=100.0,
            operation_id="operation-66666666666666666666666666666666",
        )
        ticks = iter((0.0, 0.0, 0.1, 0.2))
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerOperationLedger(_manifest(), directory)
            ledger.submit(operation)

            receipt = ledger.wait_for_acknowledgement(
                operation,
                timeout_seconds=0.2,
                poll_seconds=0.1,
                clock=lambda: next(ticks),
                sleeper=lambda _seconds: None,
            )

        self.assertIsNone(receipt)


if __name__ == "__main__":
    unittest.main()
