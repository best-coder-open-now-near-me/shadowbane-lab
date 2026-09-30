"""Frozen v2 action and v3 engagement codecs; no runtime activation or input."""
import hashlib
import json
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from shadowbane_lab.client_extension.combat_fence_v3 import (
    Authority,
    Binding,
    EngagementId,
    Ordinals,
    RequestId,
    State,
)
from shadowbane_lab.client_extension.combat_wire_v2 import (
    CLEANUP_REQUIRED,
    OUTBOUND_QUEUED,
    UNCERTAIN_HISTORY,
    Action,
    ClosureProof,
    Command,
    EntryState,
    Outcome,
    Phase,
    Receipt,
    Verb,
    identity_digest,
    operation_digest,
)
from shadowbane_lab.client_extension.movement_wire import Grant, Host, Owner


def command(authority=Authority.MANUAL_PLAYER, action=Action.CAST):
    grant = Grant(8, 9, Owner.AUTOMATION, "worker", "operation")
    npc = authority is Authority.NPC
    binding = Binding(
        1234, 5678, 0x1020304050607080, 0x1122334455667788, 7, 8, 9,
        0 if npc else 19, EngagementId(1), bytes(32) if npc else b"s" * 32,
        hashlib.sha256(json.dumps(["Server", "Local"]).encode()).digest(),
        bytes(32) if npc else hashlib.sha256(
            json.dumps(["player", "Server", "0000005c:00000035"]).encode()).digest(),
        operation_digest(grant), (91, 53), (92, 37 if npc else 53),
        bytes(32) if npc else identity_digest("Enemy"), authority, 0x12300000, 0x12400000,
    )
    return Command(Host(5678, 7, 0x1122334455667788), 123, grant, binding,
                   RequestId(2), action, 428918601 if action is Action.CAST else 0,
                   identity_digest("Local"), identity_digest("Server"))


def receipt(c=None, verb=Verb.SUBMIT):
    c = command() if c is None else c
    b = c.binding
    return Receipt(c.request, c.host, c.window, Outcome.CLIENT_OUTBOUND_QUEUED,
                   CLEANUP_REQUIRED | OUTBOUND_QUEUED, c.grant, b.revision,
                   b.local_key, b.target_key, Phase.BOUND, 2, 4, False, b.digest,
                   b.authority, c.action, c.power_id, b.engagement, EntryState.ENTERED,
                   verb, ClosureProof.NONE)


def test_golden_geometry_offsets_and_roundtrip():
    c = command()
    f = Path(__file__).parent / "fixtures"
    for filename, payload in (("combat_command_v2.hex", c.encode()),
                              ("combat_fence_v3.hex", c.binding.encode()),
                              ("combat_receipt_v2.hex", receipt(c).encode())):
        assert payload.hex() == (f / filename).read_text().strip()
    data = c.encode()
    assert len(data) == 576 and len(c.binding.encode()) == 320
    assert data[240:256] == (2).to_bytes(16, "big")
    assert struct.unpack_from("<6I", data, 536) == (2, 1, 2, 428918601, 0x12300000, 0x12400000)
    assert data[560:] == (1).to_bytes(16, "big")
    assert Command.decode(data, client_pid=1234, client_creation=c.binding.client_creation) == c
    assert Binding.decode(c.binding.encode(State.ENTERED)) == (c.binding, State.ENTERED)
    r = receipt(c)
    assert len(r.encode()) == 384
    assert struct.unpack_from("<4I", r.encode(), 340) == (2, 1, 2, 428918601)
    assert struct.unpack_from("<3I", r.encode(), 372) == (2, 38, 0)
    assert Receipt.decode(r.encode()) == r
    r.require_command(c, Verb.SUBMIT)


@pytest.mark.parametrize("authority", list(Authority))
@pytest.mark.parametrize("action", list(Action))
def test_authority_and_action_matrix(authority, action):
    c = command(authority, action)
    assert Command.decode(c.encode(), client_pid=1234,
                          client_creation=c.binding.client_creation) == c
    for verb in Verb:
        controls = (Verb.BIND_ENGAGEMENT, Verb.ENGAGEMENT_STATUS, Verb.STOP_ENGAGEMENT)
        if (verb in controls) == (action is Action.NONE):
            c.require_verb(verb)
        else:
            with pytest.raises(ValueError, match="verb and action"):
                c.require_verb(verb)
    if authority is Authority.NPC:
        assert c.binding.revision == 0
        assert not any(c.binding.store + c.binding.entry + c.binding.target_name)
        assert any(c.binding.owner + c.local_name + c.server)


