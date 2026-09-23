import struct
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.condemn_responses import CondemnResponseError
from shadowbane_lab.client_extension.condemn_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    Command,
    Outcome,
    Phase,
    Receipt,
    Snapshot,
    Target,
    Verb,
)
from shadowbane_lab.client_extension.movement_wire import Host

REQUEST = "11111111-2222-4333-8444-555555555555"
HOST = Host(123, 4, 5678)
TARGET = Target((20, 8), (30, 23), 5)
SNAPSHOT = Snapshot(
    scene=7,
    revision=2,
    local=(99, 53),
    root=100,
    manager=200,
    building_hud=300,
    front=300,
    open_button=400,
    building=(20, 8),
)
COMMAND = Command(HOST, 123, REQUEST, TARGET, SNAPSHOT)
RECEIPT = Receipt(
    REQUEST,
    HOST,
    123,
    Outcome.SUBMITTED,
    IN_FLIGHT,
    SNAPSHOT,
    TARGET,
    TARGET,
    REQUEST,
    Phase.OPENING,
    100,
    3,
)
ERRORS = (ValueError, CondemnResponseError)


def test_exact_native_packed_offsets_and_roundtrip():
    assert len(SNAPSHOT.encode()) == 132
    assert Snapshot.decode(SNAPSHOT.encode()) == SNAPSHOT
    assert struct.unpack_from("<QQ2I5I2I", SNAPSHOT.encode()) == (
        7,
        2,
        99,
        53,
        100,
        200,
        300,
        300,
        400,
        20,
        8,
    )
    raw = COMMAND.encode(Verb.ENSURE)
    assert len(raw) == 576 and raw[40:60] == TARGET.encode() and raw[60:192] == SNAPSHOT.encode()
    assert Command.decode(raw, Verb.ENSURE) == COMMAND
    raw = RECEIPT.encode()
    assert len(raw) == 384 and raw[48:180] == SNAPSHOT.encode()
    assert raw[180:200] == TARGET.encode() and raw[200:220] == TARGET.encode()
    assert struct.unpack_from("<IIQQQ", raw, 236) == (Phase.OPENING, 0x57424B31, 100, 3, 0)
    assert Receipt.decode(raw) == RECEIPT


@pytest.mark.parametrize("scope", [0, 3, 6, True, "5"])
def test_scope_is_explicit_and_typed(scope):
    with pytest.raises(ValueError):
        Target((20, 8), (30, 23), scope)


def test_guild_and_nation_do_not_merge_equal_identity():
    assert TARGET != replace(TARGET, scope=4)
    target = Target([20, 8], [30, 23], 5)
    assert target == TARGET and isinstance(target.building, tuple)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scene", 0),
        ("revision", 0),
        ("local", (1, 23)),
        ("root", 0),
        ("manager", 0),
        ("building_hud", 0),
        ("building", (20, 23)),
        ("count", 513),
        ("flags", 2),
        ("collision", 2),
        ("enabled", 1),
        ("entry", 123),
        ("row", 123),
        ("entry_key", (30, 23)),
        ("kos", 1),
        ("list_control", 1),
        ("pending", ((1, 23), (0, 0), (0, 0))),
        ("root", True),
        ("scene", -1),
    ],
)
def test_invalid_snapshot_fields_are_rejected(field, value):
    with pytest.raises(ERRORS):
        replace(SNAPSHOT, **{field: value}).encode()


def test_owned_disabled_and_enabled_rows_remain_separate():
    row = replace(
        SNAPSHOT,
        front=500,
        kos=500,
        list_control=600,
        context=(20, 8),
        row=800,
        entry=700,
        entry_key=(30, 23),
        count=1,
    )
    assert row.owned_list(TARGET) and row.eligible(TARGET)
    assert Snapshot.decode(row.encode()) == row
    assert Snapshot.decode(replace(row, enabled=1).encode()).enabled == 1
    assert not replace(row, collision=1).eligible(TARGET)
    assert not replace(row, context=(21, 8)).eligible(TARGET)
    assert not replace(row, flags=1).eligible(TARGET)


