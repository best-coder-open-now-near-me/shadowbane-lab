"""Exercise the production producer lease against Windows shared memory/processes."""

import ctypes
import mmap
import multiprocessing
import sys
import threading
import uuid

import pytest

from shadowbane_lab.client_extension import action_channel as channel

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows native IPC")


def _transport(name):
    memory = mmap.mmap(-1, channel.CLIENT_ACTION_CHANNEL_SIZE, tagname=name)
    transport = channel.WindowsNativeActionCommandTransport.__new__(
        channel.WindowsNativeActionCommandTransport
    )
    transport._kernel = channel._WindowsKernel()
    transport._view = ctypes.addressof(ctypes.c_char.from_buffer(memory))
    transport._host_lease_timeout_ms = 1000
    transport._producer_lock_name = name + ".Producer"
    transport._lease_generation = None
    transport._lock = threading.Lock()
    transport._mapping = transport._command_signal = transport._result_signal = None
    return transport, memory


def _close(transport, memory):
    # mmap owns this fixture's mapping; production close still executes its exact
    # lease release path, but must not unmap an independently owned Python view.
    original = transport._kernel.unmap_view
    transport._kernel.unmap_view = lambda view: None
    try:
        transport.close()
    finally:
        transport._kernel.unmap_view = original
        memory.close()


def _contend(name, ready, start, finish, results):
    transport, memory = _transport(name)
    ready.put(True)
    start.wait(10)
    try:
        transport._claim_host_lease()
        results.put("claimed")
    except channel.NativeActionChannelBusy:
        results.put("busy")
    finally:
        finish.wait(10)
        _close(transport, memory)


def test_two_processes_cannot_claim_the_same_producer():
    ctx = multiprocessing.get_context("spawn")
    name = "Local\\WonderBane.LeaseTest." + uuid.uuid4().hex
    keeper, memory = _transport(name)
    ready, results = ctx.Queue(), ctx.Queue()
    start, finish = ctx.Event(), ctx.Event()
    children = [
        ctx.Process(target=_contend, args=(name, ready, start, finish, results))
        for _ in range(2)
    ]
    try:
        for child in children:
            child.start()
        for _ in children:
            assert ready.get(timeout=10)
        start.set()
        assert sorted(results.get(timeout=10) for _ in children) == ["busy", "claimed"]
    finally:
        finish.set()
        for child in children:
            child.join(10)
            assert child.exitcode == 0
        _close(keeper, memory)


def test_same_process_second_transport_cannot_take_live_lease():
    name = "Local\\WonderBane.LeaseTest." + uuid.uuid4().hex
    first, memory = _transport(name)
    second, other = _transport(name)
    try:
        first._claim_host_lease()
        with pytest.raises(channel.NativeActionChannelBusy):
            second._claim_host_lease()
        _close(second, other)
        second = None
        assert first._owns_host_lease()
    finally:
        if second is not None:
            _close(second, other)
        _close(first, memory)


def test_expired_generation_cannot_renew_or_close_replacement():
    name = "Local\\WonderBane.LeaseTest." + uuid.uuid4().hex
    first, memory = _transport(name)
    second, other = _transport(name)
    try:
        first._claim_host_lease()
        first._exchange_i64(channel._HOST_HEARTBEAT_TICK_OFFSET, 0)
        second._claim_host_lease()
        assert second._lease_generation == first._lease_generation + 1
        with pytest.raises(channel.NativeActionChannelBusy):
            first._renew_host_lease()
        _close(first, memory)
        first = None
        assert second._owns_host_lease()
        second._renew_host_lease()
    finally:
        if first is not None:
            _close(first, memory)
        _close(second, other)


def test_generation_exhaustion_does_not_reuse_authority():
    name = "Local\\WonderBane.LeaseTest." + uuid.uuid4().hex
    transport, memory = _transport(name)
    try:
        transport._exchange_i32(channel._HOST_LEASE_GENERATION_OFFSET, 2**31 - 1)
        with pytest.raises(channel.NativeActionChannelUnavailable, match="exhausted"):
            transport._claim_host_lease()
        assert transport._lease_generation is None
    finally:
        _close(transport, memory)