@pytest.mark.parametrize("change", [
    {"target_key": (92, 53)}, {"revision": 1}, {"store": b"x" * 32},
    {"entry": b"x" * 32}, {"target_name": b"x" * 32}, {"owner": bytes(32)},
    {"actor_address_hint": 0}, {"target_address_hint": 0x12400001},
    {"actor_address_hint": 0x12400000}, {"target_address_hint": 0xFFFFFFFF},
    {"engagement": RequestId(1)}, {"authority": 2}, {"local_key": (91, 37)},
])
def test_npc_binding_rejects_fake_list_evidence_or_invalid_identity(change):
    with pytest.raises(ValueError):
        replace(command(Authority.NPC).binding, **change)


@pytest.mark.parametrize("offset", [0, 8, 12, 20, 319])
def test_fence_rejects_wrong_version_header_and_padding(offset):
    data = bytearray(command().binding.encode())
    data[offset] ^= 128
    with pytest.raises(ValueError):
        Binding.decode(bytes(data))


def test_mapping_name_cannot_collide_between_ordinal_one_namespaces():
    binding = command().binding
    assert binding.name.endswith(hashlib.sha256(binding.encode()).hexdigest())
    assert ".v3." in binding.name
    for change in ({"client_pid": 1235}, {"client_creation": 2}, {"producer_generation": 8},
                   {"movement_generation": 99}, {"operation": b"x" * 32}, {"scene": 10}):
        other = replace(binding, **change)
        assert other.engagement == binding.engagement
        assert other.name != binding.name


def test_ordinals_are_monotonic_scoped_and_do_not_wrap():
    ids = Ordinals()
    first = ids.next_engagement()
    assert first == EngagementId(1)
    assert ids.next_request(first) == RequestId(1)
    assert ids.next_request(first) == RequestId(2)
    second = ids.next_engagement()
    assert second == EngagementId(2) and ids.next_request(second) == RequestId(3)
    assert ids.next_request(first) == RequestId(4)  # Old-owner cleanup remains possible.
    with pytest.raises(ValueError, match="unallocated"):
        ids.next_request(EngagementId(3))
    ids._request = 2**128 - 1
    with pytest.raises(ValueError):
        ids.next_request(second)
    assert ids._request == 2**128 - 1
    ids._engagement = 2**128 - 1
    with pytest.raises(ValueError):
        ids.next_engagement()


@pytest.mark.parametrize("kind", [EngagementId, RequestId])
@pytest.mark.parametrize("value", [0, -1, 2**128, True, "1"])
def test_invalid_ordinals_are_rejected(kind, value):
    with pytest.raises(ValueError):
        kind(value)


def test_command_binding_and_operation_correlation():
    c = command()
    for pid, creation in ((1235, c.binding.client_creation), (1234, 1)):
        with pytest.raises(ValueError):
            Command.decode(c.encode(), client_pid=pid, client_creation=creation)
    for offset in (256, 352, 384, 400, 408, 440, 472, 504, 536, 540, 552, 556, 575):
        data = bytearray(c.encode())
        data[offset] ^= 1
        with pytest.raises(ValueError):
            Command.decode(bytes(data), client_pid=1234, client_creation=c.binding.client_creation)
    for change in ({"request": EngagementId(2)}, {"power_id": 0}, {"local_name": bytes(32)},
                   {"host": replace(c.host, lease_generation=8)},
                   {"grant": replace(c.grant, operation_id="other")}):
        with pytest.raises(ValueError):
            replace(c, **change).encode()


def test_receipt_correlation_includes_action_power_engagement_and_verb():
    c, r = command(), receipt()
    for change in ({"request": RequestId(3)}, {"power_id": 1},
                   {"engagement": EngagementId(2)}, {"verb": Verb.ACTION_STATUS},
                   {"binding_digest": b"x" * 32}, {"window": 124}):
        with pytest.raises(ValueError, match="immutable command"):
            replace(r, **change).require_command(c, Verb.SUBMIT)
    for offset in (288, 340, 344, 348, 372, 376, 380):
        data = bytearray(r.encode())
        struct.pack_into("<I", data, offset, 0xFFFFFFFF)
        with pytest.raises(ValueError):
            Receipt.decode(bytes(data))


def test_queued_history_survives_stop_and_scene_retirement():
    r = receipt()
    for phase, proof in ((Phase.CLOSED, ClosureProof.NATIVE_STOPPED),
                         (Phase.RETIRED, ClosureProof.SCENE_RETIRED)):
        closed = replace(r, phase=phase, closure=proof, flags=OUTBOUND_QUEUED | UNCERTAIN_HISTORY)
        assert Receipt.decode(closed.encode()) == closed
        assert closed.native_entered is True and closed.cleanup_confirmed
        assert closed.outcome is Outcome.CLIENT_OUTBOUND_QUEUED


