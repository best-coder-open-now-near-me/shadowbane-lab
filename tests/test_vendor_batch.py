import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped, fill_available_slots
from shadowbane_lab.client_extension.vendor_wire import (
    IN_FLIGHT,
    MAGIC,
    READY,
    Command,
    Host,
    Outcome,
    Receipt,
    Slot,
    Snapshot,
    Verb,
)

KEY = "12345678-1234-5678-9abc-def0123456f0"


def snapshot(slots=None):
    slots = (Slot(600), Slot(700)) if slots is None else slots
    return Snapshot(
        scene=1, revision=1, root=100, manager=200, menu=300, recipe=400, hireling=500,
        building=2229645, vendor=2517204, item_template=26990,
        prefix=3362971591, suffix=3362971591, mode=1, table=12, quantity=1, slots=slots,
    )


def receipt(state, request=KEY, outcome=Outcome.OBSERVED, flags=READY, item=0, transition=None):
    return Receipt(request, Host(1, 1, 1), 1000, outcome, flags, state, item, transition)


class Session:
    identity = NativeClientProcessIdentity(988, 1234567)

    def __init__(self, path, *, occupied=False, behavior="normal"):
        self.path = path
        self.state = snapshot((Slot(600, 40, 1), Slot(700))) if occupied else snapshot()
        self.behavior = behavior
        self.calls = []
        self.pending = None
        self.next_item = 100
        self.last_transition = (0, None)
        self.inspections = 0

    def inspect(self):
        self.inspections += 1
        if self.behavior == "wrong_vendor":
            return receipt(replace(self.state, vendor=2517205))
        if self.pending:
            if self.behavior == "timeout":
                return receipt(self.state, flags=IN_FLIGHT)
            if self.behavior == "logout":
                return receipt(Snapshot(), flags=0)
            self.next_item += 1
            slots = list(self.state.slots)
            index = next(i for i, slot in enumerate(slots) if slot.state == 0)
            slots[index] = Slot(slots[index].entry, self.next_item, 1)
            if self.behavior == "two_additions":
                slots = [Slot(s.entry, self.next_item + i, 1) for i, s in enumerate(slots)]
            self.state = replace(self.state, revision=self.state.revision + 1, slots=tuple(slots))
            self.last_transition = (self.next_item, self.pending)
            self.pending = None
        return receipt(self.state, item=self.last_transition[0], transition=self.last_transition[1])

    def create(self, expected, request_key):
        record = json.loads(self.path.read_text())
        assert record["requests"][-1]["state"] == "prepared"
        assert record["requests"][-1]["request_key"] == request_key
        assert record["requests"][-1]["expected_snapshot"] == expected.encode().hex()
        assert expected == self.state
        self.calls.append(request_key)
        if self.behavior == "exception":
            raise OSError("lost response")
        if self.behavior == "rejected":
            return receipt(self.state, request_key, Outcome.STALE, 0)
        self.pending = request_key
        return receipt(self.state, request_key, Outcome.SUBMITTED, IN_FLIGHT)


class MultipleSession(Session):
    """Server confirmations arrive separately; native publishes only a full batch."""
    def __init__(self, path, *, close_recipe=True, partial_timeout=False):
        super().__init__(path)
        self.state = replace(snapshot((Slot(600), Slot(700), Slot(800))), multiple=1)
        self.close_recipe = close_recipe
        self.partial_timeout = partial_timeout
        self.expected_count = 0
        self.arrivals = 0

    def create(self, expected, request_key):
        result = super().create(expected, request_key)
        self.expected_count = expected.free_slots
        self.arrivals = 0
        saved = json.loads(self.path.read_text())
        assert saved["schema_version"] == 2
        assert saved["requests"][-1]["expected_item_count"] == expected.free_slots
        return result

    def inspect(self):
        if not self.pending:
            return receipt(self.state, item=self.last_transition[0],
                           transition=self.last_transition[1])
        if self.partial_timeout and self.arrivals:
            return receipt(self.state, flags=IN_FLIGHT)
        self.next_item += 1
        self.arrivals += 1
        slots = list(self.state.slots)
        index = next(i for i, s in enumerate(slots) if not s.item)
        slots[index] = replace(slots[index], item=self.next_item, state=1)
        self.state = replace(self.state, revision=self.state.revision + 1, slots=tuple(slots))
        if self.close_recipe:
            self.state = replace(self.state, recipe=0, quantity=0, multiple=0)
        if self.arrivals < self.expected_count:
            return receipt(self.state, flags=IN_FLIGHT)
        self.last_transition = (self.next_item, self.pending)
        self.pending = None
        return receipt(self.state, item=self.last_transition[0],
                       transition=self.last_transition[1])


