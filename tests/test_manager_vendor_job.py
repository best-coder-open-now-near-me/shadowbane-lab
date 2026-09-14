import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_wire import IN_FLIGHT, Outcome, Slot
from shadowbane_lab.manager.vendor_job import VendorJobStore, run_vendor_job
from tests.test_vendor_batch import Session, receipt


class JobSession(Session):
    def __init__(self, store):
        super().__init__(Path("unused"))
        self.store = store
        self.keeps = []
        self.keep_pending = None
        self.renewals = 0
        self.after_create = lambda: None

    def renew_lease(self):
        self.renewals += 1

    def create(self, expected, key):
        self.path = self.store.directory(self.store.current()["job_id"]) / "create.json"
        result = super().create(expected, key)
        self.after_create()
        return result

    def inspect(self):
        if self.keep_pending:
            item, key = self.keep_pending
            self.state = replace(
                self.state,
                slots=tuple(Slot(s.entry) if s.item == item else s for s in self.state.slots),
            )
            self.keep_pending = None
            self.last_transition = (item, key)
        return super().inspect()

    def keep(self, expected, item, key):
        journal = self.store.directory(self.store.current()["job_id"]) / "keep.json"
        record = json.loads(journal.read_text())
        assert record["requests"][-1]["state"] == "prepared"
        assert expected == self.state
        self.keeps.append(item)
        self.keep_pending = (item, key)
        return receipt(expected, key, Outcome.SUBMITTED, IN_FLIGHT)

    def finish_cooking(self):
        self.state = replace(
            self.state,
            inventory=900,
            slots=tuple(replace(s, state=2) if s.item else s for s in self.state.slots),
        )


class VendorJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = VendorJobStore(Path(self.temp.name), "node", "client", "instance")
        self.session = JobSession(self.store)
        self.now = 0
        self.cancel = False

    def sleep(self, seconds):
        self.now += seconds
        self.session.finish_cooking()

    def run_job(self, **kwargs):
        return run_vendor_job(
            self.store,
            self.session,
            1000,
            clock=lambda: self.now,
            sleeper=self.sleep,
            cancelled=lambda: self.cancel,
            **kwargs,
        )

    def test_one_batch_completes_and_preserves_unknowns(self):
        result = self.run_job()
        self.assertEqual(
            ("complete", 2, 2, 0),
            (
                result["state"],
                result["created"],
                result["kept"],
                result["excluded"],
            ),
        )
        self.assertEqual(2, len(self.session.calls))
        self.assertEqual(2, len(self.session.keeps))
        self.assertEqual(2, self.session.state.free_slots)
        summary = self.store.summary()
        self.assertNotIn("initial_snapshot", summary)
        self.assertNotIn("process_id", summary)

    def test_pause_finishes_pending_receipt_then_prevents_next_create(self):
        pauses = []

        def pause():
            if len(self.session.calls) == 1:
                self.store.request(self.store.current()["job_id"], "pause")

        self.session.after_create = pause

        def sleep(seconds):
            self.now += seconds
            current = self.store.current()
            if current["state"] == "paused":
                self.assertEqual(1, len(self.session.calls))
                journal = self.store.directory(current["job_id"]) / "create.json"
                self.assertEqual(
                    "observed", json.loads(journal.read_text())["requests"][-1]["state"]
                )
                pauses.append(True)
                self.store.request(current["job_id"], "run")
            self.session.finish_cooking()

        self.sleep = sleep
        self.assertEqual("complete", self.run_job()["state"])
        self.assertTrue(pauses)
        self.assertGreater(self.session.renewals, 0)

    def test_pending_stop_never_replays(self):
        self.session.after_create = lambda: self.store.request(
            self.store.current()["job_id"], "stop"
        )
        with self.assertRaises(VendorBatchStopped):
            self.run_job()
        self.assertEqual("review", self.store.current()["state"])
        with self.assertRaises(VendorBatchStopped):
            self.run_job(resume=True)
        self.assertEqual(1, len(self.session.calls))
        self.assertEqual([], self.session.keeps)

    def test_permit_loss_while_cooking_can_resume_same_batch_without_create(self):
        def pause(seconds):
            self.cancel = True

        self.sleep = pause
        self.assertEqual("paused", self.run_job()["state"])
        self.assertEqual(2, len(self.session.calls))
        self.cancel = False
        self.session.finish_cooking()
        self.assertEqual("complete", self.run_job(resume=True)["state"])
        self.assertEqual(2, len(self.session.calls))

    def test_hidden_inventory_waits_without_keep(self):
        states = []

        def sleep(seconds):
            self.now += seconds
            current = self.store.current()
            states.append(current["state"])
            self.session.finish_cooking()
            if states.count("inventory") == 0:
                self.session.state = replace(self.session.state, inventory=0)
            if current["state"] == "inventory":
                self.assertFalse(self.session.keeps)
                self.session.state = replace(self.session.state, inventory=900)

        self.sleep = sleep
        self.assertEqual("complete", self.run_job()["state"])
        self.assertIn("inventory", states)

    def test_owner_change_and_timeout_stop_without_keep(self):
        for behavior in ("owner", "timeout"):
            with self.subTest(behavior=behavior):
                self.setUp()

                def sleep(seconds, behavior=behavior):
                    if behavior == "owner":
                        self.session.state = replace(self.session.state, scene=99)
                    else:
                        self.now = 3601

                self.sleep = sleep
                with self.assertRaises(VendorBatchStopped):
                    self.run_job()
                self.assertEqual("review", self.store.current()["state"])
                self.assertFalse(self.session.keeps)

    def test_crash_after_keep_before_job_save_reconciles_without_replay(self):
        result = self.run_job()
        result.update(state="running", kept=0)
        self.store.save(result)
        self.assertEqual(2, self.run_job(resume=True)["kept"])
        self.assertEqual(2, len(self.session.keeps))

    def test_new_start_refuses_unfinished_job_and_foreign_resume(self):
        self.sleep = lambda seconds: setattr(self, "cancel", True)
        self.run_job()
        self.cancel = False
        with self.assertRaises(VendorBatchStopped):
            self.run_job()
        self.session.identity = replace(self.session.identity, creation_filetime_utc=999)
        with self.assertRaises(VendorBatchStopped):
            self.run_job(resume=True)
        self.assertEqual(2, len(self.session.calls))

    def test_start_requires_recipe_and_exact_window(self):
        self.session.state = replace(self.session.state, recipe=0)
        with self.assertRaises(VendorBatchStopped):
            self.run_job()
        self.assertIsNone(self.store.current())
        self.assertFalse(self.session.calls)

    def test_control_cannot_redirect_job_or_undo_stop(self):
        self.sleep = lambda seconds: setattr(self, "cancel", True)
        self.run_job()
        job = self.store.current()
        with self.assertRaises(VendorBatchStopped):
            self.store.request("a" * 32, "run")
        self.store.request(job["job_id"], "stop")
        with self.assertRaises(VendorBatchStopped):
            self.store.request(job["job_id"], "run")
        with self.assertRaises(ValueError):
            self.store.directory("../escape")

    def test_rank_growth_uses_new_slots_within_the_same_fill(self):
        def grow():
            if len(self.session.calls) == 1:
                self.session.state = replace(
                    self.session.state,
                    slots=self.session.state.slots + (Slot(800),),
                )

        self.session.after_create = grow
        result = self.run_job()
        self.assertEqual((3, 3, 3), (result["created"], result["kept"], result["capacity"]))

    def test_permit_revoked_after_journal_flush_prevents_native_send(self):
        from shadowbane_lab.client_extension import vendor_batch

        original = vendor_batch.publish_atomic_record

        def publish(path, data, **kwargs):
            result = original(path, data, **kwargs)
            record = json.loads(data)
            if record.get("requests") and record["requests"][-1]["state"] == "prepared":
                self.cancel = True
            return result

        with patch.object(vendor_batch, "publish_atomic_record", side_effect=publish):
            with self.assertRaises(VendorBatchStopped):
                self.run_job()
        self.assertFalse(self.session.calls)
        self.assertEqual("review", self.store.current()["state"])
