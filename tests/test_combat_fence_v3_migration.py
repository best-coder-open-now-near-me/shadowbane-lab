"""Real Windows ticket authority, durable-list migration and publication races."""
import ctypes as c
import hashlib
import json
import os
import threading
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch

import pytest
from test_combat_fence import LOCAL, OWNER, entry, register, store_at

from shadowbane_lab.client_extension.combat_fence import Binding as LegacyBinding
from shadowbane_lab.client_extension.combat_fence_v3 import Authority, EngagementId, State
from shadowbane_lab.client_extension.combat_fence_windows import (
    FenceError,
    Ticket,
    Windows,
    create_npc_engagement,
)
from shadowbane_lab.client_extension.combat_wire_v2 import identity_digest, operation_digest
from shadowbane_lab.client_extension.movement_wire import Grant, Host, Owner
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.pve.attack_list_fence import Registry

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows kernel engagement mappings")


def legacy_binding(store, **changes):
    api = Windows()
    pid, creation = api.identity()
    registry = Registry(store.path, OWNER.storage_key)
    binding = LegacyBinding(pid, pid, creation, creation, 7, 8, 9, 1,
                            bytes.fromhex("12345678901234567890123456789012"),
                            registry.store, registry.owner, bytes.fromhex(entry().entry_id),
                            operation_digest(Grant(8, 9, Owner.AUTOMATION, "test", "legacy")),
                            (91, 53), (92, 53), identity_digest("Enemy"))
    return replace(binding, **changes)


def legacy_index(store, binding):
    registry = Registry(store.path, OWNER.storage_key)
    registry.path.write_text(json.dumps({"schema": 1, "store": registry.store.hex(),
                                        "tickets": [binding.encode().hex()]}), encoding="utf-8")
    return registry


@contextmanager
def legacy_mapping(binding):
    # An old-format mapping exists only as retirement evidence. No production
    # v2 Ticket is opened or admitted by this test or the migration code.
    api = Windows()
    with api.security() as security:
        mapping = api.checked(api.k.CreateFileMappingW(c.c_void_p(-1), c.byref(security),
                                                       4, 0, 320, binding.name), "create legacy")
    try:
        view = api.checked(api.k.MapViewOfFile(mapping, 6, 0, 0, 320), "map legacy")
        try:
            c.memmove(view, binding.encode(), 320)
            yield
        finally:
            api.k.UnmapViewOfFile(view)
    finally:
        api.k.CloseHandle(mapping)


def test_live_legacy_mapping_blocks_mutation_and_new_registration(tmp_path):
    store = store_at(tmp_path)
    binding = legacy_binding(store)
    registry = legacy_index(store, binding)
    before = store.path.read_bytes()
    with legacy_mapping(binding):
        assert Windows().mapping_exists(binding.name)
        for mutate in (store.clear, lambda: register(store)):
            with pytest.raises(FenceError, match="live v2"):
                mutate()
            assert store.path.read_bytes() == before
            assert json.loads(registry.path.read_bytes())["schema"] == 1
    with register(store) as ticket:
        assert ticket.state() is State.PENDING
        raw = json.loads(registry.path.read_bytes())
        assert raw["schema"] == 2 and len(raw["tickets"]) == 1
        assert store.path.read_bytes() == before


def test_exact_dead_client_reference_retires_even_if_legacy_mapping_remains(tmp_path):
    store = store_at(tmp_path)
    _, creation = Windows().identity()
    binding = legacy_binding(store, client_creation=creation + 1)
    registry = legacy_index(store, binding)
    with legacy_mapping(binding), register(store) as ticket:
        assert ticket.state() is State.PENDING
        assert len(registry._read()) == 1
        assert registry._read()[0].digest == ticket.binding.digest


def test_legacy_registry_wrong_owner_is_not_dropped_as_absent(tmp_path):
    store = store_at(tmp_path)
    legacy_index(store, legacy_binding(store, owner=b"x" * 32))
    before = store.path.read_bytes()
    with pytest.raises(FenceError, match="owner mismatch"):
        store.clear()
    assert store.path.read_bytes() == before


def test_new_records_reject_previous_editors_and_use_complete_registry_identity(tmp_path):
    store = store_at(tmp_path)
    assert json.loads(store.path.read_bytes())["schema"] == 5
    with register(store) as ticket:
        registry = Registry(store.path, OWNER.storage_key)
        raw = json.loads(registry.path.read_bytes())
        assert raw["schema"] == 2
        assert bytes.fromhex(raw["tickets"][0]) == ticket.binding.encode()
        assert ticket.binding.name.endswith(hashlib.sha256(ticket.binding.encode()).hexdigest())
        with ticket.locked():
            ticket._state(State.ENTERED)
        changed = store.clear()
        assert changed.entered_admissions == (ticket.binding.digest.hex(),)
        assert ticket.state() is State.ENTERED_REVOKED


def test_npc_uses_same_protected_ticket_without_saved_list_metadata(tmp_path):
    pid, creation = Windows().identity()
    host, grant = Host(pid, 7, creation), Grant(8, 9, Owner.AUTOMATION, "test", "npc")
    ticket, binding = create_npc_engagement(
        client_pid=pid, client_creation=creation, host=host, grant=grant,
        local_key=LOCAL, target_key=NativeObjectKey(2001, 37),
        owner_digest=bytes.fromhex(OWNER.storage_key), engagement=EngagementId(1),
        actor_address_hint=0x12300000, target_address_hint=0x12400000,
    )
    try:
        assert binding.authority is Authority.NPC and binding.revision == 0
        assert not any(binding.store + binding.entry + binding.target_name)
        assert ticket.state() is State.PENDING
        consumer = Ticket(binding)
        try:
            assert consumer.state() is State.PENDING
            ticket.revoke()
            assert consumer.state() is State.REVOKED
        finally:
            consumer.close(revoke=False)
        assert list(tmp_path.iterdir()) == []
    finally:
        ticket.close()


def test_registration_lock_orders_later_mutation_after_ticket_publication(tmp_path):
    store = store_at(tmp_path)
    original = Registry.register
    started, finished = threading.Event(), threading.Event()
    errors = []
    worker = None

    def mutate():
        started.set()
        try:
            store.clear(expected_revision=1)
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()

    def register_under_lock(registry, binding):
        nonlocal worker
        worker = threading.Thread(target=mutate)
        worker.start()
        assert started.wait(2)
        assert not finished.wait(0.03)
        ticket = original(registry, binding)
        assert ticket.state() is State.PENDING
        return ticket

    ticket = None
    try:
        with patch.object(Registry, "register", register_under_lock):
            ticket = register(store)
        assert finished.wait(3)
        assert not errors
        assert ticket.state() is State.REVOKED
        assert not store.snapshot().entries
    finally:
        if worker is not None:
            worker.join(3)
        if ticket is not None:
            ticket.close()


def test_failed_registry_publication_closes_unarmed_new_mapping(tmp_path):
    store = store_at(tmp_path)
    names = []
    original = Ticket.__init__

    def capture(ticket, binding, **kwargs):
        names.append(binding.name)
        original(ticket, binding, **kwargs)

    with patch.object(Ticket, "__init__", capture), patch.object(Registry, "_write",
                                                               side_effect=OSError("publish")):
        with pytest.raises(OSError, match="publish"):
            register(store)
    assert len(names) == 1 and not Windows().mapping_exists(names[0])
    assert store.snapshot().revision == 1
    assert not Registry(store.path, OWNER.storage_key).path.exists()
