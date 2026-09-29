import struct
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from shadowbane_lab.client_extension.movement_wire import Host
from shadowbane_lab.client_extension.vendor_menu_wire import (
    IN_FLIGHT,
    MAGIC,
    READY,
    UNRESOLVED,
    Command,
    Outcome,
    Receipt,
    Snapshot,
    Verb,
)
from tests.test_vendor_menu import KEY, recipe, state


def raw_receipt(**changes):
    fields = dict(request=uuid.UUID(KEY).bytes, host=Host(123, 7, 456).encode(), window=999,
                  outcome=Outcome.OBSERVED, flags=READY, snapshot=state().encode(),
                  transition=bytes(16), magic=MAGIC, padding=bytes(220))
    fields.update(changes)
    return struct.pack("<16s16sQII96s16sI220s", *fields.values())


def test_sizes_offsets_and_canonical_roundtrip():
    observed = recipe(item_template=25860, selected_template=25860,
                      activated_template=25860, mode=1, table=16, quantity=1,
                      prefix=3362971591, suffix=3362971591)
    assert len(observed.encode()) == 96
    assert Snapshot.decode(observed.encode()) == observed
    assert struct.unpack_from("<I", observed.encode(), 88)[0] == 3362971591
    assert struct.unpack_from("<I", observed.encode(), 92)[0] == 710
    command = Command(Host(123, 7, 456), 999, KEY, observed, 5051080)
    encoded = command.encode(Verb.SELECT_RECIPE)
    assert len(encoded) == 576
    assert struct.unpack_from("<I", encoded, 136)[0] == 5051080
    assert not any(encoded[140:])
    raw = raw_receipt(snapshot=observed.encode(), transition=uuid.UUID(KEY).bytes)
    assert len(raw) == 384
    result = Receipt.decode(raw)
    assert result.snapshot == observed
    assert result.transition_request == KEY
    assert Snapshot.decode(bytes(96)).empty


@pytest.mark.parametrize("changes", [dict(scene=0), dict(revision=0), dict(root=True),
    dict(item_template=25860), dict(sentinel=3362971591), dict(recipe_list=20),
    dict(mode=3), dict(multiple=2), dict(quantity=-1), dict(vendor=2**32)])
def test_snapshot_rejects_missing_owner_absent_recipe_fields_and_invalid_scalars(changes):
    with pytest.raises(ValueError):
        state(**changes).encode()


@pytest.mark.parametrize("changes", [dict(sentinel=0), dict(recipe_list=0)])
def test_recipe_requires_reviewed_sentinel_and_owned_list(changes):
    with pytest.raises(ValueError):
        replace(recipe(), **changes).encode()


@pytest.mark.parametrize("changes", [dict(request=bytes(16)), dict(window=2**32),
    dict(flags=8), dict(flags=READY | IN_FLIGHT), dict(flags=READY | UNRESOLVED),
    dict(snapshot=bytes(96)), dict(magic=0), dict(padding=b"x" + bytes(219)), dict(outcome=99)])
def test_receipt_rejects_malformed_wire(changes):
    with pytest.raises(ValueError):
        Receipt.decode(raw_receipt(**changes))


@pytest.mark.parametrize("verb", list(Verb))
def test_commands_admit_only_owned_typed_arguments(verb):
    snapshot = (recipe(item_template=25860, selected_template=25860, activated_template=25860)
                if verb in (Verb.SELECT_RECIPE, Verb.RANDOM_MODE, Verb.CLOSE_RECIPE) else state())
    if verb == Verb.INSPECT:
        snapshot = Snapshot()
    template = 25860 if verb == Verb.SELECT_RECIPE else 0
    command = Command(Host(123, 7, 456), 999, KEY, snapshot, template)
    assert len(command.encode(verb)) == 576
    with pytest.raises(ValueError):
        replace(command, template=0 if template else 25860).encode(verb)
    if verb != Verb.INSPECT:
        with pytest.raises(ValueError):
            replace(command, expected=Snapshot()).encode(verb)
        with pytest.raises(ValueError):
            replace(command, expected=replace(snapshot, front_hud=123456)).encode(verb)


def test_selection_requires_single_mode_and_random_mode_requires_matching_keys():
    command = Command(Host(123, 7, 456), 999, KEY, recipe(multiple=1), 25860)
    with pytest.raises(ValueError):
        command.encode(Verb.SELECT_RECIPE)
    with pytest.raises(ValueError):
        replace(command, expected=recipe(item_template=25860), template=0).encode(Verb.RANDOM_MODE)


def test_native_cpp_command_and_receipt_fixture_matches_python():
    fixture = Path(__file__).parent / "fixtures" / "native_vendor_menu_wire_v1.hex"
    command_raw, receipt_raw = (bytes.fromhex(line) for line in fixture.read_text().splitlines())
    key = str(uuid.UUID(bytes=b"\x01" + bytes(15)))
    expected = Snapshot(
        scene=1, revision=1, root=100, manager=200, front_hud=700, menu=300,
        hireling=400, building=500, vendor=600, recipe=700, inventory=0,
        item_template=5051080, prefix=3362971591, suffix=3362971591,
        mode=1, table=16, quantity=1, multiple=0,
        selected_template=5051080, activated_template=5051080,
        sentinel=3362971591, recipe_list=701,
    )
    command = Command(Host(1, 2, 3), 123, key, expected, 25860)
    assert len(command_raw) == 576 and len(receipt_raw) == 384
    assert command.encode(Verb.SELECT_RECIPE) == command_raw
    assert Receipt.decode(receipt_raw) == Receipt(
        key, Host(1, 2, 3), 123, Outcome.OBSERVED, READY, expected, key,
    )
