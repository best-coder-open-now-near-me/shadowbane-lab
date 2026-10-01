"""Manual-list mutation revokes only exact v4 children under the durable record lock."""

import json
import os
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest
from test_actor_action_wire import fixture

from shadowbane_lab.client_extension.actor_action_fence import ContextId, State, Ticket
from shadowbane_lab.client_extension.combat_fence_windows import FenceError, Windows
from shadowbane_lab.client_extension.combat_wire_v2 import identity_digest
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.pve.attack_list import (
    AttackListEntry,
    AttackListOwner,
    AttackListStore,
    AttackPlayerIdentity,
    AttackTargetObservation,
)
from shadowbane_lab.pve.attack_list_fence import ActorRegistry


@pytest.fixture
def saved(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows protected fence objects")
    p, _, _, _ = fixture()
    pid, created = Windows().identity()
    store = AttackListStore(tmp_path, AttackListOwner("Wonderbane", "Umbra"))
    identity = AttackPlayerIdentity("Wonderbane", NativeObjectKey(1234, 53), "Day")
    observation = AttackTargetObservation(
        "a" * 64, pid, created, NativeObjectKey(*p.actor_key), identity.object_key, "player"
    )
    entry = AttackListEntry(
        identity.entry_id, identity.name, "manual", "explicit", observation, identity
    )
    snapshot = store.add(entry)
    parent = replace(
        p,
        client_pid=pid,
        producer_pid=pid,
        client_creation=created,
        producer_creation=created,
        owner=bytes.fromhex(store.owner.storage_key),
        local_name=identity_digest("Umbra"),
        server=identity_digest("Wonderbane"),
        producer_generation=int.from_bytes(os.urandom(4), "little") or 1,
    )
    with Ticket(parent, create=True) as owner:
        owner.arm()
        yield store, entry, snapshot, parent, owner


def register(saved):
    store, entry, snapshot, parent, _ = saved
    return store.register_actor_context(
        entry.entry_id,
        expected_revision=snapshot.revision,
        parent=parent,
        context_id=ContextId(1),
        target_hint=0x12400000,
    )


def test_schema_migration_preserves_intent_and_revision_then_removal_revokes_child(saved):
    store, entry, before, parent, owner = saved
    ticket, binding = register(saved)
    try:
        after = store.snapshot()
        assert after.entries == before.entries and after.revision == before.revision
        assert after.actor_fenced and json.loads(store.path.read_bytes())["schema"] == 6
        assert ticket.state() is State.PENDING
        with ticket.locked():
            ticket._state(State.ENTERED)
        result = store.remove(entry.entry_id)
        assert result.entered_admissions == (binding.digest.hex(),)
        assert ticket.state() is State.ENTERED_REVOKED
        assert owner.state() is State.PENDING
        assert json.loads(store.path.read_bytes())["schema"] == 6
    finally:
        ticket.close()


def test_failed_record_publish_leaves_revoked_child_and_original_user_intent(saved):
    store, entry, before, _, owner = saved
    ticket, _ = register(saved)
    try:
        with patch(
            "shadowbane_lab.pve.attack_list.publish_atomic_record", side_effect=OSError("disk")
        ):
            with pytest.raises(OSError):
                store.clear()
        assert store.snapshot().entries == before.entries
        assert ticket.state() is State.REVOKED and owner.state() is State.PENDING
    finally:
        ticket.close()


def test_stale_revision_or_foreign_parent_cannot_publish(saved):
    store, entry, before, parent, _ = saved
    with pytest.raises(ValueError, match="current"):
        store.register_actor_context(
            entry.entry_id,
            expected_revision=before.revision + 1,
            parent=parent,
            context_id=ContextId(1),
            target_hint=0x12400000,
        )
    with pytest.raises(ValueError, match="owner"):
        store.register_actor_context(
            entry.entry_id,
            expected_revision=before.revision,
            parent=replace(parent, owner=b"f" * 32),
            context_id=ContextId(1),
            target_hint=0x12400000,
        )
    assert not store.snapshot().actor_fenced


def test_corrupt_sidecar_blocks_mutation_without_erasing_settings(saved):
    store, entry, before, _, _ = saved
    registry = ActorRegistry(store.path, store.owner.storage_key)
    registry.path.write_text("{}", encoding="utf-8")
    with pytest.raises(FenceError):
        store.remove(entry.entry_id)
    assert store.snapshot().entries == before.entries


def test_live_legacy_fence_blocks_context_migration(saved, monkeypatch):
    store, _, _, _, _ = saved
    monkeypatch.setattr(
        "shadowbane_lab.pve.attack_list_fence.Registry._read",
        lambda self: [Mock(name="legacy", client_pid=1, client_creation=2)],
    )
    monkeypatch.setattr(Windows, "mapping_exists", lambda *args: True)
    monkeypatch.setattr(Windows, "alive", lambda *args: True)
    with pytest.raises(FenceError, match="legacy"):
        register(saved)
    assert not store.snapshot().actor_fenced
