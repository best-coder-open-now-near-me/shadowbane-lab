"""Combat receipts distinguish local submission, cleanup and immutable ownership."""

import hashlib
import struct
from dataclasses import replace

import pytest
from test_combat_wire import fixture

from shadowbane_lab.client_extension import action_channel
from shadowbane_lab.client_extension.combat_channel import NativeCombatCommand
from shadowbane_lab.client_extension.combat_wire import (
    CLEANUP_REQUIRED,
    LOCAL_CANCELLED,
    OUTBOUND_QUEUED,
    Outcome,
    Phase,
    Receipt,
    Verb,
)


def receipt():
    command = fixture()
    b = command.binding
    return Receipt(b.request, command.host, command.window, Outcome.CLIENT_OUTBOUND_QUEUED,
                   CLEANUP_REQUIRED | OUTBOUND_QUEUED, command.grant, b.revision,
                   b.local_key, b.target_key, Phase.ENGAGED, 1, 1, True,
                   hashlib.sha256(b.encode()).digest())


def test_receipt_exact_geometry_and_roundtrip():
    value = receipt()
    encoded = value.encode()
    assert len(encoded) == 384
    assert struct.unpack_from("<I", encoded, 288) == (0x57424331,)
    assert encoded[308:340] == value.binding_digest
    decoded = Receipt.decode(encoded)
    assert decoded == value
    decoded.require_command(fixture())
    assert not decoded.cleanup_confirmed


@pytest.mark.parametrize("change", [
    {"request": b"r" * 16}, {"window": 124}, {"revision": 20},
    {"local_key": (93, 53)}, {"target_key": (94, 53)}, {"binding_digest": b"x" * 32},
    {"host": replace(fixture().host, lease_generation=8)},
    {"grant": replace(fixture().grant, generation=9)},
])
def test_each_immutable_receipt_field_must_match_command(change):
    with pytest.raises(ValueError, match="immutable command"):
        replace(receipt(), **change).require_command(fixture())


@pytest.mark.parametrize("offset,value", [(288, 0), (292, 5), (304, 2), (340, 1), (44, 8)])
def test_corrupt_receipt_is_not_accepted(offset, value):
    data = bytearray(receipt().encode())
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(ValueError):
        Receipt.decode(bytes(data))


def test_cleanup_requires_explicit_native_confirmation():
    original = receipt()
    for outcome in (Outcome.PENDING, Outcome.UNCERTAIN, Outcome.STALE, Outcome.UNAVAILABLE):
        assert not replace(original, outcome=outcome, phase=Phase.CANCELLING).cleanup_confirmed
    assert not replace(original, outcome=Outcome.LOCAL_CANCELLED).cleanup_confirmed
    assert replace(original, outcome=Outcome.LOCAL_CANCELLED,
                   flags=LOCAL_CANCELLED, phase=Phase.IDLE).cleanup_confirmed
    assert replace(original, outcome=Outcome.STALE, phase=Phase.RETIRED,
                   flags=OUTBOUND_QUEUED).cleanup_confirmed


@pytest.mark.parametrize("change", [
    {"flags": CLEANUP_REQUIRED}, {"phase": Phase.CANCELLING},
    {"outcome": Outcome.LOCAL_CANCELLED},
    {"outcome": Outcome.LOCAL_CANCELLED, "flags": LOCAL_CANCELLED},
    {"outcome": Outcome.STALE, "phase": Phase.RETIRED},
])
def test_receipt_rejects_contradictory_native_lifecycle_evidence(change):
    with pytest.raises(ValueError):
        replace(receipt(), **change).encode()


@pytest.mark.parametrize("verb", tuple(Verb))
def test_lifecycle_verbs_carry_same_original_command_without_generic_action(verb):
    command = fixture()
    encoded = NativeCombatCommand(7, verb, command).encode_slot(
        sequence=1, created_tick=10, deadline_tick=20,
    )
    assert len(encoded) == action_channel.CLIENT_ACTION_COMMAND_SLOT_SIZE
    assert encoded[-576:] == command.encode()
    prefix = action_channel._COMMAND.unpack(encoded[:-576])
    assert prefix[2] == verb
    assert prefix[6:12] == (0, 0, 0, 0, 0, 0)