def test_unknown_and_action_only_cancellation_never_prove_engagement_cleanup():
    r = receipt()
    cancelled = replace(r, outcome=Outcome.ACTION_CANCELLED, flags=CLEANUP_REQUIRED,
                        entry_state=EntryState.NEVER_ENTERED, verb=Verb.CANCEL_ACTION)
    assert Receipt.decode(cancelled.encode()) == cancelled
    assert cancelled.native_entered is False and not cancelled.cleanup_confirmed
    control = command(action=Action.NONE)
    unknown_stop = replace(receipt(control), outcome=Outcome.ENGAGEMENT_CLOSED,
                           flags=0, phase=Phase.CLOSED, entry_state=EntryState.UNKNOWN,
                           verb=Verb.STOP_ENGAGEMENT, closure=ClosureProof.NEVER_BOUND)
    assert Receipt.decode(unknown_stop.encode()) == unknown_stop
    assert unknown_stop.native_entered is None and not unknown_stop.cleanup_confirmed


def test_expired_history_is_unknown_not_no_entry_or_cleanup_proof():
    expired = replace(receipt(), outcome=Outcome.HISTORY_EXPIRED, flags=0, phase=Phase.UNKNOWN,
                      entry_state=EntryState.UNKNOWN, verb=Verb.ACTION_STATUS,
                      closure=ClosureProof.HISTORY_EXPIRED)
    assert Receipt.decode(expired.encode()) == expired
    assert expired.native_entered is None and not expired.cleanup_confirmed
    for change in ({"flags": OUTBOUND_QUEUED}, {"entry_state": EntryState.NEVER_ENTERED},
                   {"phase": Phase.CLOSED}, {"closure": ClosureProof.NATIVE_STOPPED}):
        with pytest.raises(ValueError):
            replace(expired, **change).encode()


@pytest.mark.parametrize("change", [
    {"phase": Phase.CLOSED}, {"phase": Phase.UNKNOWN}, {"flags": OUTBOUND_QUEUED},
    {"entry_state": EntryState.NEVER_ENTERED}, {"closure": ClosureProof.NATIVE_STOPPED},
    {"outcome": Outcome.ACTION_CANCELLED}, {"outcome": Outcome.DEFERRED},
    {"action": Action.ATTACK}, {"verb": Verb.STOP_ENGAGEMENT},
    {"flags": 8}, {"combat_target_present": 1},
])
def test_receipt_rejects_inconsistent_authority_or_proof(change):
    with pytest.raises(ValueError):
        replace(receipt(), **change).encode()


def test_full_utf16_identity_remains_lossless():
    assert identity_digest("\U0001f642") == hashlib.sha256(b"\x3d\xd8\x42\xde").digest()
    assert identity_digest("name") != identity_digest("Name")
    for invalid in ("", "x\0x", "x" * 65, "\ud800"):
        with pytest.raises(ValueError):
            identity_digest(invalid)


def test_deferred_bind_and_deferred_action_have_distinct_entry_evidence():
    c = command(action=Action.NONE)
    deferred_bind = replace(receipt(c), outcome=Outcome.DEFERRED, flags=0,
                            phase=Phase.CLOSED, entry_state=EntryState.UNKNOWN,
                            verb=Verb.BIND_ENGAGEMENT, closure=ClosureProof.NEVER_BOUND)
    assert Receipt.decode(deferred_bind.encode()) == deferred_bind
    assert deferred_bind.native_entered is None and not deferred_bind.cleanup_confirmed
    for change in ({"phase": Phase.UNKNOWN, "closure": ClosureProof.NONE},
                   {"entry_state": EntryState.NEVER_ENTERED}):
        with pytest.raises(ValueError):
            replace(deferred_bind, **change).encode()
    deferred_action = replace(receipt(), outcome=Outcome.DEFERRED,
                              flags=CLEANUP_REQUIRED, entry_state=EntryState.NEVER_ENTERED)
    assert Receipt.decode(deferred_action.encode()) == deferred_action
    assert deferred_action.native_entered is False and not deferred_action.cleanup_confirmed


def test_entered_action_cannot_claim_engagement_never_bound():
    with pytest.raises(ValueError, match="never-bound"):
        replace(receipt(), flags=OUTBOUND_QUEUED, phase=Phase.CLOSED,
                closure=ClosureProof.NEVER_BOUND).encode()