def _hold_transaction(name, ready, release):
    kernel = channel._WindowsKernel()
    with kernel.producer_lock(name + ".Producer", 1000):
        ready.set()
        release.wait(30)


def test_expired_lease_cannot_be_claimed_during_other_process_transaction():
    ctx = multiprocessing.get_context("spawn")
    name = "Local\\WonderBane.LeaseTest." + uuid.uuid4().hex
    transport, memory = _transport(name)
    ready, release = ctx.Event(), ctx.Event()
    child = ctx.Process(target=_hold_transaction, args=(name, ready, release))
    try:
        child.start()
        assert ready.wait(10)
        transport._host_lease_timeout_ms = 20
        with pytest.raises(channel.NativeActionChannelBusy, match="transaction"):
            transport._claim_host_lease()
        unrelated, separate = _transport(name + ".OtherClient")
        try:
            unrelated._claim_host_lease()
            assert unrelated._owns_host_lease()
        finally:
            _close(unrelated, separate)
        # Abrupt death of this test-owned process must not strand producer ownership.
        child.terminate()
        child.join(10)
        assert child.exitcode is not None
        transport._claim_host_lease()
        assert transport._owns_host_lease()
    finally:
        if child.exitcode is None:
            release.set()
            child.join(10)
        _close(transport, memory)


def test_unaligned_scalar_is_rejected_before_access():
    kernel = channel._WindowsKernel()
    value = ctypes.c_int64(123)
    with pytest.raises(channel.NativeActionChannelError, match="unaligned"):
        kernel.read_i64(ctypes.addressof(value) + 1)


def test_host_identity_exposes_exact_current_process_lifetime():
    kernel = channel._WindowsKernel()
    first = kernel.process_identity()
    assert first.process_id == kernel.process_id()
    assert first.creation_filetime_utc > 0
    assert kernel.process_identity() == first


def test_city_session_uses_production_transport_and_shared_memory_ring(monkeypatch):
    """The session mock must not hide admission/publication failures in submit()."""
    import itertools
    import struct

    from shadowbane_lab.client_extension.city_window_session import NativeCityWindowSession
    from shadowbane_lab.client_extension.city_window_wire import (
        _RECEIPT,
        MAGIC,
        READY,
        Outcome,
        Snapshot,
        Verb,
    )

    transport, memory = _transport("Local\\WonderBane.CityTransportTest." + uuid.uuid4().hex)
    state = Snapshot(1, 1, 100, 200)
    seen = []
    session = None

    def consume(_event):
        sequence = transport._read_i64(channel._COMMAND_WRITE_SEQUENCE_OFFSET)
        offset = channel.CLIENT_ACTION_COMMAND_RING_OFFSET + (sequence - 1) * 768
        raw = bytes(memory[offset:offset + 768])
        header = channel._COMMAND.unpack(raw[:192])
        assert header[0] == sequence
        verb = Verb(header[2])
        assert header[4] > 0 and header[5] == header[4] + 750
        assert raw[232:296] == (Snapshot() if verb == Verb.INSPECT else state).encode()
        seen.append(verb)
        reply = _RECEIPT.pack(
            raw[216:232], raw[192:208], struct.unpack("<Q", raw[208:216])[0],
            Outcome.OBSERVED if verb == Verb.INSPECT else Outcome.SUBMITTED,
            READY if verb == Verb.INSPECT else 0, state.encode(), MAGIC, bytes(268),
        )
        detail = b"native_city_window_receipt_v1"
        result = channel._RESULT.pack(
            sequence, header[1], sequence,
            channel.NativeActionResultStage.SUBMITTED_TO_CLIENT, 0,
            transport._kernel.tick_count(), 77, len(detail), detail, bytes(8),
        ) + reply
        result_offset = channel.CLIENT_ACTION_RESULT_RING_OFFSET + (sequence - 1) * 512
        memory[result_offset:result_offset + 512] = result
        transport._exchange_i64(channel._COMMAND_READ_SEQUENCE_OFFSET, sequence)
        transport._exchange_i64(channel._RESULT_WRITE_SEQUENCE_OFFSET, sequence)

    try:
        transport._claim_host_lease()
        transport._command_signal = 17  # notification is handled by the fixture peer
        monkeypatch.setattr(transport._kernel, "set_event", consume)
        session = NativeCityWindowSession.__new__(NativeCityWindowSession)
        session.identity = channel.NativeClientProcessIdentity(988, 123)
        session.window = 1000
        session._transport, session._ids, session._closed = transport, itertools.count(1), False
        before = session.inspect()
        assert before.snapshot == state and before.flags == READY
        assert session.open(before.snapshot, str(uuid.uuid4())).outcome == Outcome.SUBMITTED
        assert seen == [Verb.INSPECT, Verb.OPEN]
        assert transport._read_i64(channel._RESULT_READ_SEQUENCE_OFFSET) == 2
        with pytest.raises(ValueError, match="command must be"):
            transport.submit(object(), timeout_ms=750)
        assert transport._read_i64(channel._COMMAND_WRITE_SEQUENCE_OFFSET) == 2
        transport._exchange_i32(channel._HOST_LEASE_GENERATION_OFFSET,
                                transport.host_lease_generation + 1)
        with pytest.raises(channel.NativeActionChannelBusy, match="lease was lost"):
            session.open(before.snapshot, str(uuid.uuid4()))
        assert seen == [Verb.INSPECT, Verb.OPEN]
    finally:
        transport._command_signal = None
        _close(transport, memory)

