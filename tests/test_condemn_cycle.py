import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension import condemn_session as native
from shadowbane_lab.client_extension import vendor_navigation_wire as nav
from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.condemn_wire import IN_FLIGHT, READY, Receipt, Verb
from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.manager import condemn_cycle as module
from shadowbane_lab.manager.vendor_job import VendorJobStore
from tests.test_condemn_session import Reader, Stream, Transport
from tests.test_condemn_transaction import BEFORE, LIFE, TARGET
from tests.test_guard_funding_cycle import Session, World

OWNER = dict(player_pointer=500, character_name="Poley", server_name="test")


class ScopedTransport(Transport):
    def submit(self, command, timeout_ms):
        result = super().submit(command, timeout_ms)
        if self.mode == "wrong_scope":
            return result
        receipt = Receipt.decode(result.movement_payload)
        building = command.payload.target.building
        snapshot = replace(
            receipt.snapshot,
            building=building,
            context=building if receipt.snapshot.kos else (0, 0),
        )
        receipt = replace(receipt, target=command.payload.target, snapshot=snapshot)
        if command.kind == Verb.ENSURE or command.payload.transition_request:
            receipt = replace(receipt, transition_target=command.payload.target)
        elif not receipt.flags & IN_FLIGHT:
            receipt = replace(receipt, flags=READY)
        return replace(result, movement_payload=receipt.encode())


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    binding = SimpleNamespace(
        game_process_id=LIFE.process_id,
        game_process_started_at_100ns=LIFE.creation,
        game_window_handle=1000,
    )
    operation = SimpleNamespace(operation_id="operation-" + "a" * 32)
    context = module.CondemnContext(LIFE, BEFORE.root)
    world = World()
    world.navigation = nav.Snapshot(
        scene=LIFE.scene_epoch, revision=1, root=BEFORE.root, manager=BEFORE.manager
    )
    stream = Stream()
    monkeypatch.setattr(ScopedTransport, "stream", stream)
    monkeypatch.setattr(Reader, "stream", stream)
    monkeypatch.setattr(native.channel, "WindowsNativeActionCommandTransport", ScopedTransport)
    monkeypatch.setattr(native, "CondemnResponseReader", Reader)
    monkeypatch.setattr(native, "WindowsSharedMemorySnapshotReader", lambda: object())
    from tests import test_guard_funding_cycle as guard_tests

    identity = NativeClientProcessIdentity(LIFE.process_id, LIFE.creation)
    monkeypatch.setattr(guard_tests, "IDENTITY", identity)
    sessions = []
    options = dict(mode="normal")

    def navigation_factory(binding, *, journal):
        assert not world.open_sessions
        world.open_sessions += 1
        return Session(world, "navigation", journal, nav.Host(1, 7, 1))

    def session_factory(binding, *, progress):
        assert not world.open_sessions and world.pending is None
        GuardSpendingJournal(store.root).assert_idle()
        monkeypatch.setattr(ScopedTransport, "progress", progress)
        s = native.NativeCondemnSession(identity, 1000, progress=progress)
        s._transport.mode = options["mode"]
        sessions.append(s)
        return s

    tick = [0]

    def clock():
        tick[0] += 0.05
        return tick[0]

    def run(**changes):
        return module.run_condemn_cycle(
            store,
            binding,
            operation,
            context,
            changes.pop("targets", (TARGET,)),
            OWNER,
            cancelled=lambda: False,
            navigation_factory=navigation_factory,
            session_factory=session_factory,
            owner_reader=lambda _: OWNER,
            clock=clock,
            sleep=lambda _: None,
            **changes,
        )

    return SimpleNamespace(
        store=store,
        navigation_factory=navigation_factory,
        session_factory=session_factory,
        clock=clock,
        binding=binding,
        operation=operation,
        context=context,
        world=world,
        sessions=sessions,
        options=options,
        run=run,
        path=store.root / "condemn-cycles" / (operation.operation_id + ".json"),
    )


def test_building_handoff_and_complete_native_chain_share_durable_receipts(setup):
    result = setup.run()
    assert result["state"] == "complete"
    assert setup.world.calls == ["building"]
    assert result["navigation"]["request"] and result["navigation"]["after"]
    assert result["actions"][0]["state"] == "state_verified"
    store = CondemnProgressStore(setup.store.root)
    assert store.read()["attempts"][0]["request"] == result["actions"][0]["request"]
    assert store.verified_native_targets(LIFE) == {TARGET}
    assert not setup.world.open_sessions
    assert all(s._closed for s in setup.sessions)
    with pytest.raises(module.CondemnCycleStopped, match="already attempted"):
        setup.run()
    assert setup.world.calls == ["building"] and len(setup.sessions) == 1


