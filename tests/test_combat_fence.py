"""Production store/mapping races; optional Win32 native consumer interop."""
from __future__ import annotations

import json
import multiprocessing
import os
import queue
import subprocess
import threading
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from shadowbane_lab.client_extension.combat_fence import Binding, State
from shadowbane_lab.client_extension.combat_fence_windows import FenceError, Ticket, Windows
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.pve.attack_list import (
    AttackListEntry,
    AttackListOwner,
    AttackListStore,
    AttackPlayerIdentity,
    AttackTargetObservation,
)
from shadowbane_lab.pve.attack_list_commands import apply_attack_list_command
from shadowbane_lab.pve.attack_list_fence import Registry

OWNER = AttackListOwner("test-server", "test-character")
LOCAL = NativeObjectKey(91, 53)
TARGET = NativeObjectKey(92, 53)
WINDOWS = pytest.mark.skipif(os.name != "nt", reason="Windows kernel admission objects")


def entry(source="manual"):
    identity = AttackPlayerIdentity(OWNER.server, TARGET, "Enemy")
    observation = AttackTargetObservation("a" * 64, 123, 456, LOCAL, TARGET, "player")
    return AttackListEntry(identity.entry_id, "Enemy", source, "test", observation, identity)


def store_at(root):
    store = AttackListStore(root, OWNER)
    store.add(entry())
    return store


def register(store, client=None, **changes):
    if client is None:
        client = Windows().identity()
    args = dict(expected_revision=store.snapshot().revision, client_pid=client[0],
                client_creation=client[1], producer_generation=7, movement_generation=8,
                scene=9, operation=b"o" * 32, local_key=LOCAL)
    args.update(changes)
    return store.register_admission(entry().entry_id, **args)


def test_shared_fixture_roundtrip():
    payload = bytes.fromhex((Path(__file__).parent / "fixtures/combat_fence_v1.hex").read_text())
    binding, state = Binding.decode(payload)
    assert state == State.REGISTERING
    assert binding.encode() == payload
    assert binding.revision == 19 and binding.target_key == (92, 53)
    for offset in (0, 8, 12, 20, 319):
        corrupt = bytearray(payload)
        corrupt[offset] ^= 128
        with pytest.raises(ValueError):
            Binding.decode(bytes(corrupt))


@WINDOWS
def test_store_admission_is_current_manual_player_intent(tmp_path):
    store = store_at(tmp_path)
    with register(store) as ticket:
        assert ticket.state() == State.PENDING
        assert ticket.binding.owner == bytes.fromhex(OWNER.storage_key)
        with pytest.raises(ValueError):
            register(store, expected_revision=2)
        with pytest.raises(FenceError):
            register(store, client=(os.getpid(), 1))
        assert store.add(entry()).revision == 1  # no-op does not revoke
        assert ticket.state() == State.PENDING
        assert not store.remove(entry().entry_id).entries
        assert ticket.state() == State.REVOKED
    with pytest.raises(ValueError):
        register(store, expected_revision=2)
    store.add(entry("response"))
    with pytest.raises(ValueError):
        register(store)


@WINDOWS
def test_publish_failure_revokes_without_changing_saved_intent(tmp_path):
    store = store_at(tmp_path)
    before = store.snapshot()
    with register(store) as ticket:
        with patch("shadowbane_lab.pve.attack_list.publish_atomic_record", side_effect=OSError):
            with pytest.raises(OSError):
                store.clear()
        assert store.snapshot() == before
        assert ticket.state() == State.REVOKED
        with pytest.raises(FenceError):
            ticket.arm()
        with register(store) as replacement:
            assert replacement.binding.request != ticket.binding.request
            assert replacement.state() == State.PENDING


@WINDOWS
def test_registration_publication_failure_never_arms(tmp_path):
    store = store_at(tmp_path)
    with patch("shadowbane_lab.pve.attack_list_fence.publish_atomic_record", side_effect=OSError):
        with pytest.raises(OSError):
            register(store)
    assert not Registry(store.path, OWNER.storage_key).path.exists()
    assert store.snapshot().revision == 1


