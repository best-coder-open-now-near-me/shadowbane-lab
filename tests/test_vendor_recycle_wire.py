import uuid
from dataclasses import replace
from unittest.mock import patch

import pytest

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeActionResult,
    NativeActionResultStage,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.vendor_session import NativeVendorSession
from shadowbane_lab.client_extension.vendor_wire import (
    _RECEIPT,
    _RECYCLE_BATCH,
    _RECYCLE_COMPLETION,
    IN_FLIGHT,
    MAGIC,
    READY,
    RECYCLE_MAGIC,
    Command,
    Host,
    NativeRecycleBatch,
    NativeRecycleCompletion,
    Outcome,
    Receipt,
    Snapshot,
    Verb,
)
from tests.test_vendor_batch import KEY, snapshot

BATCH = NativeRecycleBatch((1001, 1002), "a" * 64, 1000, 302)
STATE = replace(snapshot(), inventory=900)


def raw_receipt(*, completion=None, transition=False, magic=RECYCLE_MAGIC):
    return _RECEIPT.pack(uuid.UUID(KEY).bytes, Host(123, 7, 456).encode(), 1000,
                         Outcome.OBSERVED, READY, STATE.encode(), magic,
                         2 if transition else 0, uuid.UUID(KEY).bytes if transition else bytes(16),
                         _RECYCLE_COMPLETION.pack(*(completion or (0, 0, 0, 0))))


def test_exact_recycle_profile_does_not_alias_order_budget_or_legacy_padding():
    command = Command(Host(123, 7, 456), 1000, KEY, STATE, 2, recycle_batch=BATCH)
    raw = command.encode(Verb.RECYCLE)
    assert len(raw) == 576 and int.from_bytes(raw[328:332], "little") == 2
    digest, gold, refund, *tail = _RECYCLE_BATCH.unpack(raw[332:])
    assert digest.hex() == BATCH.fingerprint and (gold, refund) == (1000, 302)
    assert tail[:2] == [1001, 1002] and not any(tail[2:-1]) and not any(tail[-1])
    assert Receipt.decode(raw_receipt()).recycle_completion == NativeRecycleCompletion(0, 0, 0, 0)
    receipt = Receipt.decode(raw_receipt(completion=(657, 682, 302, 1302), transition=True))
    assert receipt.transition_request == KEY and receipt.transition_item == 2
    assert receipt.recycle_completion == NativeRecycleCompletion(657, 682, 302, 1302)
    assert receipt.remaining_counts is None


@pytest.mark.parametrize("field,value", [
    ("items", (1002, 1001)), ("items", (1001, 1001)), ("items", ()),
    ("items", tuple(range(1, 50))), ("items", (True,)),
    ("fingerprint", "0" * 64), ("fingerprint", "A" * 64), ("fingerprint", "q" * 64),
    ("gold_before", True), ("gold_before", 2**31 - 1), ("refund", 0), ("refund", True),
])
def test_noncanonical_batches_are_rejected(field, value):
    with pytest.raises(ValueError):
        replace(BATCH, **{field: value}).encode()


def test_legacy_verbs_and_inspections_cannot_smuggle_recycling_arguments():
    for verb in (Verb.INSPECT_RECYCLE, Verb.INSPECT, Verb.INSPECT_ORDERS, Verb.CREATE, Verb.KEEP):
        with pytest.raises(ValueError):
            Command(Host(123, 7, 456), 1000, KEY, STATE, 2, recycle_batch=BATCH).encode(verb)
    for state in (Snapshot(), replace(STATE, inventory=0),
                  replace(STATE, slots=(replace(STATE.slots[0], item=99, state=1),))):
        with pytest.raises(ValueError):
            command = Command(Host(123, 7, 456), 1000, KEY, state, 2, recycle_batch=BATCH)
            command.encode(Verb.RECYCLE)
    with pytest.raises(ValueError):
        Command(Host(123, 7, 456), 1000, KEY, STATE, 1, recycle_batch=BATCH).encode(Verb.RECYCLE)


@pytest.mark.parametrize("completion,transition", [
    ((657, 682, 302, 1302), False), ((657, 657, 302, 1302), True),
    ((657, 682, 0, 1302), True), ((657, 682, 1303, 1302), True),
    ((657, 2**63, 302, 1302), True), ((657, 682, 302, 2**31), True),
])
def test_partial_or_unbounded_completion_cannot_be_a_receipt(completion, transition):
    with pytest.raises(ValueError):
        Receipt.decode(raw_receipt(completion=completion, transition=transition))


class Transport:
    host_process_identity = NativeClientProcessIdentity(123, 456)
    host_lease_generation = 7
    detail = "native_vendor_recycle_receipt_v1"
    magic = RECYCLE_MAGIC

    def __init__(self, identity):
        self.commands = []

    def submit(self, command, *, timeout_ms):
        self.commands.append(command)
        assert len(command.encode_slot(sequence=1, created_tick=100, deadline_tick=850)) == 768
        action = command.kind == Verb.RECYCLE
        raw = _RECEIPT.pack(uuid.UUID(command.payload.request_key).bytes,
                            command.payload.host.encode(), command.payload.window,
                            Outcome.SUBMITTED if action else Outcome.OBSERVED,
                            IN_FLIGHT if action else READY, STATE.encode(), self.magic,
                            0, bytes(16), bytes(24))
        return NativeActionResult(1, command.command_id, 1,
                                  NativeActionResultStage.SUBMITTED_TO_CLIENT,
                                  0, 100, 5760, self.detail, raw)

    def close(self):
        pass


def test_shared_producer_session_submits_one_typed_batch_and_keeps_inspection_distinct():
    with patch("shadowbane_lab.client_extension.vendor_session.channel."
               "WindowsNativeActionCommandTransport", Transport):
        session = NativeVendorSession(NativeClientProcessIdentity(988, 12345), 1000)
        assert session.inspect_recycle().recycle_completion is not None
        result = session.recycle(STATE, KEY, BATCH)
        assert result.outcome == Outcome.SUBMITTED
        assert [c.kind for c in session._transport.commands] == [Verb.INSPECT_RECYCLE, Verb.RECYCLE]
        assert session._transport.commands[1].payload.recycle_batch == BATCH
        session.close()


def test_legacy_host_receipt_cannot_pretend_to_offer_recycle_support():
    with patch("shadowbane_lab.client_extension.vendor_session.channel."
               "WindowsNativeActionCommandTransport", Transport), patch.object(
                   Transport, "magic", MAGIC):
        session = NativeVendorSession(NativeClientProcessIdentity(988, 12345), 1000)
        with pytest.raises(NativeActionChannelError, match="profile"):
            session.inspect_recycle()
        session.close()