def test_guild_and_nation_remain_distinct_even_for_same_identity(setup):
    setup.options["mode"] = "existing"
    targets = (TARGET, replace(TARGET, scope=4))
    result = setup.run(targets=targets)
    assert result["state"] == "complete" and len(result["actions"]) == 2
    assert {a["state"] for a in result["actions"]} == {"already_enabled"}
    assert CondemnProgressStore(setup.store.root).verified_native_targets(LIFE) == set(targets)
    assert len(setup.sessions) == 1


def test_lost_building_reply_never_hands_off_to_condemn(setup):
    setup.world.fail = "building"
    with pytest.raises(TimeoutError):
        setup.run()
    assert not setup.sessions
    assert json.loads(setup.path.read_bytes())["state"] == "review"
    from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingStopped

    with pytest.raises(GuardSpendingStopped):
        GuardSpendingJournal(setup.store.root).assert_idle()


@pytest.mark.parametrize("mode", ["timeout", "wrong_request", "wrong_scope", "reader_failure"])
def test_condemn_fault_stops_before_next_crest_and_preserves_record(setup, mode):
    setup.options["mode"] = mode
    with pytest.raises((RuntimeError, ValueError, OSError)):
        setup.run(targets=(TARGET, replace(TARGET, scope=4)))
    record = json.loads(setup.path.read_bytes())
    assert record["state"] == "review" and len(record["actions"]) <= 1
    assert len(setup.sessions[0]._transport.commands) <= 2


def test_pause_finishes_current_chain_before_next_crest(setup):
    def paused():
        return bool(setup.sessions and setup.sessions[0]._transport.original)

    result = setup.run(targets=(TARGET, replace(TARGET, scope=4)), pause_requested=paused)
    assert result["state"] == "paused"
    assert [a["state"] for a in result["actions"]] == ["state_verified"]
    CondemnProgressStore(setup.store.root).assert_idle()


def test_pause_before_navigation_sends_nothing(setup):
    assert setup.run(pause_requested=lambda: True)["state"] == "paused"
    assert not setup.world.calls and not setup.sessions


def test_changed_scene_blocks_before_building_open(setup):
    setup.world.navigation = replace(setup.world.navigation, scene=7)
    with pytest.raises(module.CondemnCycleStopped, match="area changed"):
        setup.run()
    assert not setup.world.calls and not setup.sessions


@pytest.mark.parametrize(
    "targets", [(), (TARGET, TARGET), (TARGET, replace(TARGET, building=(101, 8)))]
)
def test_invalid_selection_is_rejected_without_navigation(setup, targets):
    with pytest.raises(ValueError):
        setup.run(targets=targets)
    assert not setup.path.exists() and not setup.world.calls


def test_foreign_process_selection_is_rejected_before_any_action(setup):
    setup.binding.game_process_id += 1
    with pytest.raises(module.CondemnCycleStopped, match="lifetime"):
        setup.run()
    assert not setup.path.exists() and not setup.world.calls


def test_changed_character_stops_before_condemn_continuation(setup, monkeypatch):
    original = module._Cycle.check

    def check(cycle):
        if setup.sessions and setup.sessions[0]._transport.original:
            cycle.owner_reader = lambda _: dict(OWNER, character_name="another")
        original(cycle)

    monkeypatch.setattr(module._Cycle, "check", check)
    with pytest.raises(RuntimeError, match="character changed"):
        setup.run()
    assert CondemnProgressStore(setup.store.root).read()["active"]
    assert len(setup.sessions[0]._transport.commands) == 2


def test_saved_condemn_uncertainty_blocks_other_manager_ui_runners(setup):
    from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStopped
    from shadowbane_lab.manager.guard_funding_cycle import (
        GuardFundingTarget,
        run_guard_funding_cycle,
    )
    from shadowbane_lab.manager.vendor_discovery import _run_discovery
    from shadowbane_lab.manager.vendor_job import run_vendor_job
    from shadowbane_lab.manager.vendor_navigation import _run_building_discovery
    from tests.test_condemn_transaction import Flow

    Flow(setup.store.root).start()
    for call in [
        lambda: setup.run(),
        lambda: run_vendor_job(setup.store, None, 1000),
        lambda: _run_discovery(
            setup.store,
            setup.binding,
            setup.operation,
            None,
            cancelled=lambda: False,
            reader=None,
            clock=None,
            sleep=None,
            guard=False,
        ),
        lambda: _run_building_discovery(
            setup.store,
            setup.binding,
            setup.operation,
            None,
            {},
            cancelled=lambda: False,
            reader=None,
            clock=None,
            sleep=None,
            guard=False,
        ),
        lambda: run_guard_funding_cycle(
            setup.store,
            setup.binding,
            setup.operation,
            GuardFundingTarget(
                LIFE.process_id, LIFE.creation, LIFE.scene_epoch, BEFORE.root, 100, 777
            ),
            cancelled=lambda: False,
        ),
    ]:
        with pytest.raises(CondemnProgressStopped):
            call()
    assert not setup.path.exists() and not setup.world.calls
