import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.manager.operation import (
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationReceipt,
    WorkerOperationState,
    loads_worker_operation,
    new_worker_operation,
)
from shadowbane_lab.manager.vendor_control import (
    ManagerVendorControl,
    VendorWorkerExecutor,
    open_vendor_session,
)
from shadowbane_lab.manager.vendor_job import VendorJobStore
from shadowbane_lab.manager.worker_runtime import ExactClientWorkerBinding
from tests.test_manager_operation import (
    CLIENT_ID,
    INSTANCE_ID,
    NODE_ID,
    WORKER_ID,
    _manifest,
    _permit,
)
from tests.test_manager_vendor_job import JobSession


class VendorControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.permit = _permit()
        self.permits = SimpleNamespace(inspect_permit=lambda client: self.permit)
        self.operations = WorkerOperationLedger(_manifest(), self.root)
        self.control = ManagerVendorControl(
            self.root,
            NODE_ID,
            self.permits,
            self.operations,
            clock=lambda: 100,
        )
        self.store = self.control.store(CLIENT_ID, INSTANCE_ID)
        self.session = JobSession(self.store)
        binding = ExactClientWorkerBinding(CLIENT_ID, INSTANCE_ID, 988, 1234567, 1000, WORKER_ID)
        VendorWorkerExecutor(self.root, NODE_ID, binding).initialize(
            self.permit.worker_id,
            SimpleNamespace(
                process_id=self.permit.process_id,
                process_started_at_100ns=self.permit.process_started_at_100ns,
            ),
        )

    def execute(self, action):
        current = self.store.current()
        return self.control.execute(
            action,
            CLIENT_ID,
            INSTANCE_ID,
            job_id=current["job_id"] if current and action != "vendor-start" else None,
        )

    def test_discovery_uses_same_ledger_and_cannot_overlap(self):
        self.control.execute("vendor-discover", CLIENT_ID, INSTANCE_ID)
        records = self.operations.inspect_slot(CLIENT_ID)
        self.assertEqual("vendor discover", records[0].operation.command)
        self.assertEqual(records[0].operation,
                         loads_worker_operation(json.dumps(records[0].operation.to_dict())))
        with self.assertRaises(VendorBatchStopped):
            self.control.execute("vendor-discover", CLIENT_ID, INSTANCE_ID)
        with self.assertRaises(VendorBatchStopped):
            self.execute("vendor-start")
        self.assertIsNone(self.store.current())

    def test_discovery_requires_matching_new_worker_capability(self):
        path = self.store.root / "city-window-capability.json"
        payload = json.loads(path.read_text())
        payload["worker_id"] = "other-worker"
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(VendorBatchStopped, "city-window capable"):
            self.control.execute("vendor-discover", CLIENT_ID, INSTANCE_ID)
        self.assertFalse(self.operations.inspect_slot(CLIENT_ID))

    def test_discovery_requires_matching_navigation_worker(self):
        path = self.store.root / "vendor-navigation-capability.json"
        payload = json.loads(path.read_text())
        payload["worker_id"] = "other-worker"
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(VendorBatchStopped, "vendor-navigation host"):
            self.control.execute("vendor-discover", CLIENT_ID, INSTANCE_ID)
        self.assertFalse(self.operations.inspect_slot(CLIENT_ID))

    def test_start_uses_exact_ledger_and_duplicate_click_cannot_queue_another_batch(self):
        self.execute("vendor-start")
        records = self.operations.inspect_slot(CLIENT_ID)
        self.assertEqual(1, len(records))
        op = records[0].operation
        self.assertEqual(WorkerOperationKind.VENDOR, op.kind)
        self.assertEqual("vendor start", op.command)
        self.assertEqual(self.permit.worker_id, op.worker_id)
        self.assertEqual(op, loads_worker_operation(json.dumps(op.to_dict())))
        with self.assertRaises(VendorBatchStopped):
            self.execute("vendor-start")
        self.assertEqual(1, len(self.operations.inspect_slot(CLIENT_ID)))

    def test_wrong_instance_expired_and_denied_permits_prevent_start(self):
        original = self.permit
        for permit in (
            replace(original, instance_id="different"),
            replace(original, issued_at=97, expires_at=99),
            replace(original, allowed=False),
            None,
        ):
            with self.subTest(permit=permit):
                self.permit = permit
                with self.assertRaises(VendorBatchStopped):
                    self.execute("vendor-start")
        self.assertEqual((), self.operations.inspect_slot(CLIENT_ID))

    def test_older_worker_or_stale_capability_never_receives_vendor_command(self):
        path = self.store.root / "worker-capability.json"
        path.unlink()
        with self.assertRaises(VendorBatchStopped):
            self.execute("vendor-start")
        path.write_text("{}")
        with self.assertRaises(VendorBatchStopped):
            self.execute("vendor-start")
        self.assertEqual((), self.operations.inspect_slot(CLIENT_ID))

    def test_existing_travel_blocks_start_and_resume(self):
        op = new_worker_operation(self.permit, WorkerOperationKind.TRAVEL, "/go", now=100)
        self.operations.submit(op)
        with self.assertRaises(VendorBatchStopped):
            self.execute("vendor-start")
        self.store.begin(self.session, 1000, 100)
        with self.assertRaises(VendorBatchStopped):
            self.execute("vendor-resume")

    def test_active_pause_resume_updates_control_without_second_operation(self):
        self.execute("vendor-start")
        op = self.operations.inspect_slot(CLIENT_ID)[0].operation
        self.operations.publish_receipt(
            WorkerOperationReceipt.for_operation(
                op,
                WorkerOperationState.ACTIVE,
                observed_at=100,
            )
        )
        record = self.store.begin(self.session, 1000, 100)
        self.execute("vendor-pause")
        self.assertEqual("pause", self.store.control(record["job_id"]))
        self.execute("vendor-resume")
        self.assertEqual("run", self.store.control(record["job_id"]))
        self.assertEqual(1, len(self.operations.inspect_slot(CLIENT_ID)))

    def test_resume_after_worker_exit_targets_current_job_explicitly(self):
        record = self.store.begin(self.session, 1000, 100)
        record.update(state="paused", phase="waiting")
        self.store.save(record)
        self.execute("vendor-resume")
        op = self.operations.inspect_slot(CLIENT_ID)[0].operation
        self.assertEqual("vendor resume " + record["job_id"], op.command)

    def test_stop_idle_job_works_without_a_dispatch_permit(self):
        record = self.store.begin(self.session, 1000, 100)
        self.permit = None
        self.execute("vendor-stop")
        self.assertEqual("stopped", self.store.current()["state"])
        self.assertEqual("stop", self.store.control(record["job_id"]))
        self.assertEqual((), self.operations.inspect_slot(CLIENT_ID))

    def test_idle_stop_preserves_uncertain_journal_as_review(self):
        record = self.store.begin(self.session, 1000, 100)
        path = self.store.directory(record["job_id"]) / "create.json"
        path.write_text(json.dumps({"state": "uncertain"}))
        self.execute("vendor-stop")
        self.assertEqual("review", self.store.current()["state"])
        with self.assertRaises(VendorBatchStopped):
            self.execute("vendor-start")

    def test_stale_dashboard_cannot_pause_a_newer_batch(self):
        self.store.begin(self.session, 1000, 100)
        with self.assertRaises(VendorBatchStopped):
            self.control.execute("vendor-pause", CLIENT_ID, INSTANCE_ID, job_id="a" * 32)
        self.assertEqual("run", self.store.summary()["control"])

    def test_vendor_command_grammar_has_no_path_or_arbitrary_action_escape(self):
        for command in ("vendor junk", "vendor resume ../escape", "vendor start --unlimited"):
            with self.assertRaises(ValueError):
                new_worker_operation(self.permit, WorkerOperationKind.VENDOR, command, now=100)


class VendorExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binding = ExactClientWorkerBinding(
            CLIENT_ID, INSTANCE_ID, 988, 1234567, 1000, WORKER_ID
        )
        self.store = VendorJobStore(self.root, NODE_ID, CLIENT_ID, INSTANCE_ID)
        self.session = JobSession(self.store)
        self.session.close = Mock()
        self.factory = Mock(return_value=self.session)
        self.executor = VendorWorkerExecutor(
            self.root,
            NODE_ID,
            self.binding,
            session_factory=self.factory,
        )
        self.op = new_worker_operation(
            _permit(), WorkerOperationKind.VENDOR, "vendor start", now=100
        )
        self.stop = threading.Event()

    def test_discovery_closes_city_lease_before_navigation_and_closes_on_failure(self):
        city = Mock()
        navigation = Mock()
        city_closed = []

        def open_navigation(binding):
            self.assertEqual(self.binding, binding)
            self.assertEqual([True], city_closed)
            return navigation

        city.close.side_effect = lambda: city_closed.append(True)
        executor = VendorWorkerExecutor(
            self.root, NODE_ID, self.binding, city_session_factory=lambda _: city,
            navigation_session_factory=open_navigation,
        )
        operation = replace(self.op, command="vendor discover")
        with (
            patch("shadowbane_lab.manager.vendor_control.run_discovery",
                  return_value={"state": "complete"}) as nearby,
            patch("shadowbane_lab.manager.vendor_control.run_building_discovery",
                  side_effect=VendorBatchStopped("window requires review")) as buildings,
        ):
            with self.assertRaisesRegex(VendorBatchStopped, "requires review"):
                executor.execute(operation, stop_signal=self.stop)
            nearby.assert_called_once()
            buildings.assert_called_once()
        navigation.close.assert_called_once()
        self.factory.assert_not_called()

    def test_executor_runs_whole_batch_and_always_closes_native_session(self):
        original = self.session.inspect

        def inspect():
            value = original()
            if self.session.state.free_slots == 0:
                self.session.finish_cooking()
            return value

        self.session.inspect = inspect
        result = self.executor.execute(self.op, stop_signal=self.stop)
        self.assertEqual(WorkerOperationState.SUCCEEDED, result.state)
        self.assertEqual(2, len(self.session.calls))
        self.assertEqual(2, len(self.session.keeps))
        self.session.close.assert_called_once()

    def test_revoked_dispatch_and_wrong_worker_never_open_transport(self):
        self.stop.set()
        result = self.executor.execute(self.op, stop_signal=self.stop)
        self.assertEqual(WorkerOperationState.CANCELLED, result.state)
        self.factory.assert_not_called()
        self.stop.clear()
        with self.assertRaises(VendorBatchStopped):
            self.executor.execute(replace(self.op, instance_id="other"), stop_signal=self.stop)
        self.factory.assert_not_called()

    def test_failed_native_call_closes_session_and_keeps_uncertain_job(self):
        self.session.behavior = "exception"
        with self.assertRaises(OSError):
            self.executor.execute(self.op, stop_signal=self.stop)
        self.session.close.assert_called_once()
        self.assertEqual("review", self.store.current()["state"])

    def test_old_resume_cannot_redirect_to_new_current_job(self):
        op = replace(self.op, command="vendor resume " + "a" * 32)
        with self.assertRaises(VendorBatchStopped):
            self.executor.execute(op, stop_signal=self.stop)
        self.factory.assert_not_called()

    def test_live_factory_verifies_build_and_lifetime_before_native_session(self):
        memory = Mock(process_creation_filetime_utc=999, executable_sha256="unknown")
        with (
            patch(
                "shadowbane_lab.manager.vendor_control.WindowsReadOnlyProcessMemory.open_for_process",
                return_value=memory,
            ),
            patch("shadowbane_lab.manager.vendor_control.NativeVendorSession") as native,
        ):
            with self.assertRaises(VendorBatchStopped):
                open_vendor_session(self.binding)
            memory.close.assert_called_once()
            native.assert_not_called()
