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
