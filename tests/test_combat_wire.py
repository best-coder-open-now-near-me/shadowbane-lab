"""Typed command binds whole fence lifetime and lossless native identities."""
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from test_combat_fence import LOCAL, NativeConsumer, entry, store_at

from shadowbane_lab.client_extension.combat_fence import Binding, State
from shadowbane_lab.client_extension.combat_fence_windows import Windows
from shadowbane_lab.client_extension.combat_wire import Command, identity_digest, operation_digest
from shadowbane_lab.client_extension.movement_wire import Grant, Host, Owner


def fixture():
    grant = Grant(8, 9, Owner.AUTOMATION, "worker", "operation")
    binding = Binding(1234, 5678, 0x1020304050607080, 0x1122334455667788,
                      7, 8, 9, 19, bytes(range(1, 17)), b"s" * 32,
                      hashlib.sha256(json.dumps(["Server", "Local\U0001f642"]).encode()).digest(),
                      hashlib.sha256(json.dumps(["player", "Server", "0000005c:00000035"])
                                     .encode()).digest(),
                      operation_digest(grant), (91, 53), (92, 53), identity_digest("Enemy\u00e9"))
    return Command(Host(5678, 7, 0x1122334455667788), 123, grant, binding,
                   identity_digest("Local\U0001f642"), identity_digest("Server"),
                   identity_digest("Enemy\u00e9"))


def test_shared_command_fixture_and_lifetime():
    command = fixture()
    payload = command.encode()
    fixture_path = Path(__file__).parent / "fixtures/combat_command_v1.hex"
    assert payload.hex() == fixture_path.read_text().strip()
    assert Command.decode(payload, client_pid=1234, client_creation=0x1020304050607080) == command
    for pid, creation in ((1235, 0x1020304050607080), (1234, 1)):
        with pytest.raises(ValueError, match="complete binding"):
            Command.decode(payload, client_pid=pid, client_creation=creation)
    # Every immutable field carried by the command must be bound, not just UUID.
    for offset in (0, 8, 24, 32, 48, 240, 256, 352, 384, 400, 408, 440, 472, 504, 575):
        corrupt = bytearray(payload)
        corrupt[offset] ^= 1
        with pytest.raises(ValueError):
            Command.decode(bytes(corrupt), client_pid=1234, client_creation=0x1020304050607080)


def test_complete_utf16_identity_without_lossy_normalization():
    assert identity_digest("\U0001f642") == hashlib.sha256(b"\x3d\xd8\x42\xde").digest()
    assert identity_digest("name") != identity_digest("Name")
    assert identity_digest("name") != identity_digest("name ")
    assert identity_digest("\u00e9") != identity_digest("e\u0301")
    assert identity_digest("\U0001f642" * 32)
    for value in ("", "a\0b", "a" * 65, "\U0001f642" * 33, "\ud800", "\udc00"):
        with pytest.raises(ValueError):
            identity_digest(value)
    c = fixture()
    for change in (dict(window=0), dict(host=replace(c.host, lease_generation=8)),
                   dict(grant=replace(c.grant, operation_id="other")),
                   dict(local_name=bytes(32)), dict(target_name=b"short")):
        with pytest.raises(ValueError):
            replace(c, **change).encode()


@pytest.mark.skipif(os.name != "nt", reason="Windows kernel admissions")
def test_production_registration_builds_canonical_command(tmp_path):
    store = store_at(tmp_path)
    pid, creation = Windows().identity()
    host = Host(pid, 7, creation)
    grant = Grant(8, 9, Owner.AUTOMATION, "worker", "operation")
    args = dict(expected_revision=1, client_pid=pid, client_creation=creation,
                host=host, window=123, grant=grant, local_key=LOCAL)
    ticket, command = store.register_combat_admission(entry().entry_id, **args)
    try:
        assert ticket.state() == State.PENDING
        assert command.binding == ticket.binding
        assert command.target_name == identity_digest("Enemy")
        assert Command.decode(command.encode(), client_pid=pid, client_creation=creation) == command
        store.clear(expected_revision=1)
        assert ticket.state() == State.REVOKED
    finally:
        ticket.close()
    with pytest.raises(ValueError):
        store.register_combat_admission(entry().entry_id, **args)


@pytest.mark.skipif(os.name != "nt", reason="Windows native command consumer")
@pytest.mark.parametrize("schedule",
                         ["enter_remove", "remove_enter", "wrong_binding", "wrong_name"])
def test_real_process_command_registration_and_revocation(tmp_path, schedule):
    path = os.environ.get("SHADOWBANE_COMBAT_FENCE_TEST_EXE")
    if not path:
        pytest.skip("compiled Win32 native command consumer not configured")
    native = NativeConsumer(path, "--command-consumer")
    ticket = None
    try:
        store = store_at(tmp_path)
        producer, creation = Windows().identity()
        client, client_creation = native.identity
        ticket, command = store.register_combat_admission(
            entry().entry_id, expected_revision=1, client_pid=client,
            client_creation=client_creation, host=Host(producer, 7, creation), window=123,
            grant=Grant(8, 9, Owner.AUTOMATION, "worker", "operation"), local_key=LOCAL,
        )
        if schedule == "wrong_binding":
            # A self-consistent full command/digest cannot substitute another
            # saved owner for the immutable mapping's actual registered owner.
            command = replace(command, binding=replace(command.binding, owner=b"x" * 32))
        elif schedule == "wrong_name":
            digest = identity_digest("Renamed")
            command = replace(command, binding=replace(command.binding, target_name=digest),
                              target_name=digest)
        assert native.command(command.encode().hex()) == "open"
        if schedule == "enter_remove":
            assert native.command("enter") == "0"
            assert store.clear().entered_admissions == (ticket.binding.request.hex(),)
            assert native.command("inspect") == "5 4"
        elif schedule == "remove_enter":
            assert store.clear().entered_admissions == ()
            assert native.command("enter") == "5"
        else:
            assert native.command("enter") == "3"
            assert ticket.state() == State.PENDING
    finally:
        if ticket is not None:
            ticket.close()
        native.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows kernel admissions")
def test_saved_metadata_cannot_cross_a_concurrent_list_revision(tmp_path):
    store = store_at(tmp_path)
    pid, creation = Windows().identity()
    register = store.register_admission
    def mutate_before_registration(*args, **kwargs):
        store.clear(expected_revision=1)
        return register(*args, **kwargs)
    with patch.object(store, "register_admission", side_effect=mutate_before_registration):
        with pytest.raises(ValueError, match="current manual"):
            store.register_combat_admission(
                entry().entry_id, expected_revision=1, client_pid=pid, client_creation=creation,
                host=Host(pid, 7, creation), window=123,
                grant=Grant(8, 9, Owner.AUTOMATION, "worker", "operation"), local_key=LOCAL,
            )
    assert store.snapshot().revision == 2
    assert not store.path.with_suffix(".admissions.json").exists()
