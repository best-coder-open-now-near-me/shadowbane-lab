import uuid
from dataclasses import replace
from types import SimpleNamespace

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelTimeout,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.movement_dispatcher import NativeMovementTravelDispatcher
from shadowbane_lab.client_extension.movement_session import NativeMovementGrant
from shadowbane_lab.client_extension.movement_wire import Grant, Host, Owner
from shadowbane_lab.protocol import Vector2
from shadowbane_lab.travel.model import TravelDecision, TravelManeuver, TravelPhase


class Session:
    def __init__(self, grant):
        self.observed = grant.ownership
        self.calls = []
        self.fail = False

    def snapshot(self):
        return SimpleNamespace(grant=self.observed, flags=3)

    def move(self, grant, destination, key):
        self.calls.append(("move", grant, destination, key))
        if self.fail:
            raise NativeActionChannelTimeout("delayed")

    def pause(self, grant, key):
        self.calls.append(("pause", grant, key))


def setup():
    grant = NativeMovementGrant(
        NativeClientProcessIdentity(123, 456),
        789,
        Grant(10, 20, Owner.AUTOMATION, "worker", "operation"),
        Host(22, 3, 44),
        str(uuid.uuid4()),
    )
    session = Session(grant)
    decision = TravelDecision(
        1,
        1,
        TravelPhase.TRAVELING,
        0,
        50,
        1,
        minimap_direction=Vector2(1, 0),
        maneuver=TravelManeuver.DIRECT,
        click_destination=Vector2(123, 456),
    )
    return session, NativeMovementTravelDispatcher(session, grant), decision


def test_native_adapter_preserves_bounded_destination_and_pauses_same_grant():
    session, adapter, decision = setup()
    assert adapter.dispatch(decision).accepted
    assert session.calls[-1][2] == (123, 0.0, -456)
    stop = replace(
        decision,
        phase=TravelPhase.STOPPED,
        minimap_direction=None,
        maneuver=None,
        click_destination=None,
        terminal_reason="pause",
    )
    assert adapter.stop_movement(stop).accepted
    assert adapter.dispatch(replace(decision, decision_id=2)).accepted
    assert [call[0] for call in session.calls] == ["move", "pause", "move"]
    assert all(call[1] == adapter.grant for call in session.calls)


def test_takeover_latches_combat_stop_without_reacquisition():
    session, adapter, decision = setup()
    session.observed = Grant(11, 20, Owner.MANUAL)
    assert adapter.is_set() and adapter.interruption_reason
    session.observed = adapter.grant.ownership
    assert adapter.is_set() and not adapter.dispatch(decision).accepted
    assert session.calls == []


def test_ambiguous_move_latches_interruption_and_stable_request_key():
    session, adapter, decision = setup()
    assert adapter._request("move", decision) == adapter._request("move", decision)
    session.fail = True
    assert not adapter.dispatch(decision).accepted
    assert adapter.is_set()
    session.fail = False
    assert not adapter.dispatch(decision).accepted and len(session.calls) == 1
