import json
import uuid
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from shadowbane_lab.client_extension import vendor_navigation_wire as nav
from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelTimeout,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.guard_spending_journal import (
    GuardSpendingJournal,
    GuardSpendingStopped,
)
from shadowbane_lab.client_extension.vendor_navigation_session import NativeVendorNavigationSession
from tests.test_guard_upgrade_journal import (
    COMMAND as UPGRADE,
)
from tests.test_guard_upgrade_journal import (
    FINISHED as UPGRADED,
)
from tests.test_guard_upgrade_journal import (
    IDENTITY,
)
from tests.test_guard_upgrade_journal import (
    SUBMITTED as UPGRADING,
)
from tests.test_vendor_navigation import KEY, OPENED, STATE, Transport

HOST = nav.Host(1, 1, 1)
WAREHOUSE = replace(OPENED, warehouse_hud=800, warehouse_object=900, front_hud=800,
                    warehouse_id=777, warehouse_type=42)
GUARD = replace(OPENED, visible=3, vendor_hud=600, front_hud=600, selected_entry=700,
                vendor_id=777, vendor_type=37)
CASES = [(nav.Verb.BUILDING, STATE, 0, OPENED),
         (nav.Verb.GUARD, OPENED, 777, GUARD),
         (nav.Verb.WAREHOUSE, OPENED, 777, WAREHOUSE)]


def command(before=OPENED, target=777, key=KEY):
    return nav.Command(HOST, 1000, key, before, 123, target)


def receipt(c, state, outcome=nav.Outcome.OBSERVED, flags=0, key=None):
    return nav.Receipt(key or c.request_key, HOST, 1000, outcome, flags, state, c.request_key)


def blocked(journal):
    dispatch = Mock()
    with pytest.raises(GuardSpendingStopped):
        journal.submit(IDENTITY, replace(UPGRADE, request_key=str(uuid.uuid4())), dispatch)
    dispatch.assert_not_called()
    with pytest.raises(GuardSpendingStopped):
        journal.assert_idle()


@pytest.mark.parametrize("verb,before,target,after", CASES)
def test_guard_navigation_intent_blocks_spending_until_same_lease_completion(
    tmp_path, verb, before, target, after,
):
    journal = GuardSpendingJournal(tmp_path)
    c = command(before, target)

    def dispatch():
        saved = json.loads(journal._path(KEY).read_text())
        assert saved["operation"] == "navigate_" + verb.name.lower()
        assert saved["submission"] is None
        assert nav.Command.decode(bytes.fromhex(saved["command"]), verb) == c
        assert json.loads(journal.active.read_text())["request_key"] == KEY
        return receipt(c, before, nav.Outcome.SUBMITTED, nav.IN_FLIGHT)

    journal.submit(IDENTITY, c, dispatch, navigation_verb=verb)
    blocked(GuardSpendingJournal(tmp_path))
    journal.observe(IDENTITY, receipt(c, after, key=str(uuid.uuid4())))
    journal.assert_idle()
    with pytest.raises(GuardSpendingStopped, match="already attempted"):
        journal.submit(IDENTITY, c, Mock(), navigation_verb=verb)


@pytest.mark.parametrize("verb,before,target,after", CASES)
def test_already_open_correlated_navigation_is_terminal(tmp_path, verb, before, target, after):
    journal = GuardSpendingJournal(tmp_path)
    c = command(after, target)
    journal.submit(IDENTITY, c, lambda: receipt(c, after), navigation_verb=verb)
    journal.assert_idle()
    assert json.loads(journal._path(KEY).read_text())["submission"]
    with pytest.raises(GuardSpendingStopped):
        journal.submit(IDENTITY, c, Mock(), navigation_verb=verb)


@pytest.mark.parametrize("verb,before,target,after", CASES)
def test_lost_navigation_reply_cannot_be_inferred_or_cleared_after_restart(
    tmp_path, verb, before, target, after,
):
    journal = GuardSpendingJournal(tmp_path)
    c = command(before, target)
    with pytest.raises(TimeoutError):
        journal.submit(IDENTITY, c, Mock(side_effect=TimeoutError), navigation_verb=verb)
    resumed = GuardSpendingJournal(tmp_path)
    resumed.observe(IDENTITY, receipt(c, after))
    blocked(resumed)
    resumed.observe(NativeClientProcessIdentity(999, 456), receipt(c, after))
    blocked(resumed)


