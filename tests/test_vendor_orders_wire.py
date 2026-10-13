"""The order-count profile is additive and cannot authorize crafting."""
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from shadowbane_lab.client_extension.action_channel import NativeActionChannelError
from shadowbane_lab.client_extension.vendor_session import NativeVendorSession
from shadowbane_lab.client_extension.vendor_wire import (
    _RECEIPT,
    IN_FLIGHT,
    MAGIC,
    ORDERS_MAGIC,
    READY,
    Command,
    Host,
    Outcome,
    Receipt,
    Slot,
    Verb,
)
from tests.test_vendor_batch import KEY, snapshot
from tests.test_vendor_session import Transport


def raw_receipt(*, magic=ORDERS_MAGIC, extension=bytes([9, 1]) + bytes(22)):
    state = replace(snapshot((Slot(600, 123, 1), Slot(700))), quantity=10, multiple=1)
    return _RECEIPT.pack(uuid.UUID(KEY).bytes, Host(1, 1, 1).encode(), 1000,
                         Outcome.OBSERVED, READY, state.encode(), magic, 0,
                         bytes(16), extension)


def test_preserves_raw_count_and_empty_slot_count_without_inferring_items():
    result = Receipt.decode(raw_receipt())
    assert result.remaining_counts == (9, 1)
    assert result.snapshot.free_slots == 1
    assert Receipt.decode(raw_receipt(extension=bytes(24))).remaining_counts == (0, 0)
    assert Receipt.decode(raw_receipt(magic=MAGIC, extension=bytes(24))).remaining_counts is None


@pytest.mark.parametrize("magic,extension", [
    (MAGIC, bytes([9, 1]) + bytes(22)),
    (ORDERS_MAGIC, bytes([9, 1, 1]) + bytes(21)),
    (ORDERS_MAGIC, bytes(23) + b"\x01"),
    (0x57425633, bytes(24)),
])
def test_unknown_profile_and_nonzero_unused_count_bytes_rejected(magic, extension):
    with pytest.raises(ValueError):
        Receipt.decode(raw_receipt(magic=magic, extension=extension))


def test_orders_inspection_carries_no_mutation_and_ten_item_create_stays_rejected():
    command = Command(Host(1, 1, 1), 1000, KEY)
    assert len(command.encode(Verb.INSPECT_ORDERS)) == 576
    state = Receipt.decode(raw_receipt()).snapshot
    for verb in (Verb.CREATE, Verb.CREATE_RANDOM, Verb.INSPECT_ORDERS):
        with pytest.raises(ValueError):
            replace(command, expected=state).encode(verb)
    with pytest.raises(ValueError):
        replace(command, item=123).encode(Verb.INSPECT_ORDERS)


@pytest.mark.parametrize("wrong_profile", [False, True])
def test_session_requires_the_explicit_order_profile(wrong_profile):
    with patch("shadowbane_lab.client_extension.vendor_session.channel."
               "WindowsNativeActionCommandTransport", Transport):
        session = NativeVendorSession(Transport.host_process_identity, 1000)
        original = session._transport.submit

        def submit(command, **kwargs):
            result = original(command, **kwargs)
            raw = bytearray(result.movement_payload)
            if not wrong_profile:
                raw[336:340] = ORDERS_MAGIC.to_bytes(4, "little")
                raw[360:362] = bytes([9, 1])
            return replace(result, detail="native_vendor_orders_receipt_v2",
                           movement_payload=bytes(raw))

        session._transport.submit = submit
        try:
            if wrong_profile:
                with pytest.raises(NativeActionChannelError, match="profile mismatch"):
                    session.inspect_orders()
            else:
                assert session.inspect_orders().remaining_counts == (9, 1)
            assert len(session._transport.commands) == 1
            assert session._transport.commands[0].kind == Verb.INSPECT_ORDERS
        finally:
            session.close()


def test_old_native_cannot_be_silently_used_as_order_support():
    with patch("shadowbane_lab.client_extension.vendor_session.channel."
               "WindowsNativeActionCommandTransport", Transport):
        session = NativeVendorSession(Transport.host_process_identity, 1000)
        try:
            with pytest.raises(NativeActionChannelError, match="native_vendor_receipt_v1"):
                session.inspect_orders()
            assert len(session._transport.commands) == 1
        finally:
            session.close()


def test_cpp_order_receipt_matches_python():
    raw = bytes.fromhex((Path(__file__).parent / "fixtures" /
                         "native_vendor_orders_wire_v2.hex").read_text().strip())
    result = Receipt.decode(raw)
    assert result.remaining_counts == (9, 1)
    assert result.snapshot.quantity == 10 and result.snapshot.multiple == 1
    assert result.snapshot.slots == (Slot(600, 123, 1), Slot(700))
    assert result.flags == READY and not result.flags & IN_FLIGHT