@WINDOWS
def test_corrupt_or_inaccessible_live_ticket_blocks_publication(tmp_path):
    store = store_at(tmp_path)
    with register(store) as ticket:
        registry = Registry(store.path, OWNER.storage_key)
        good = registry.path.read_bytes()
        registry.path.write_bytes(b"broken")
        with pytest.raises(ValueError):
            store.clear()
        registry.path.write_bytes(good)
        with patch("shadowbane_lab.pve.attack_list_fence.Ticket", side_effect=PermissionError):
            with pytest.raises(PermissionError):
                store.clear()
        assert store.snapshot().revision == 1
        assert ticket.state() == State.PENDING


@WINDOWS
def test_missing_mapping_retired_and_capacity_fails_closed(tmp_path):
    store = store_at(tmp_path)
    ticket = register(store)
    ticket.close()
    with register(store) as active:
        registry = Registry(store.path, OWNER.storage_key)
        assert len(registry._read()) == 1
        with patch("shadowbane_lab.pve.attack_list_fence.CAPACITY", 1):
            with pytest.raises(FenceError, match="full"):
                register(store)
        assert active.state() == State.PENDING
    assert not store.clear().entries


@WINDOWS
def test_user_protected_security_descriptor():
    # Verify actual SDDL, not a mocked security attribute. A different user receives
    # no ACE; administrators with privilege override are outside this trust model.
    import ctypes as c
    api = Windows()
    convert = api.a.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = [c.c_void_p, c.c_uint32, c.c_uint32,
                        c.POINTER(c.c_void_p), c.c_void_p]
    convert.restype = c.c_int
    with api.security() as security:
        output = c.c_void_p()
        try:
            assert convert(security.descriptor, 1, 4, c.byref(output), None)
            sddl = c.wstring_at(output)
            assert sddl.startswith("D:P(A;;GA;;;S-1-5-21-")
            assert sddl.count("(") == 1
            assert not security.inherit
        finally:
            api.k.LocalFree(output)


class NativeConsumer:
    def __init__(self, executable):
        self.process = subprocess.Popen([executable, "--consumer"], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, text=True)
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.identity = tuple(map(int, self.receive().split()))

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line.strip())
        self.lines.put("EOF")

    def receive(self):
        return self.lines.get(timeout=10)

    def send(self, text):
        self.process.stdin.write(text + "\n")
        self.process.stdin.flush()

    def command(self, text):
        self.send(text)
        return self.receive()

    def open(self, binding):
        assert self.command(binding.encode().hex()) == "open"

    def close(self):
        self.process.stdin.close()
        try:
            assert self.process.wait(timeout=10) == 0
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait()
            self.process.stdout.close()
            self.reader.join(5)


@pytest.fixture
def native():
    path = os.environ.get("SHADOWBANE_COMBAT_FENCE_TEST_EXE")
    if not path:
        pytest.skip("set SHADOWBANE_COMBAT_FENCE_TEST_EXE to built Win32 native fence test")
    assert Path(path).is_file()
    result = NativeConsumer(path)
    try:
        yield result
    finally:
        result.close()


@WINDOWS
def test_native_entry_once_then_mutation_requires_cancellation(tmp_path, native):
    store = store_at(tmp_path)
    with register(store, native.identity) as ticket:
        native.open(ticket.binding)
        assert native.command("wrong-generation") == "3"
        assert ticket.state() == State.PENDING
        with ticket.locked():
            assert native.command("enter") == "1"  # zero-wait busy
        assert native.command("enter") == "0"
        assert native.command("enter") == "4"  # no duplicate admission
        result = apply_attack_list_command("/blacklist clear", store)
        assert result["entered_admissions_requiring_cancellation"] == [ticket.binding.request.hex()]
        assert native.command("inspect") == "5 4"
        assert native.command("enter") == "5"


@WINDOWS
def test_native_revocation_wins_and_immutable_binding_rejected(tmp_path, native):
    store = store_at(tmp_path)
    with register(store, native.identity) as ticket:
        native.open(replace(ticket.binding, owner=b"z" * 32))
        assert native.command("enter") == "3"
        assert ticket.state() == State.PENDING
        store.clear()
        assert ticket.state() == State.REVOKED


