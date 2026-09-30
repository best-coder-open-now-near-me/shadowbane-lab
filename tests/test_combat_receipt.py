"""Combat receipts distinguish local submission, cleanup and immutable ownership."""

import struct
from dataclasses import replace

import pytest
from test_combat_wire_v2 import command as fixture
from test_combat_wire_v2 import receipt

from shadowbane_lab.client_extension import action_channel
from shadowbane_lab.client_extension.combat_channel import NativeCombatCommand
from shadowbane_lab.client_extension.combat_fence_v3 import RequestId
from shadowbane_lab.client_extension.combat_wire_v2 import (
    CLEANUP_REQUIRED,
    OUTBOUND_QUEUED,
    Action,
    ClosureProof,
    Outcome,
    Phase,
    Receipt,
    Verb,
)


def test_receipt_exact_geometry_and_roundtrip():
    value = receipt()
    encoded = value.encode()
    assert len(encoded) == 384
    assert struct.unpack_from("<I", encoded, 288) == (0x57424331,)
    assert encoded[308:340] == value.binding_digest
    decoded = Receipt.decode(encoded)
    assert decoded == value
    decoded.require_command(fixture(), Verb.SUBMIT)
    assert not decoded.cleanup_confirmed


@pytest.mark.parametrize("change", [
    {"request": RequestId(44)}, {"window": 124}, {"revision": 20},
    {"local_key": (93, 53)}, {"target_key": (94, 53)}, {"binding_digest": b"x" * 32},
    {"host": replace(fixture().host, lease_generation=8)},
    {"grant": replace(fixture().grant, generation=9)},
])
def test_each_immutable_receipt_field_must_match_command(change):
    with pytest.raises(ValueError, match="immutable command"):
        replace(receipt(), **change).require_command(fixture(), Verb.SUBMIT)


@pytest.mark.parametrize("offset,value", [(288, 0), (292, 6), (304, 2), (340, 1), (44, 8)])
def test_corrupt_receipt_is_not_accepted(offset, value):
    data = bytearray(receipt().encode())
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(ValueError):
        Receipt.decode(bytes(data))


def test_cleanup_requires_explicit_native_confirmation():
    original = receipt()
    for outcome in (Outcome.PENDING, Outcome.UNCERTAIN, Outcome.STALE, Outcome.UNAVAILABLE):
        assert not replace(original, outcome=outcome, phase=Phase.STOPPING).cleanup_confirmed
    assert not replace(original, outcome=Outcome.ENGAGEMENT_CLOSED).cleanup_confirmed
    assert replace(original, outcome=Outcome.ENGAGEMENT_CLOSED,
                   flags=OUTBOUND_QUEUED, phase=Phase.CLOSED,
                   closure=ClosureProof.NATIVE_STOPPED).cleanup_confirmed
    assert replace(original, outcome=Outcome.STALE, phase=Phase.RETIRED,
                   flags=OUTBOUND_QUEUED, closure=ClosureProof.SCENE_RETIRED).cleanup_confirmed
    assert not replace(original, phase=Phase.CLOSED, flags=0,
                       closure=ClosureProof.NEVER_BOUND).cleanup_confirmed


@pytest.mark.parametrize("change", [
    {"flags": CLEANUP_REQUIRED}, {"phase": Phase.CLOSED},
    {"outcome": Outcome.ACTION_CANCELLED},
    {"closure": ClosureProof.NATIVE_STOPPED},
    {"outcome": Outcome.STALE, "phase": Phase.RETIRED},
])
def test_receipt_rejects_contradictory_native_lifecycle_evidence(change):
    with pytest.raises(ValueError):
        replace(receipt(), **change).encode()


@pytest.mark.parametrize("verb", tuple(Verb))
def test_lifecycle_verbs_carry_same_original_command_without_generic_action(verb):
    action = (Action.NONE if verb in (Verb.BIND_ENGAGEMENT, Verb.ENGAGEMENT_STATUS,
                                     Verb.STOP_ENGAGEMENT) else Action.CAST)
    command = fixture(action=action)
    encoded = NativeCombatCommand(7, verb, command).encode_slot(
        sequence=1, created_tick=10, deadline_tick=20,
    )
    assert len(encoded) == action_channel.CLIENT_ACTION_COMMAND_SLOT_SIZE
    assert encoded[-576:] == command.encode()
    prefix = action_channel._COMMAND.unpack(encoded[:-576])
    assert prefix[2] == verb
    assert prefix[6:12] == (0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize("legacy_verb", [34, 35, 36])
def test_old_lifecycle_verbs_cannot_enter_the_v2_channel(legacy_verb):
    with pytest.raises(ValueError):
        NativeCombatCommand(7, legacy_verb, fixture()).encode_slot(
            sequence=1, created_tick=10, deadline_tick=20,
        )