@pytest.mark.parametrize("change", ["warehouse", "building", "scene", "manager", "type",
                                    "lease", "request", "pending", "unresolved", "lifetime",
                                    "background"])
def test_wrong_or_partial_warehouse_response_never_unlocks_spending(tmp_path, change):
    journal = GuardSpendingJournal(tmp_path)
    c = command()
    journal.submit(IDENTITY, c, lambda: receipt(c, OPENED, nav.Outcome.SUBMITTED, nav.IN_FLIGHT),
                   navigation_verb=nav.Verb.WAREHOUSE)
    r = receipt(c, WAREHOUSE)
    identity = IDENTITY
    if change == "background":
        r = replace(r, snapshot=replace(WAREHOUSE, front_hud=999))
    elif change in ("warehouse", "building", "scene", "manager"):
        field = {"warehouse": "warehouse_id", "building": "building_id"}.get(change, change)
        r = replace(r, snapshot=replace(WAREHOUSE, **{field: 999}))
    elif change == "type":
        journal.observe(IDENTITY, UPGRADED)
        blocked(journal)
        return
    elif change == "lease":
        r = replace(r, host=replace(HOST, lease_generation=2))
    elif change == "request":
        r = replace(r, transition_request=str(uuid.uuid4()))
    elif change == "lifetime":
        identity = NativeClientProcessIdentity(999, 456)
    else:
        r = replace(r, flags=nav.IN_FLIGHT if change == "pending" else nav.UNRESOLVED)
    journal.observe(identity, r)
    blocked(journal)
    if change == "unresolved":
        journal.observe(IDENTITY, receipt(c, WAREHOUSE))
        blocked(journal)


def test_spending_blocks_navigation_before_dispatch(tmp_path):
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, UPGRADE, lambda: UPGRADING)
    dispatch = Mock()
    with pytest.raises(GuardSpendingStopped):
        journal.submit(IDENTITY, command(), dispatch, navigation_verb=nav.Verb.WAREHOUSE)
    dispatch.assert_not_called()
    journal.observe(IDENTITY, receipt(command(), WAREHOUSE))
    blocked(journal)


def test_navigation_requires_explicit_supported_operation(tmp_path):
    journal = GuardSpendingJournal(tmp_path)
    for verb in (None, nav.Verb.INSPECT, nav.Verb.VENDOR):
        with pytest.raises(ValueError):
            journal.submit(IDENTITY, command(), Mock(), navigation_verb=verb)
    with pytest.raises(ValueError):
        journal.submit(IDENTITY, UPGRADE, Mock(), navigation_verb=nav.Verb.GUARD)
    assert not journal.active.exists()


def test_navigation_command_roundtrip_validates_type_and_padding():
    c = command()
    raw = c.encode(nav.Verb.WAREHOUSE)
    assert nav.Command.decode(raw, nav.Verb.WAREHOUSE) == c
    for offset in (140, 148, 152):
        damaged = bytearray(raw)
        damaged[offset] ^= 1
        with pytest.raises(ValueError):
            nav.Command.decode(bytes(damaged), nav.Verb.WAREHOUSE)


def test_navigation_session_records_lost_reply_before_transport_and_never_retries(tmp_path):
    journal = GuardSpendingJournal(tmp_path)
    with patch(
        "shadowbane_lab.client_extension.vendor_navigation_session.channel.WindowsNativeActionCommandTransport",
        Transport,
    ):
        session = NativeVendorNavigationSession(IDENTITY, 1000, journal=journal)
        session._transport.mode = "timeout"
        with pytest.raises(NativeActionChannelTimeout, match="test"):
            session.open_warehouse(OPENED, 123, 777, KEY)
        assert len(session._transport.commands) == 1
        with pytest.raises(GuardSpendingStopped):
            session.open_guard(OPENED, 123, 777, str(uuid.uuid4()))
        assert len(session._transport.commands) == 1
        session.close()
    blocked(GuardSpendingJournal(tmp_path))