def _hold_mutex(encoded, ready, release=None):
    binding, _ = Binding.decode(bytes.fromhex(encoded))
    ticket = Ticket(binding)
    try:
        with ticket.locked():
            ready.put(True)
            (release or threading.Event()).wait(120)
    finally:
        ticket.close(revoke=False)


def _clear(root, ready, release, result):
    store = AttackListStore(root, OWNER)
    ready.put(True)
    if not release.wait(15):
        raise RuntimeError("clear release timed out")
    saved = store.clear()
    result.put((saved.revision, saved.entered_admissions))


def _producer(root, client, ready, release, crash_stage=None):
    store = AttackListStore(root, OWNER)
    if crash_stage == "registered":
        original = Registry._write
        def paused(self, bindings):
            original(self, bindings)
            ready.put(bindings[-1].encode().hex())
            if not release.wait(20):
                raise RuntimeError("producer release timed out")
        Registry._write = paused
    with register(store, client) as ticket:
        ready.put(ticket.binding.encode().hex())
        release.wait(20)


def stop(child):
    if child.is_alive():
        child.terminate()
    child.join(10)
    assert not child.is_alive()


@WINDOWS
def test_abandoned_mutex_revokes_native_admission(tmp_path, native):
    store = store_at(tmp_path)
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    with register(store, native.identity) as ticket:
        native.open(ticket.binding)
        child = context.Process(target=_hold_mutex, args=(ticket.binding.encode().hex(), ready))
        child.start()
        try:
            assert ready.get(timeout=15)
            assert native.command("enter") == "1"
            stop(child)
            assert native.command("enter") == "5"
            assert ticket.state() == State.REVOKED
        finally:
            stop(child)
            ready.close()


@WINDOWS
@pytest.mark.parametrize("stage", [None, "registered"])
def test_crash_before_or_after_arm_cannot_authorize(tmp_path, native, stage):
    store_at(tmp_path)
    context = multiprocessing.get_context("spawn")
    ready, release = context.Queue(), context.Event()
    child = context.Process(target=_producer,
                            args=(tmp_path, native.identity, ready, release, stage))
    child.start()
    try:
        binding, _ = Binding.decode(bytes.fromhex(ready.get(timeout=15)))
        native.open(binding)  # retains both objects and exact producer process handle
        if stage == "registered":
            assert native.command("enter") == "4"
        stop(child)
        assert native.command("enter") == "5"
        assert not AttackListStore(tmp_path, OWNER).clear().entries
    finally:
        stop(child)
        ready.close()


@WINDOWS
def test_mutation_waits_for_registration_then_revokes(tmp_path, native):
    store_at(tmp_path)
    context = multiprocessing.get_context("spawn")
    ready, registered = context.Queue(), context.Event()
    producer = context.Process(target=_producer,
        args=(tmp_path, native.identity, ready, registered, "registered"))
    mutation_ready, go, result = context.Queue(), context.Event(), context.Queue()
    mutator = context.Process(target=_clear, args=(tmp_path, mutation_ready, go, result))
    producer.start()
    try:
        binding, _ = Binding.decode(bytes.fromhex(ready.get(timeout=15)))
        native.open(binding)
        mutator.start()
        assert mutation_ready.get(timeout=15)
        go.set()
        assert native.command("enter") == "4"  # registry durable, not armed yet
        registered.set()
        ready.get(timeout=15)
        assert result.get(timeout=15)[0] == 2
        assert native.command("enter") == "5"
        mutator.join(10)
        assert mutator.exitcode == 0
    finally:
        stop(producer)
        if mutator.pid:
            stop(mutator)
        for item in (ready, mutation_ready, result):
            item.close()