@pytest.mark.parametrize(
    "verb,updates",
    [
        (Verb.INSPECT, {}),
        (Verb.ENSURE, {"expected": Snapshot()}),
        (Verb.ENSURE, {"transition_request": REQUEST}),
        (Verb.ENSURE, {"window": 0}),
        (Verb.ENSURE, {"window": True}),
        (Verb.ENSURE, {"target": Target((21, 8), (30, 23), 5)}),
        (Verb.ENSURE, {"request_key": "00000000-0000-0000-0000-000000000000"}),
    ],
)
def test_command_admission(verb, updates):
    with pytest.raises(ValueError):
        replace(COMMAND, **updates).encode(verb)


def test_continuation_inspect_preserves_transition_and_has_no_snapshot():
    c = replace(COMMAND, expected=Snapshot(), transition_request=REQUEST)
    assert Command.decode(c.encode(Verb.INSPECT), Verb.INSPECT) == c


@pytest.mark.parametrize("offset", [208, 575])
def test_command_unknown_bytes_rejected(offset):
    raw = bytearray(COMMAND.encode(Verb.ENSURE))
    raw[offset] = 1
    with pytest.raises(ValueError):
        Command.decode(raw, Verb.ENSURE)


@pytest.mark.parametrize("offset,value", [(44, 8), (240, 0), (268, 1), (383, 1)])
def test_receipt_reserved_and_signature_checks(offset, value):
    raw = bytearray(RECEIPT.encode())
    raw[offset] = value
    with pytest.raises(ValueError):
        Receipt.decode(raw)


@pytest.mark.parametrize(
    "updates",
    [
        {"flags": READY | IN_FLIGHT},
        {"flags": 0},
        {"action_tick": 0},
        {"transition_request": None},
        {"transition_target": None},
        {"phase": Phase.UNCERTAIN},
        {"phase": Phase.VERIFIED},
        {"phase": Phase.EXISTING},
        {"response_floor": 2**63},
        {"window": 0},
    ],
)
def test_receipt_contradictions_fail(updates):
    with pytest.raises(ValueError):
        replace(RECEIPT, **updates).encode()


def test_completed_and_existing_state_never_conflate():
    verified = replace(RECEIPT, flags=0, phase=Phase.VERIFIED, completion_sequence=6)
    existing = replace(RECEIPT, outcome=Outcome.OBSERVED, flags=0, phase=Phase.EXISTING)
    assert Receipt.decode(verified.encode()) == verified
    assert Receipt.decode(existing.encode()) == existing
    with pytest.raises(ValueError):
        replace(existing, completion_sequence=6).encode()
    with pytest.raises(ValueError):
        replace(verified, completion_sequence=3).encode()


def test_observation_target_can_differ_from_retained_transition():
    # An idle inspection may show another target while retaining previous result metadata.
    r = replace(
        RECEIPT,
        flags=0,
        phase=Phase.VERIFIED,
        completion_sequence=6,
        target=replace(TARGET, scope=4),
    )
    assert Receipt.decode(r.encode()).target != r.transition_target


def test_queued_expiry_and_uncertain_empty_observation_decode():
    expired = Receipt(REQUEST, HOST, 123, Outcome.STALE, 0, Snapshot())
    assert Receipt.decode(expired.encode()) == expired
    failed = replace(
        RECEIPT, snapshot=Snapshot(), phase=Phase.UNCERTAIN, flags=IN_FLIGHT | UNRESOLVED
    )
    assert Receipt.decode(failed.encode()) == failed


@pytest.mark.parametrize("size", [0, 19, 131, 383, 575, 577])
def test_bad_sizes_fail(size):
    for fn in (
        Target.decode,
        Snapshot.decode,
        Receipt.decode,
        lambda data: Command.decode(data, Verb.ENSURE),
    ):
        with pytest.raises(ERRORS):
            fn(bytes(size))


@pytest.mark.parametrize(
    "updates",
    [
        {"target": Target((21, 8), (30, 23), 5)},
        {"target": Target((20, 8), (30, 23), 4)},
        {"phase": Phase.IDLE, "action_tick": 0, "response_floor": 3},
        {"completion_sequence": 6},
        {"outcome": True},
        {"phase": True},
    ],
)
def test_receipt_scope_and_action_metadata_cannot_be_relabelled(updates):
    with pytest.raises(ValueError):
        replace(RECEIPT, **updates).encode()