def test_navigation_session_uses_production_transport_and_shared_memory_ring(monkeypatch):
    """The session mock must not hide admission/publication failures in submit()."""
    import itertools
    import struct

    from shadowbane_lab.client_extension.vendor_navigation_session import (
        NativeVendorNavigationSession,
    )
    from shadowbane_lab.client_extension.vendor_navigation_wire import (
        _RECEIPT,
        MAGIC,
        READY,
        Outcome,
        Snapshot,
        Verb,
    )

    transport, memory = _transport("Local\\WonderBane.NavigationTransportTest." + uuid.uuid4().hex)
    state = Snapshot(1, 1, 100, 200, front_hud=300, mode=6,
                     building_hud=300, visible=1, initialized=1,
                     building_id=123, building_type=8)
    seen = []
    session = None

    def consume(_event):
        sequence = transport._read_i64(channel._COMMAND_WRITE_SEQUENCE_OFFSET)
        offset = channel.CLIENT_ACTION_COMMAND_RING_OFFSET + (sequence - 1) * 768
        raw = bytes(memory[offset:offset + 768])
        header = channel._COMMAND.unpack(raw[:192])
        assert header[0] == sequence
        verb = Verb(header[2])
        assert header[4] > 0 and header[5] == header[4] + 750
        assert raw[232:328] == (Snapshot() if verb == Verb.INSPECT else state).encode()
        if verb == Verb.VENDOR:
            assert struct.unpack("<4I", raw[328:344]) == (123, 8, 777, 42)
        seen.append(verb)
        reply = _RECEIPT.pack(
            raw[216:232], raw[192:208], struct.unpack("<Q", raw[208:216])[0],
            Outcome.OBSERVED if verb == Verb.INSPECT else Outcome.SUBMITTED,
            READY if verb == Verb.INSPECT else 0, state.encode(), bytes(16), MAGIC, bytes(220),
        )
        detail = b"native_vendor_navigation_receipt_v3"
        result = channel._RESULT.pack(
            sequence, header[1], sequence,
            channel.NativeActionResultStage.SUBMITTED_TO_CLIENT, 0,
            transport._kernel.tick_count(), 77, len(detail), detail, bytes(8),
        ) + reply
        result_offset = channel.CLIENT_ACTION_RESULT_RING_OFFSET + (sequence - 1) * 512
        memory[result_offset:result_offset + 512] = result
        transport._exchange_i64(channel._COMMAND_READ_SEQUENCE_OFFSET, sequence)
        transport._exchange_i64(channel._RESULT_WRITE_SEQUENCE_OFFSET, sequence)

    try:
        transport._claim_host_lease()
        transport._command_signal = 17  # notification is handled by the fixture peer
        monkeypatch.setattr(transport._kernel, "set_event", consume)
        session = NativeVendorNavigationSession.__new__(NativeVendorNavigationSession)
        session._parent = None
        session._journal = None
        session.identity = channel.NativeClientProcessIdentity(988, 123)
        session.window = 1000
        session._transport, session._ids, session._closed = transport, itertools.count(1), False
        before = session.inspect()
        assert before.snapshot == state and before.flags == READY
        opened = session.open_building(before.snapshot, 123, str(uuid.uuid4()))
        assert opened.outcome == Outcome.SUBMITTED
        selected = session.open_vendor(before.snapshot, 123, 777, str(uuid.uuid4()))
        assert selected.outcome == Outcome.SUBMITTED
        assert seen == [Verb.INSPECT, Verb.BUILDING, Verb.VENDOR]
        assert transport._read_i64(channel._RESULT_READ_SEQUENCE_OFFSET) == 3
        with pytest.raises(ValueError, match="command must be"):
            transport.submit(object(), timeout_ms=750)
        assert transport._read_i64(channel._COMMAND_WRITE_SEQUENCE_OFFSET) == 3
        transport._exchange_i32(channel._HOST_LEASE_GENERATION_OFFSET,
                                transport.host_lease_generation + 1)
        with pytest.raises(channel.NativeActionChannelBusy, match="lease was lost"):
            session.open_building(before.snapshot, 123, str(uuid.uuid4()))
        assert seen == [Verb.INSPECT, Verb.BUILDING, Verb.VENDOR]
    finally:
        transport._command_signal = None
        _close(transport, memory)