class VendorWireTests(unittest.TestCase):
    def test_snapshot_roundtrip_and_command_size(self):
        s = snapshot()
        self.assertEqual(288, len(s.encode()))
        self.assertEqual(s, Snapshot.decode(s.encode()))
        self.assertEqual(2, s.free_slots)
        command = Command(Host(123, 7, 456), 1000, KEY, s)
        data = command.encode(Verb.CREATE)
        self.assertEqual(576, len(data))
        self.assertEqual(s.encode(), data[40:328])
        self.assertEqual(bytes(244), data[332:])

    def test_malformed_state_and_commands_fail(self):
        for s in (
            replace(snapshot(), slots=(Slot(600), Slot(600))),
            replace(snapshot(), slots=(Slot(600, 1, 0),)),
            replace(snapshot(), slots=(Slot(600, 1, 1), Slot(700, 1, 2))),
            replace(snapshot(), scene=True),
            replace(snapshot(), slots=list(snapshot().slots)),
        ):
            with self.subTest(s=s), self.assertRaises(ValueError):
                s.encode()
        for verb, expected, item in (
            (Verb.INSPECT, snapshot(), 0),
            (Verb.CREATE, replace(snapshot(), quantity=2), 0),
            (Verb.CREATE, replace(snapshot(), quantity=2, multiple=1), 0),
            (Verb.CREATE, replace(snapshot(), multiple=2), 0),
            (Verb.CREATE, Snapshot(), 0), (Verb.KEEP, snapshot(), 0),
        ):
            with self.subTest(verb=verb), self.assertRaises(ValueError):
                Command(Host(1, 1, 1), 1000, KEY, expected, item).encode(verb)

    def test_receipt_identity_padding_and_readiness_are_validated(self):
        import uuid

        from shadowbane_lab.client_extension.vendor_wire import _RECEIPT

        data = _RECEIPT.pack(
            uuid.UUID(KEY).bytes, Host(123, 7, 456).encode(), 1000,
            Outcome.OBSERVED, READY, snapshot().encode(), MAGIC, 0, bytes(16), bytes(24),
        )
        self.assertEqual(KEY, Receipt.decode(data).request_key)
        for offset, value in ((336, 0), (44, READY | IN_FLIGHT), (383, 1)):
            raw = bytearray(data)
            raw[offset] = value
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                Receipt.decode(bytes(raw))
        raw = bytearray(snapshot().encode())
        raw[-1] = 1
        with self.assertRaises(ValueError):
            Snapshot.decode(bytes(raw))


