import copy
import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_wire import IN_FLIGHT, READY, Outcome, Slot
from shadowbane_lab.manager.vendor_job import VendorJobStore, run_vendor_job
from tests.test_vendor_batch import MultipleSession, Session, receipt


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


class MultipleJobSession(JobSession, MultipleSession):
    def __init__(self, store):
        JobSession.__init__(self, store)
        self.state = replace(self.state, multiple=1)
        self.close_recipe = True
        self.partial_timeout = False
        self.expected_count = 0
        self.arrivals = 0


class FocusJobSession(JobSession):
    focused = False

    def inspect(self):
        observed = super().inspect()
        return observed if self.focused else replace(observed, flags=observed.flags & ~READY)


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

    def test_multiple_batch_closes_recipe_then_keeps_all_items(self):
        self.session = MultipleJobSession(self.store)
        result = self.run_job()
        self.assertEqual(("complete", 3, 3, 0), (
            result["state"], result["created"], result["kept"], result["excluded"],
        ))
        self.assertEqual(1, len(self.session.calls))
        self.assertEqual(3, len(self.session.keeps))
        self.assertEqual(0, self.session.state.recipe)
        self.assertEqual(3, self.session.state.free_slots)

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

    def test_completed_keep_requires_its_exact_observed_chain(self):
        result = self.run_job()
        directory = self.store.directory(result["job_id"])
        keep_path = directory / "keep.json"
        original = json.loads(keep_path.read_bytes())
        create_bytes = (directory / "create.json").read_bytes()
        calls = (len(self.session.calls), len(self.session.keeps))

        def change_snapshot(record, **changes):
            request = record["requests"][0]
            from shadowbane_lab.client_extension.vendor_wire import Snapshot
            expected = Snapshot.decode(bytes.fromhex(request["expected_snapshot"]))
            request["expected_snapshot"] = replace(expected, **changes).encode().hex()

        mutations = {
            "wrong operation": lambda r: r.update(operation="fill_available_slots"),
            "wrong schema": lambda r: r.update(schema_version=True),
            "different source bytes": lambda r: r.update(source_batch_sha256="0" * 64),
            "different batch": lambda r: r.update(batch_id="12345678-1234-5678-9abc-def012345678"),
            "missing inventory receipt": lambda r: r["requests"].pop(),
            "pending request": lambda r: r["requests"][0].update(state="submitted"),
            "wrong item": lambda r: r["requests"][0].update(item_id=999),
            "duplicate UUID": lambda r: r["requests"][1].update(
                request_key=r["requests"][0]["request_key"]),
            "invalid UUID": lambda r: r["requests"][0].update(request_key="invalid"),
            "missing disposition": lambda r: r["decisions"].pop(str(r["kept"][0])),
            "missing item": lambda r: r["kept"].pop(),
            "duplicate kept item": lambda r: r["kept"].append(r["kept"][0]),
            "overlapping disposition": lambda r: r["excluded"].append(r["kept"][0]),
            "wrong building": lambda r: change_snapshot(r, building=999),
            "missing inventory": lambda r: change_snapshot(r, inventory=0),
            "lost production": lambda r: change_snapshot(r, slots=(Slot(600), Slot(700))),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(original)
                mutate(changed)
                changed_bytes = json.dumps(changed).encode()
                keep_path.write_bytes(changed_bytes)
                result.update(state="running", kept=0)
                self.store.save(result)
                with self.assertRaises(VendorBatchStopped):
                    self.run_job(resume=True)
                self.assertEqual("review", self.store.current()["state"])
                self.assertEqual(calls, (len(self.session.calls), len(self.session.keeps)))
                self.assertEqual(changed_bytes, keep_path.read_bytes())
                self.assertEqual(create_bytes, (directory / "create.json").read_bytes())

    def test_orphan_keep_and_changed_create_never_count_as_finished(self):
        result = self.run_job()
        directory = self.store.directory(result["job_id"])
        create_path, keep_path = directory / "create.json", directory / "keep.json"
        original_create, original_keep = create_path.read_bytes(), keep_path.read_bytes()
        calls = (len(self.session.calls), len(self.session.keeps))
        for source in (None, original_create + b" "):
            with self.subTest(source_exists=source is not None):
                if source is None:
                    create_path.unlink()
                else:
                    create_path.write_bytes(source)
                result.update(state="running", kept=0)
                self.store.save(result)
                with self.assertRaises(VendorBatchStopped):
                    self.run_job(resume=True)
                self.assertEqual("review", self.store.current()["state"])
                self.assertEqual(calls, (len(self.session.calls), len(self.session.keeps)))
                self.assertEqual(original_keep, keep_path.read_bytes())

    def test_create_from_another_building_cannot_complete_same_vendor_job(self):
        from shadowbane_lab.client_extension.vendor_wire import Snapshot
        result = self.run_job()
        initial = Snapshot.decode(bytes.fromhex(result["initial_snapshot"]))
        result.update(
            state="running", initial_snapshot=replace(initial, building=999).encode().hex(),
        )
        self.store.save(result)
        with self.assertRaises(VendorBatchStopped):
            self.run_job(resume=True)
        self.assertEqual("review", self.store.current()["state"])
        self.assertEqual((2, 2), (len(self.session.calls), len(self.session.keeps)))

    def test_multiple_completed_recovery_restores_progress_without_native_calls(self):
        self.session = MultipleJobSession(self.store)
        result = self.run_job()
        result.update(state="running", phase="filling", created=0, kept=0)
        self.store.save(result)
        from shadowbane_lab.manager import vendor_job
        original_read = vendor_job._read_record
        with (
            patch.object(vendor_job, "_read_record", wraps=original_read) as read,
            patch.object(
                self.session, "inspect", side_effect=AssertionError("unexpected native call"),
            ),
        ):
            recovered = self.run_job(resume=True)
        self.assertEqual(("complete", "keeping", 3, 3), (
            recovered["state"], recovered["phase"], recovered["created"], recovered["kept"],
        ))
        for name in ("create.json", "keep.json"):
            self.assertEqual(
                1, sum(Path(call.args[0]).name == name for call in read.call_args_list),
            )
        self.assertEqual((1, 3), (len(self.session.calls), len(self.session.keeps)))

    def test_completed_exclusion_recovery_preserves_its_receipts(self):
        with patch("shadowbane_lab.client_extension.vendor_completion._decisions", return_value={
            101: {"disposition": "exclude", "reason": "confirmed_low_tier"},
            102: {"disposition": "keep", "reason": "unknown_affix_preserved"},
        }):
            result = self.run_job()
        result.update(state="running", kept=0, excluded=0)
        self.store.save(result)
        recovered = self.run_job(resume=True)
        self.assertEqual((1, 1), (recovered["kept"], recovered["excluded"]))
        self.assertEqual([102], self.session.keeps)
        self.assertTrue(any(slot.item == 101 for slot in self.session.state.slots))

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

    def test_deep_windows_runtime_paths_support_atomic_jobs_and_receipts(self):
        self.store = VendorJobStore(
            Path(self.temp.name) / ("runtime-" + "r" * 85),
            "node-" + "n" * 65, "client-" + "c" * 65, "client-" + "i" * 64,
        )
        cleanup_root = self.store.root.parents[3]
        normal_root = str(cleanup_root).removeprefix(chr(92) * 2 + "?" + chr(92))
        # Resolve the temp root too: Windows CI may expose its short 8.3 alias.
        self.assertTrue(Path(normal_root).is_relative_to(Path(self.temp.name).resolve()))
        self.addCleanup(lambda: shutil.rmtree(cleanup_root, ignore_errors=False))
        self.session = JobSession(self.store)
        result = self.run_job()
        self.assertEqual("complete", result["state"])
        self.assertEqual(2, result["kept"])
        self.assertGreater(len(str(self.store.directory(result["job_id"]) / "create.json")), 260)

    def test_start_waits_for_game_without_creating_items_or_requiring_resume(self):
        self.session = FocusJobSession(self.store)
        waits = []
        def sleep(seconds):
            self.now += seconds
            job = self.store.current()
            if job["state"] == "attention":
                self.assertFalse(self.session.calls)
                self.assertFalse(self.session.keeps)
                waits.append(job["job_id"])
                if len(waits) == 6:
                    self.session.focused = True
            self.session.finish_cooking()
        self.sleep = sleep
        result = self.run_job()
        self.assertEqual("complete", result["state"])
        self.assertEqual(6, len(waits))
        self.assertEqual({result["job_id"]}, set(waits))
        self.assertEqual((2, 2), (len(self.session.calls), len(self.session.keeps)))

    def test_focus_loss_after_create_confirms_receipt_before_waiting(self):
        self.session = FocusJobSession(self.store)
        self.session.focused = True
        def lose_focus():
            if len(self.session.calls) == 1:
                self.session.focused = False
        self.session.after_create = lose_focus
        waits = []
        def sleep(seconds):
            self.now += seconds
            job = self.store.current()
            if job["state"] == "attention":
                batch_path = self.store.directory(job["job_id"]) / "create.json"
                batch = json.loads(batch_path.read_text())
                self.assertEqual(["observed"], [r["state"] for r in batch["requests"]])
                self.assertEqual(1, len(self.session.calls))
                waits.append(True)
                self.session.focused = True
            self.session.finish_cooking()
        self.sleep = sleep
        self.assertEqual("complete", self.run_job()["state"])
        self.assertEqual([True], waits)
        self.assertEqual(2, len(self.session.calls))

    def test_focus_loss_after_keep_confirms_inventory_before_next_keep(self):
        self.session = FocusJobSession(self.store)
        self.session.focused = True
        original = self.session.keep
        def keep(expected, item, key):
            result = original(expected, item, key)
            if len(self.session.keeps) == 1:
                self.session.focused = False
            return result
        self.session.keep = keep
        waits = []
        def sleep(seconds):
            self.now += seconds
            job = self.store.current()
            if job["state"] == "attention":
                kept = json.loads((self.store.directory(job["job_id"]) / "keep.json").read_text())
                self.assertEqual(["observed_in_inventory"], [r["state"] for r in kept["requests"]])
                self.assertEqual(1, len(self.session.keeps))
                waits.append(True)
                self.session.focused = True
            self.session.finish_cooking()
        self.sleep = sleep
        self.assertEqual("complete", self.run_job()["state"])
        self.assertEqual([True], waits)
        self.assertEqual(2, len(self.session.keeps))

    def test_stop_or_owner_change_while_waiting_never_sends_create(self):
        for mode in ("stop", "owner", "timeout", "permit"):
            with self.subTest(mode=mode):
                self.setUp()
                self.session = FocusJobSession(self.store)
                def sleep(seconds, mode=mode):
                    self.now += seconds
                    if mode == "stop":
                        self.store.request(self.store.current()["job_id"], "stop")
                    elif mode == "owner":
                        self.session.state = replace(self.session.state, vendor=999)
                    elif mode == "timeout":
                        self.now = 3601
                    else:
                        self.cancel = True
                self.sleep = sleep
                if mode in {"stop", "permit"}:
                    self.assertEqual(
                        "stopped" if mode == "stop" else "paused", self.run_job()["state"],
                    )
                else:
                    with self.assertRaises(VendorBatchStopped):
                        self.run_job()
                self.assertFalse(self.session.calls)
                self.assertFalse(self.session.keeps)