def test_borrowed_vendor_menu_workflow_uses_production_transport_and_ring(monkeypatch):
    """Exercise admission and publication for every menu verb without a game."""
    import itertools
    import struct
    from dataclasses import replace

    from shadowbane_lab.client_extension.vendor_menu_wire import (
        _RECEIPT,
        MAGIC,
        RANDOM_SENTINEL,
        READY,
        Host,
        Outcome,
        Snapshot,
        Verb,
    )
    from shadowbane_lab.client_extension.vendor_session import NativeVendorSession

    transport, memory = _transport("Local\\WonderBane.VendorMenuTransport." + uuid.uuid4().hex)
    initial = Snapshot(1, 1, 100, 200, front_hud=300, menu=300,
                       hireling=400, building=500, vendor=600)
    state, seen = initial, []

    def consume(_event):
        nonlocal state
        sequence = transport._read_i64(channel._COMMAND_WRITE_SEQUENCE_OFFSET)
        offset = channel.CLIENT_ACTION_COMMAND_RING_OFFSET + (sequence - 1) * 768
        raw = bytes(memory[offset:offset + 768])
        header = channel._COMMAND.unpack(raw[:192])
        verb = Verb(header[2])
        assert header[0] == sequence and header[5] == header[4] + 750
        assert Snapshot.decode(raw[232:328]) == (Snapshot() if verb == Verb.INSPECT else state)
        identity = transport.host_process_identity
        assert Host.decode(raw[192:208]) == Host(
            identity.process_id, transport.host_lease_generation, identity.creation_filetime_utc)
        template = struct.unpack("<I", raw[328:332])[0]
        assert template == (777 if verb in (Verb.SELECT_RECIPE, Verb.SELECT_ORDER_RECIPE)
                            else 10 if verb == Verb.ORDER_QUANTITY else 0)
        seen.append(verb)
        if verb in (Verb.OPEN_RECIPE, Verb.OPEN_ORDER_RECIPE):
            state = replace(state, front_hud=700, recipe=700, recipe_list=710,
                            sentinel=RANDOM_SENTINEL, quantity=1,
                            multiple=int(verb == Verb.OPEN_ORDER_RECIPE))
        elif verb in (Verb.SELECT_RECIPE, Verb.SELECT_ORDER_RECIPE):
            state = replace(state, item_template=777, selected_template=777, activated_template=777)
        elif verb in (Verb.RANDOM_MODE, Verb.RANDOM_ORDER_MODE):
            state = replace(state, mode=1, table=57, quantity=1,
                            prefix=RANDOM_SENTINEL, suffix=RANDOM_SENTINEL)
        elif verb == Verb.CLOSE_RECIPE:
            state = initial
        elif verb == Verb.OPEN_INVENTORY:
            state = replace(state, front_hud=800, inventory=800)
        elif verb == Verb.CLOSE_INVENTORY:
            state = initial
        elif verb == Verb.ORDER_QUANTITY:
            state = replace(state, quantity=template)
        reply = _RECEIPT.pack(
            raw[216:232], raw[192:208], struct.unpack("<Q", raw[208:216])[0],
            Outcome.OBSERVED if verb == Verb.INSPECT else Outcome.SUBMITTED,
            READY if verb == Verb.INSPECT else 0, state.encode(), bytes(16), MAGIC, bytes(220))
        detail = b"native_vendor_menu_receipt_v1"
        result = channel._RESULT.pack(
            sequence, header[1], sequence, channel.NativeActionResultStage.SUBMITTED_TO_CLIENT,
            0, transport._kernel.tick_count(), 77, len(detail), detail, bytes(8)) + reply
        result_offset = channel.CLIENT_ACTION_RESULT_RING_OFFSET + (sequence - 1) * 512
        memory[result_offset:result_offset + 512] = result
        transport._exchange_i64(channel._COMMAND_READ_SEQUENCE_OFFSET, sequence)
        transport._exchange_i64(channel._RESULT_WRITE_SEQUENCE_OFFSET, sequence)

    try:
        transport._claim_host_lease()
        transport._command_signal = 17
        monkeypatch.setattr(transport._kernel, "set_event", consume)
        parent = NativeVendorSession.__new__(NativeVendorSession)
        parent.identity, parent.window = channel.NativeClientProcessIdentity(988, 123), 1000
        parent._transport, parent._ids, parent._closed = transport, itertools.count(1), False
        menu = parent.menu_session()
        before = menu.inspect()
        opened = menu.open_recipe(before.snapshot, str(uuid.uuid4()))
        selected = menu.select_recipe(opened.snapshot, 777, str(uuid.uuid4()))
        randomized = menu.random_mode(selected.snapshot, str(uuid.uuid4()))
        assert randomized.snapshot.random_recipe(777, 57)
        closed = menu.close_recipe(randomized.snapshot, str(uuid.uuid4()))
        inventory = menu.open_inventory(closed.snapshot, str(uuid.uuid4()))
        closed_inventory = menu.close_inventory(inventory.snapshot, str(uuid.uuid4()))
        opened_order = menu.open_order_recipe(closed_inventory.snapshot, str(uuid.uuid4()))
        selected_order = menu.select_order_recipe(opened_order.snapshot, 777, str(uuid.uuid4()))
        random_order = menu.random_order_mode(selected_order.snapshot, str(uuid.uuid4()))
        ten = menu.order_quantity(random_order.snapshot, 10, str(uuid.uuid4()))
        assert ten.snapshot.random_order(777, 57, 10, True)
        assert seen == list(Verb)
        assert transport._read_i64(channel._RESULT_READ_SEQUENCE_OFFSET) == 11
        menu.close()
        assert transport._owns_host_lease()  # the parent still owns the producer
        with pytest.raises(ValueError, match="command must be"):
            transport.submit(object(), timeout_ms=750)
        transport._exchange_i32(channel._HOST_LEASE_GENERATION_OFFSET,
                                transport.host_lease_generation + 1)
        with pytest.raises(channel.NativeActionChannelBusy, match="lease was lost"):
            parent.menu_session().open_recipe(initial, str(uuid.uuid4()))
        assert seen == list(Verb)
        assert transport._read_i64(channel._COMMAND_WRITE_SEQUENCE_OFFSET) == 11
    finally:
        transport._command_signal = None
        _close(transport, memory)


