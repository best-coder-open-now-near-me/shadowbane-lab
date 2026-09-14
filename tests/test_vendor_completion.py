import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped, fill_available_slots
from shadowbane_lab.client_extension.vendor_completion import keep_completed_batch
from shadowbane_lab.client_extension.vendor_wire import IN_FLIGHT, READY, Outcome, Slot
from tests.test_vendor_batch import MultipleSession, Session, receipt


class KeepSession:
    def __init__(self, created, journal, behavior="normal"):
        self.identity = created.identity
        self.state = replace(
            created.state,
            inventory=900,
            slots=tuple(replace(s, state=2) for s in created.state.slots),
        )
        self.journal = journal
        self.behavior = behavior
        self.calls = []
        self.pending = None
        self.transition = (0, None)

    def inspect(self):
        if self.pending:
            item, key = self.pending
            if self.behavior == "logout":
                return receipt(replace(self.state, scene=2), flags=0)
            slots = tuple(Slot(s.entry) if s.item == item else s for s in self.state.slots)
            self.state = replace(self.state, slots=slots, revision=self.state.revision + 1)
            if self.behavior == "queue_only":
                return receipt(self.state, flags=IN_FLIGHT)
            if self.behavior == "external_item":
                self.state = replace(self.state, slots=self.state.slots + (Slot(800, 999, 1),))
            self.transition = (item, key)
            self.pending = None
        return receipt(
            self.state, flags=READY, item=self.transition[0], transition=self.transition[1]
        )

    def keep(self, expected, item, key):
        saved = json.loads(self.journal.read_text())
        assert saved["requests"][-1]["state"] == "prepared"
        assert saved["requests"][-1]["request_key"] == key
        assert saved["requests"][-1]["item_id"] == item
        assert expected == self.state
        self.calls.append(item)
        if self.behavior == "lost_response":
            raise OSError("lost response")
        if self.behavior == "rejected":
            return receipt(self.state, key, Outcome.STALE, 0)
        self.pending = (item, key)
        return receipt(self.state, key, Outcome.SUBMITTED, IN_FLIGHT)


class VendorCompletionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.batch = self.root / "batch.json"
        created = Session(self.batch)
        self.created = fill_available_slots(created, self.batch, 2517204)
        self.journal = self.root / "keep.json"
        self.session = KeepSession(created, self.journal)
        self.tick = 0.0

    def sleep(self, seconds):
        self.tick += seconds

    def run_keep(self, **kwargs):
        return keep_completed_batch(
            self.session,
            self.batch,
            self.journal,
            clock=lambda: self.tick,
            sleeper=self.sleep,
            acceptance_timeout=0.3,
            **kwargs,
        )

    def test_unknowns_kept_once_with_inventory_confirmation_and_durable_requests(self):
        result = self.run_keep()
        self.assertEqual("complete", result["state"])
        self.assertEqual(self.created["items"], result["kept"])
        self.assertEqual(self.created["items"], self.session.calls)
        self.assertTrue(all(r["state"] == "observed_in_inventory" for r in result["requests"]))
        self.assertTrue(
            all(d["reason"] == "unknown_affix_preserved" for d in result["decisions"].values())
        )
        with self.assertRaises(VendorBatchStopped):
            self.run_keep()
        self.assertEqual(2, len(self.session.calls))

    def test_hidden_inventory_or_cooking_item_prevents_submission(self):
        for hidden in (True, False):
            original = self.session.state
            self.session.state = (
                replace(original, inventory=0)
                if hidden
                else replace(original, slots=tuple(replace(s, state=1) for s in original.slots))
            )
            with self.subTest(hidden=hidden), self.assertRaises(VendorBatchStopped):
                self.run_keep()
            self.assertFalse(self.journal.exists())
            self.assertEqual([], self.session.calls)
            self.session.state = original

    def test_lost_response_does_not_retry_or_keep_next_item(self):
        self.session.behavior = "lost_response"
        with self.assertRaises(OSError):
            self.run_keep()
        self.assertEqual(1, len(self.session.calls))
        self.assertEqual("uncertain", json.loads(self.journal.read_text())["state"])
        with self.assertRaises(VendorBatchStopped):
            self.run_keep()

    def test_queue_removal_without_inventory_never_counts_as_success(self):
        self.session.behavior = "queue_only"
        with self.assertRaises(VendorBatchStopped):
            self.run_keep()
        self.assertEqual([], json.loads(self.journal.read_text())["kept"])
        self.assertEqual(1, len(self.session.calls))

    def test_logout_stops_without_next_keep(self):
        self.session.behavior = "logout"
        with self.assertRaises(VendorBatchStopped):
            self.run_keep()
        self.assertEqual(1, len(self.session.calls))

    def test_external_item_change_stops_without_next_keep(self):
        self.session.behavior = "external_item"
        with self.assertRaises(VendorBatchStopped):
            self.run_keep()
        self.assertEqual(1, len(self.session.calls))

    def test_rejection_is_recorded_without_retry(self):
        self.session.behavior = "rejected"
        with self.assertRaises(VendorBatchStopped):
            self.run_keep()
        self.assertEqual("rejected", json.loads(self.journal.read_text())["requests"][0]["state"])
        self.assertEqual(1, len(self.session.calls))

    def test_cancel_before_send_and_after_send(self):
        result = self.run_keep(cancelled=lambda: True)
        self.assertEqual("cancelled", result["state"])
        self.assertEqual([], self.session.calls)

    def test_cancel_after_send_does_not_claim_inventory(self):
        result = self.run_keep(cancelled=lambda: bool(self.session.calls))
        self.assertEqual("cancelled_pending", result["state"])
        self.assertEqual([], result["kept"])

    def test_disk_failure_prevents_unrecorded_keep(self):
        with (
            patch(
                "shadowbane_lab.client_extension.vendor_completion.publish_atomic_record",
                side_effect=OSError("disk full"),
            ),
            self.assertRaises(OSError),
        ):
            self.run_keep()
        self.assertEqual([], self.session.calls)

    def test_other_client_batch_is_rejected(self):
        data = json.loads(self.batch.read_text())
        data["process_creation_filetime_utc"] += 1
        self.batch.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.run_keep()
        self.assertEqual([], self.session.calls)

    def test_confirmed_exclusion_stays_in_production_while_unknown_is_kept(self):
        items = self.created["items"]
        with patch(
            "shadowbane_lab.client_extension.vendor_completion._decisions",
            return_value={
                items[0]: {"disposition": "exclude", "reason": "confirmed_low_tier"},
                items[1]: {"disposition": "keep", "reason": "unknown_affix_preserved"},
            },
        ):
            result = self.run_keep()
        self.assertEqual([items[0]], result["excluded"])
        self.assertEqual([items[1]], result["kept"])
        self.assertTrue(any(s.item == items[0] for s in self.session.state.slots))

    def completion_record(self):
        from tests.test_crafting_assessment import result

        r = result()
        r.update(
            process_id=self.session.identity.process_id,
            process_creation_filetime_utc=self.session.identity.creation_filetime_utc,
        )
        r["message"]["vendor"] = {"object_id": 2517204, "object_type": 42}
        r["message"]["roll"]["item"] = {"object_id": self.created["items"][0], "object_type": 40}
        return r

    def test_bound_native_completion_uses_real_affix_assessment(self):
        capture = self.root / "capture.jsonl"
        capture.write_text(json.dumps(self.completion_record()) + "\n")
        result = self.run_keep(capture=capture)
        self.assertEqual(3, result["decisions"][self.created["items"][0]]["suffix"]["tier"])
        self.assertEqual(2, len(result["kept"]))

    def test_foreign_evidence_rejected_before_any_keep(self):
        capture = self.root / "capture.jsonl"
        r = self.completion_record()
        r["process_creation_filetime_utc"] += 1
        capture.write_text(json.dumps(r) + "\n")
        with self.assertRaises(ValueError):
            self.run_keep(capture=capture)
        self.assertEqual([], self.session.calls)

    def test_conflicting_affix_evidence_rejected_before_keep(self):
        capture = self.root / "capture.jsonl"
        a = self.completion_record()
        b = self.completion_record()
        b["message"]["suffix_token"] = 423138203
        capture.write_text(json.dumps(a) + "\n" + json.dumps(b) + "\n")
        with self.assertRaises(ValueError):
            self.run_keep(capture=capture)
        self.assertEqual([], self.session.calls)

    def test_cooking_capture_does_not_turn_hidden_affixes_into_absence(self):
        capture = self.root / "capture.jsonl"
        r = self.completion_record()
        r["message"].update(prefix_token=0, suffix_token=0)
        r["message"]["roll"].update(in_progress=1, complete_flag=0, seconds_remaining=50)
        capture.write_text(json.dumps(r) + "\n")
        result = self.run_keep(capture=capture)
        self.assertEqual(
            "unknown_affix_preserved", result["decisions"][self.created["items"][0]]["reason"]
        )


class MultipleCompletionTests(unittest.TestCase):
    def test_complete_multiple_request_keeps_every_unknown_once(self):
        with tempfile.TemporaryDirectory() as d:
            batch, journal = Path(d) / "batch.json", Path(d) / "keep.json"
            created = MultipleSession(batch)
            record = fill_available_slots(created, batch, 2517204, sleeper=lambda _: None)
            session = KeepSession(created, journal)
            result = keep_completed_batch(session, batch, journal)
            self.assertEqual(record["items"], result["kept"])
            self.assertEqual(record["items"], session.calls)
            self.assertEqual(3, session.state.free_slots)

    def test_malformed_multiple_receipts_never_authorize_keep(self):
        import copy
        with tempfile.TemporaryDirectory() as d:
            batch, journal = Path(d) / "batch.json", Path(d) / "keep.json"
            created = MultipleSession(batch)
            record = fill_available_slots(created, batch, 2517204, sleeper=lambda _: None)
            mutations = (
                lambda r: r["requests"][0].update(expected_item_count=2),
                lambda r: r["requests"][0].update(expected_item_count=True),
                lambda r: r["requests"][0].update(item_ids=[101, 101, 103]),
                lambda r: r["requests"][0].update(item_ids=[101, 102]),
                lambda r: r["requests"][0].update(item_ids=[101, 102, 999]),
                lambda r: r["requests"][0].update(expected_snapshot="bad"),
                lambda r: r["requests"][0].update(state="submitted"),
                lambda r: r.update(schema_version=1),
                lambda r: r["requests"].append(dict(r["requests"][0])),
            )
            for mutation in mutations:
                changed = copy.deepcopy(record)
                mutation(changed)
                batch.write_text(json.dumps(changed))
                session = KeepSession(created, journal)
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    keep_completed_batch(session, batch, journal)
                self.assertEqual([], session.calls)
                self.assertFalse(journal.exists())
