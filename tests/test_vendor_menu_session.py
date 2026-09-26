import uuid
from dataclasses import replace
from unittest.mock import patch

import pytest

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeActionChannelTimeout,
    NativeActionResult,
    NativeActionResultStage,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.vendor_menu_session import NativeVendorMenuSession
from shadowbane_lab.client_extension.vendor_menu_wire import Host, Outcome, Verb
from tests.test_vendor_menu import KEY, state
from tests.test_vendor_menu_wire import raw_receipt

MODULE = "shadowbane_lab.client_extension.vendor_menu_session"


class Transport:
    host_process_identity = NativeClientProcessIdentity(123, 456)
    host_lease_generation = 7

    def __init__(self, identity):
        self.commands = []
        self.closed = False
        self.mode = "normal"

    def submit(self, command, *, timeout_ms):
        self.commands.append(command)
        assert len(command.encode_slot(sequence=1, created_tick=10,
                                       deadline_tick=10 + timeout_ms)) == 768
        if self.mode == "timeout":
            raise NativeActionChannelTimeout("timeout")
        payload = raw_receipt(request=uuid.UUID(command.payload.request_key).bytes)
        if self.mode == "wrong_request":
            payload = raw_receipt()
        if self.mode == "wrong_window":
            payload = raw_receipt(request=uuid.UUID(command.payload.request_key).bytes, window=1000)
        if self.mode == "wrong_host":
            payload = raw_receipt(request=uuid.UUID(command.payload.request_key).bytes,
                                  host=Host(124, 7, 456).encode())
        result = NativeActionResult(1, command.command_id, 1,
                                   NativeActionResultStage.SUBMITTED_TO_CLIENT, 0, 10, 99,
                                   "native_vendor_menu_receipt_v1", payload)
        if self.mode == "contradiction":
            return replace(result, stage=NativeActionResultStage.FAILED)
        if self.mode in ("expired", "unknown"):
            return replace(result, stage=NativeActionResultStage.FAILED, error_code=13,
                           detail="invalid_or_expired_vendor_menu_lease"
                           if self.mode == "expired" else "unknown_command_kind")
        return result

    def renew_lease(self):
        self.host_lease_generation += 1

    def close(self):
        self.closed = True


@pytest.fixture
def session():
    with patch(MODULE + ".channel.WindowsNativeActionCommandTransport", Transport), patch(
        MODULE + ".time.sleep"
    ):
        value = NativeVendorMenuSession(NativeClientProcessIdentity(988, 12345), 999)
        yield value
        value.close()


def test_session_correlates_and_closes(session):
    assert session.inspect().outcome == Outcome.OBSERVED
    assert session._transport.commands[0].kind == Verb.INSPECT
    session.close()
    assert session._transport.closed
    with pytest.raises(NativeActionChannelError):
        session.inspect()


@pytest.mark.parametrize("mode", ["wrong_request", "wrong_window", "wrong_host", "contradiction"])
def test_session_rejects_unrelated_or_contradictory_receipts(session, mode):
    session._transport.mode = mode
    with pytest.raises(NativeActionChannelError):
        session.inspect()
    assert len(session._transport.commands) == 1


@pytest.mark.parametrize("mode,count", [("expired", 3), ("timeout", 3), ("unknown", 1)])
def test_inspection_retry_is_bounded_with_fresh_ids(session, mode, count):
    session._transport.mode = mode
    with pytest.raises(NativeActionChannelError):
        session.inspect()
    commands = session._transport.commands
    assert len(commands) == count
    assert len({c.payload.request_key for c in commands}) == count
    assert len({c.command_id for c in commands}) == count


@pytest.mark.parametrize("mode", ["expired", "timeout", "unknown"])
def test_mutations_never_retry(session, mode):
    session._transport.mode = mode
    with pytest.raises(NativeActionChannelError):
        session.open_recipe(state(), KEY)
    assert len(session._transport.commands) == 1


def test_borrowed_adapter_shares_lease_sequence_and_preserves_parent_lifetime():
    from shadowbane_lab.client_extension.vendor_session import NativeVendorSession

    with patch("shadowbane_lab.client_extension.vendor_session.channel."
               "WindowsNativeActionCommandTransport", Transport) as factory:
        parent = NativeVendorSession(NativeClientProcessIdentity(988, 12345), 999)
        next(parent._ids)
        adapter = parent.menu_session()
        assert adapter.identity == parent.identity and adapter.window == parent.window
        assert adapter._transport is parent._transport
        assert adapter._ids is parent._ids
        assert adapter.inspect().outcome == Outcome.OBSERVED
        assert parent._transport.commands[0].command_id == 2
        assert factory is Transport
        adapter.close()
        assert not parent._transport.closed
        with pytest.raises(NativeActionChannelError):
            adapter.inspect()
        second = parent.menu_session()
        assert second.inspect().outcome == Outcome.OBSERVED
        assert parent._transport.commands[1].command_id == 3
        parent.close()
        assert parent._transport.closed
        with pytest.raises(NativeActionChannelError):
            second.inspect()
        with pytest.raises(NativeActionChannelError):
            second.renew_lease()
        with pytest.raises(NativeActionChannelError):
            parent.menu_session()
        assert len(parent._transport.commands) == 2