@WINDOWS
def test_real_process_entry_mutation_race_has_one_winner(tmp_path, native):
    store = store_at(tmp_path)
    context = multiprocessing.get_context("spawn")
    ready, release, result = context.Queue(), context.Event(), context.Queue()
    with register(store, native.identity) as ticket:
        native.open(ticket.binding)
        child = context.Process(target=_clear, args=(tmp_path, ready, release, result))
        child.start()
        try:
            assert ready.get(timeout=15)
            release.set()
            entered = native.command("enter")
            revision, cancellations = result.get(timeout=15)
            assert revision == 2
            if entered == "0":
                assert cancellations == (ticket.binding.request.hex(),)
                assert ticket.state() == State.ENTERED_REVOKED
            else:
                assert entered in {"1", "5"}
                assert not cancellations
                assert ticket.state() == State.REVOKED
            child.join(10)
            assert child.exitcode == 0
        finally:
            stop(child)
            ready.close()
            result.close()


def _crash_mutation(root, ready):
    def hold_publication(*args, **kwargs):
        ready.put(True)
        threading.Event().wait(120)
    with patch("shadowbane_lab.pve.attack_list.publish_atomic_record", hold_publication):
        AttackListStore(root, OWNER).clear()


@WINDOWS
def test_mutator_crash_after_revocation_preserves_old_list_without_old_authority(tmp_path, native):
    store = store_at(tmp_path)
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    with register(store, native.identity) as ticket:
        native.open(ticket.binding)
        child = context.Process(target=_crash_mutation, args=(tmp_path, ready))
        child.start()
        try:
            assert ready.get(timeout=15)
            assert native.command("enter") == "5"
            stop(child)
            assert store.snapshot().revision == 1
            assert store.snapshot().entries == (entry(),)
            assert ticket.state() == State.REVOKED
            assert store.clear().revision == 2
        finally:
            stop(child)
            ready.close()


@WINDOWS
def test_store_scope_and_mapping_reuse_are_rejected(tmp_path):
    store = store_at(tmp_path / "one")
    other = store_at(tmp_path / "two")
    with register(store) as ticket:
        with pytest.raises(FenceError, match="already exists"):
            Ticket(ticket.binding, create=True)
        assert ticket.state() == State.PENDING
        with register(other) as second:
            assert second.binding.store != ticket.binding.store
            other.clear()
            assert second.state() == State.REVOKED
            assert ticket.state() == State.PENDING


@WINDOWS
def test_failed_close_retains_handles_for_revocation_retry(tmp_path, native):
    store = store_at(tmp_path)
    context = multiprocessing.get_context("spawn")
    ready, release = context.Queue(), context.Event()
    ticket = register(store, native.identity)
    native.open(ticket.binding)
    child = context.Process(target=_hold_mutex,
                            args=(ticket.binding.encode().hex(), ready, release))
    child.start()
    try:
        assert ready.get(timeout=15)
        with pytest.raises(FenceError, match="busy"):
            ticket.close(timeout_ms=20)
        assert ticket.view and ticket.mapping and ticket.mutex
        assert native.command("enter") == "1"
        release.set()
        child.join(10)
        assert child.exitcode == 0
        assert ticket.state() == State.PENDING
        ticket.close()
        assert not ticket.view and not ticket.mapping and not ticket.mutex
        assert native.command("enter") == "5"
    finally:
        release.set()
        stop(child)
        ticket.close()
        ready.close()


@WINDOWS
def test_first_admission_migrates_record_to_exclude_unfenced_legacy_writers(tmp_path):
    store = store_at(tmp_path)
    assert json.loads(store.path.read_bytes())["schema"] == 3
    before = store.snapshot()
    with register(store):
        raw = json.loads(store.path.read_bytes())
        # The prior production reader explicitly accepts only (1, 2, 3).
        assert raw["schema"] == 4 and raw["schema"] not in (1, 2, 3)
        assert store.snapshot() == before
        assert store.snapshot().fenced
    store.clear()
    assert json.loads(store.path.read_bytes())["schema"] == 4
    assert AttackListStore(tmp_path, OWNER).snapshot().fenced


@WINDOWS
def test_migration_failure_never_registers_or_arms(tmp_path):
    store = store_at(tmp_path)
    with patch("shadowbane_lab.pve.attack_list.publish_atomic_record", side_effect=OSError):
        with pytest.raises(OSError):
            register(store)
    assert not Registry(store.path, OWNER.storage_key).path.exists()
    assert json.loads(store.path.read_bytes())["schema"] == 3
    assert not store.snapshot().fenced