class VendorBatchTests(unittest.TestCase):
    def run_batch(self, path, session, **kwargs):
        tick = [0.0]

        def sleep(delay):
            tick[0] += delay

        return fill_available_slots(
            session, path, 2517204, clock=lambda: tick[0], sleeper=sleep,
            acceptance_timeout=0.3, **kwargs,
        )

    def test_fills_all_initially_available_slots_once_and_persists_before_send(self):
        for occupied, planned in ((False, 2), (True, 1)):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "batch.json"
                session = Session(path, occupied=occupied)
                result = self.run_batch(path, session)
                self.assertEqual("complete", result["state"])
                self.assertEqual(planned, result["planned_rolls"])
                self.assertEqual(planned, len(session.calls))
                self.assertEqual(planned, len(set(session.calls)))
                self.assertEqual(0, session.state.free_slots)
                self.assertEqual(988, json.loads(path.read_text())["process_id"])
                with self.assertRaises(VendorBatchStopped):
                    self.run_batch(path, session)
                self.assertEqual(planned, len(session.calls))

    def test_ranked_vendor_uses_all_sixteen_observed_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.json"
            session = Session(path)
            session.state = snapshot(tuple(Slot(600 + i * 100) for i in range(16)))
            result = self.run_batch(path, session)
            self.assertEqual(16, len(session.calls))
            self.assertEqual(0, session.state.free_slots)
            self.assertEqual([16], result["capacity_history"])

    def test_rank_growth_during_and_between_creates_fills_new_capacity(self):
        for during in (True, False):
            with self.subTest(during=during), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "batch.json"
                session = Session(path)
                original = session.inspect

                def inspect(session=session, during=during, original=original):
                    if len(session.calls) in (1, 3) and bool(session.pending) == during:
                        count = 4 if len(session.calls) == 1 else 6
                        slots = session.state.slots
                        if len(slots) < count:
                            session.state = replace(session.state, slots=slots + tuple(
                                Slot(600 + i * 100) for i in range(len(slots), count)
                            ))
                    return original()

                session.inspect = inspect
                result = self.run_batch(path, session)
                self.assertEqual("complete", result["state"])
                self.assertEqual(6, len(session.calls))
                self.assertEqual([2, 4, 6], result["capacity_history"])
                self.assertEqual(6, result["planned_rolls"])
                self.assertEqual(0, session.state.free_slots)

    def test_capacity_loss_stops_after_pending_send_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.json"
            session = Session(path)
            original = session.inspect

            def inspect():
                if session.pending:
                    session.state = replace(session.state, slots=session.state.slots[:1])
                return original()

            session.inspect = inspect
            with self.assertRaises(VendorBatchStopped):
                self.run_batch(path, session)
            self.assertEqual(1, len(session.calls))
            self.assertEqual("uncertain", json.loads(path.read_text())["state"])

    def test_full_queue_is_a_zero_action_completed_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.json"
            session = Session(path)
            session.state = snapshot((Slot(600, 1, 1), Slot(700, 2, 2)))
            self.assertEqual("complete", self.run_batch(path, session)["state"])
            self.assertEqual([], session.calls)

    def test_wrong_vendor_fails_before_creating_a_journal_or_sending(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.json"
            session = Session(path, behavior="wrong_vendor")
            with self.assertRaises(VendorBatchStopped):
                self.run_batch(path, session)
            self.assertFalse(path.exists())
            self.assertEqual([], session.calls)

    def test_timeout_lost_response_logout_and_ambiguous_additions_never_retry(self):
        for behavior in ("timeout", "exception", "logout", "two_additions"):
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "batch.json"
                session = Session(path, behavior=behavior)
                with self.assertRaises((VendorBatchStopped, OSError)):
                    self.run_batch(path, session)
                self.assertEqual(1, len(session.calls))
                self.assertEqual("uncertain", json.loads(path.read_text())["state"])
                with self.assertRaises(VendorBatchStopped):
                    self.run_batch(path, session)
                self.assertEqual(1, len(session.calls))

    def test_explicit_rejection_stops_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.json"
            session = Session(path, behavior="rejected")
            with self.assertRaises(VendorBatchStopped):
                self.run_batch(path, session)
            self.assertEqual("stopped", json.loads(path.read_text())["state"])
            self.assertEqual(1, len(session.calls))

    def test_cancellation_before_and_after_submission_preserves_uncertainty(self):
        for after_send in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "batch.json"
                session = Session(path, behavior="timeout")
                result = self.run_batch(
                    path, session,
                    cancelled=lambda s=session, after=after_send: bool(s.calls) if after else True
                )
                self.assertEqual(
                    "cancelled_pending" if after_send else "cancelled", result["state"]
                )
                self.assertEqual(int(after_send), len(session.calls))

    def test_disk_failure_prevents_any_unjournaled_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "batch.json"
            session = Session(path)
            with patch(
                "shadowbane_lab.client_extension.vendor_batch.publish_atomic_record",
                side_effect=OSError("disk full"),
            ), self.assertRaises(OSError):
                self.run_batch(path, session)
            self.assertEqual([], session.calls)


class MultipleBatchTests(unittest.TestCase):
    def run_batch(self, path, session, **kwargs):
        tick = [0.0]
        def sleep(delay):
            tick[0] += delay
        return fill_available_slots(
            session, path, 2517204, clock=lambda: tick[0], sleeper=sleep,
            acceptance_timeout=2, **kwargs,
        )

    def test_partial_arrivals_close_recipe_and_one_durable_request_for_all_free_slots(self):
        for capacity, occupied in ((3, 0), (3, 2), (16, 0)):
            with (
                self.subTest(capacity=capacity, occupied=occupied),
                tempfile.TemporaryDirectory() as d,
            ):
                path = Path(d) / "batch.json"
                session = MultipleSession(path)
                session.state = replace(session.state, slots=tuple(
                    Slot(600 + i * 100, 50 + i, 1) if i < occupied else Slot(600 + i * 100)
                    for i in range(capacity)
                ))
                result = self.run_batch(path, session)
                self.assertEqual("complete", result["state"])
                self.assertEqual(1, len(session.calls))
                self.assertEqual(capacity - occupied, len(result["items"]))
                self.assertEqual(result["items"], result["requests"][0]["item_ids"])
                self.assertEqual(0, session.state.recipe)
                with self.assertRaises(VendorBatchStopped):
                    self.run_batch(path, session)
                self.assertEqual(1, len(session.calls))

    def test_partial_timeout_never_retries_or_publishes_partial_success(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "batch.json"
            session = MultipleSession(path, partial_timeout=True)
            with self.assertRaises(VendorBatchStopped):
                self.run_batch(path, session)
            record = json.loads(path.read_text())
            self.assertEqual("uncertain", record["state"])
            self.assertEqual([], record["items"])
            self.assertEqual(1, len(session.calls))

    def test_premature_receipt_and_disappearing_partial_item_stop(self):
        for premature in (True, False):
            with self.subTest(premature=premature), tempfile.TemporaryDirectory() as d:
                path = Path(d) / "batch.json"
                session = MultipleSession(path)
                original = session.inspect
                def inspect(session=session, premature=premature, original=original):
                    if session.arrivals == 1 and not premature:
                        session.state = replace(session.state, slots=(
                            Slot(600), *session.state.slots[1:],
                        ))
                    observed = original()
                    if premature and session.pending:
                        return replace(observed, flags=READY, transition_item=101,
                                       transition_request=session.pending)
                    return observed
                session.inspect = inspect
                with self.assertRaises(VendorBatchStopped):
                    self.run_batch(path, session)
                self.assertEqual("uncertain", json.loads(path.read_text())["state"])
                self.assertEqual(1, len(session.calls))

    def test_rank_growth_does_not_expand_the_inflight_request(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "batch.json"
            session = MultipleSession(path, close_recipe=False)
            original = session.inspect
            def inspect():
                if session.pending and len(session.state.slots) == 3:
                    session.state = replace(session.state, slots=(*session.state.slots, Slot(900)))
                return original()
            session.inspect = inspect
            result = self.run_batch(path, session)
            self.assertEqual("complete", result["state"])
            self.assertEqual([3, 1], [r["expected_item_count"] for r in result["requests"]])
            self.assertEqual(4, len(result["items"]))
            self.assertEqual([3, 4], result["capacity_history"])