def test_vendor_funding_adapters_share_actual_ring_lease_and_sequence(monkeypatch):
    import itertools
    import struct
    from types import SimpleNamespace

    from shadowbane_lab.client_extension import (
        guard_funding_wire as gold,
    )
    from shadowbane_lab.client_extension import (
        vendor_navigation_wire as nav,
    )
    from shadowbane_lab.client_extension.guard_funding_session import NativeGuardFundingSession
    from shadowbane_lab.client_extension.vendor_navigation_session import (
        NativeVendorNavigationSession,
    )

    transport, memory = _transport("Local\\WonderBane.VendorFunding." + uuid.uuid4().hex)
    seen = []
    states = {
        int(gold.Verb.INSPECT): (gold, gold.Snapshot(
            scene=1, revision=1, root=100, actor=900,
            character_id=11, character_type=53, manager=200, hud=300, source_object=400,
            source_id=500, source_type=42, direction=1, resource=555, balance=1000, reserve=100)),
        int(nav.Verb.INSPECT): (nav, nav.Snapshot(scene=1, revision=1, root=100, manager=200)),
    }

    def consume(_event):
        sequence = transport._read_i64(channel._COMMAND_WRITE_SEQUENCE_OFFSET)
        offset = channel.CLIENT_ACTION_COMMAND_RING_OFFSET + (sequence - 1) * 768
        raw = bytes(memory[offset:offset + 768])
        header = channel._COMMAND.unpack(raw[:192])
        codec, state = states[header[2]]
        seen.append((header[1], header[2], raw[192:208]))
        reply = codec._RECEIPT.pack(raw[216:232], raw[192:208],
            struct.unpack('<Q', raw[208:216])[0], codec.Outcome.OBSERVED,
            codec.READY, state.encode(), bytes(16), codec.MAGIC, bytes(220))
        detail = (b'native_guard_funding_receipt_v1' if codec is gold
                  else b'native_vendor_navigation_receipt_v3')
        result = channel._RESULT.pack(sequence, header[1], sequence,
            channel.NativeActionResultStage.SUBMITTED_TO_CLIENT, 0,
            transport._kernel.tick_count(), 77, len(detail), detail, bytes(8)) + reply
        result_offset = channel.CLIENT_ACTION_RESULT_RING_OFFSET + (sequence - 1) * 512
        memory[result_offset:result_offset + 512] = result
        transport._exchange_i64(channel._COMMAND_READ_SEQUENCE_OFFSET, sequence)
        transport._exchange_i64(channel._RESULT_WRITE_SEQUENCE_OFFSET, sequence)

    try:
        transport._claim_host_lease()
        transport._command_signal = 17
        monkeypatch.setattr(transport._kernel, 'set_event', consume)
        parent = SimpleNamespace(identity=channel.NativeClientProcessIdentity(988,123),window=1000,
                                 _transport=transport,_ids=itertools.count(1),_closed=False)
        funding = NativeGuardFundingSession.borrow(parent, journal=None)
        navigation = NativeVendorNavigationSession.borrow(parent, journal=None)
        funding.inspect(gold.Direction.WAREHOUSE)
        navigation.inspect()
        funding.inspect(gold.Direction.WAREHOUSE)
        assert [row[0] for row in seen] == [1,2,3]
        assert len({row[2] for row in seen}) == 1
        navigation.close()
        assert transport._owns_host_lease()
        parent._closed = True
        with pytest.raises(channel.NativeActionChannelUnavailable):
            funding.inspect(gold.Direction.WAREHOUSE)
        with pytest.raises(channel.NativeActionChannelUnavailable):
            funding.renew_lease()
        funding.close()
        assert transport._owns_host_lease()
        assert len(seen) == 3
    finally:
        transport._command_signal = None
        _close(transport, memory)


def test_expired_lease_records_timing_without_renewing(monkeypatch):
    transport, memory = _transport("Local\\WonderBane.LeaseTiming." + uuid.uuid4().hex)
    try:
        transport._claim_host_lease()
        transport._exchange_i64(channel._HOST_HEARTBEAT_TICK_OFFSET, 3990)
        ticks = iter((5000, 5005))
        monkeypatch.setattr(transport._kernel, "tick_count", lambda: next(ticks))
        with pytest.raises(channel.NativeActionChannelBusy, match="lease expired") as caught:
            transport.renew_lease()
        assert caught.value.__notes__ == ["heartbeat_age_ms=1015; renewal_wait_ms=5"]
        assert transport._read_i64(channel._HOST_HEARTBEAT_TICK_OFFSET) == 3990
    finally:
        _close(transport, memory)
