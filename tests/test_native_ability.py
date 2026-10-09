"""Synthetic learned definitions on a borrowed handle; no client process is opened."""

import struct
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.client_observation import native_ability as ability
from shadowbane_lab.client_observation.native_character_config import ActiveCharacterError
from shadowbane_lab.client_observation.native_training import NativeTrainingEntry

ORIGINAL = "e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8"
PREPARED = "0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d"
SHOT = 563795161


def entry(power_id=SHOT, rank=40):
    return NativeTrainingEntry(power_id, "unknown", "unknown", rank, rank, rank, False)


class Memory:
    pid = 123
    pointer_size = 4
    executable_name = "sb.exe"
    executable_sha256 = PREPARED
    base_address = 0x400000

    def __init__(self):
        self.manager, self.sentinel = 0x20000, 0x21000
        self.slot = self.base_address + 0x138757C
        self.blocks = {}
        self.reads = []
        self.counts = {}
        self.mutate = None
        self.nodes = {}
        self.definitions = {}
        self.strings = {}

    def configure(self, records):
        records = sorted(records)
        self.blocks[self.slot] = bytearray(struct.pack("<I", self.manager))
        self.blocks[self.manager] = bytearray(struct.pack("<II", self.sentinel, len(records)))
        self.blocks[self.sentinel] = bytearray(struct.pack("<IIII", 0, 0x22000, 0, 0))
        for index, (power_id, name) in enumerate(records):
            node = 0x22000 + index * 0x1000
            definition = 0x100000 + index * 0x1000
            self.nodes[power_id], self.definitions[power_id] = node, definition
            right = node + 0x1000 if index + 1 < len(records) else self.sentinel
            self.blocks[node] = bytearray(
                struct.pack("<IIIIII", 0, 0, self.sentinel, right, power_id, definition)
            )
            data = bytearray(0x28C)
            for offset, value in ((0x138, power_id), (0x204, 0), (0x1A8, 2), (0x1B4, 0)):
                struct.pack_into("<I", data, offset, value)
            for ordinal, (offset, text) in enumerate(((0x13C, f"POWER-{power_id}"), (0x154, name))):
                address = 0x200000 + index * 0x2000 + ordinal * 0x1000
                raw = text.encode("utf-16-le") + b"\0\0"
                self.blocks[address] = bytearray(raw)
                self.strings[power_id, offset] = address
                struct.pack_into(
                    "<III", data, offset + 4, address, address + len(raw) - 2, address + len(raw)
                )
            self.blocks[definition] = data

    def read_block(self, address, size):
        self.reads.append((address, size))
        self.counts[address] = self.counts.get(address, 0) + 1
        data = bytes(self.blocks[address][:size])
        if address == self.mutate and self.counts[address] == 2:
            return bytes([data[0] ^ 1]) + data[1:]
        return data


@pytest.fixture
def setup(monkeypatch):
    process = Memory()
    process.configure([(SHOT, "Shot to the Leg")])
    session = SimpleNamespace(
        binding=SimpleNamespace(
            process_id=123, executable_sha256=PREPARED, process_creation_filetime_utc=456
        ),
        reader=SimpleNamespace(process=process, process_creation_filetime_utc=456),
        require_current=Mock(),
    )
    reader = Mock()
    reader.observe.return_value = SimpleNamespace(powers=(entry(),))
    factory = Mock(return_value=reader)
    monkeypatch.setattr(ability, "NativePlayerTrainingReader", factory)
    monkeypatch.setattr(ability, "load_bundled_native_training_profile", lambda: "profile")
    return session, process, reader, factory


@pytest.mark.parametrize(
    "selector", ["Shot to the Leg", "sHoT tO tHe LeG", str(SHOT), hex(SHOT), f"POWER-{SHOT}"]
)
def test_generic_name_or_id_reads_native_rank_and_names_on_same_handle(setup, selector):
    session, process, _, factory = setup
    result = ability.resolve_learned_ability(session, selector)
    assert result.power_id == SHOT and result.learned_rank == 40
    assert result.display_name == "Shot to the Leg" and result.recipient == "actor"
    assert result.internal_name == f"POWER-{SHOT}"
    assert result.as_dict()["target_mode"] == 2
    factory.assert_called_once_with("profile", process)
    assert session.require_current.call_count >= 4


@pytest.mark.parametrize("image", [ORIGINAL, PREPARED,
    "381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5",
    "a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a",
    "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e",
    "e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437",
    "1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c",
    "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903"])
def test_only_exact_reviewed_original_and_prepared_images_are_admitted(setup, image):
    session, process, _, _ = setup
    session.binding.executable_sha256 = process.executable_sha256 = image
    assert ability.resolve_learned_ability(session, str(SHOT)).power_id == SHOT


@pytest.mark.parametrize("mismatch", ["unknown", "pid", "creation", "hash", "pointer", "name"])
def test_compatibility_failure_precedes_any_native_read(setup, mismatch):
    session, process, _, factory = setup
    if mismatch == "unknown":
        session.binding.executable_sha256 = process.executable_sha256 = "a" * 64
    elif mismatch == "pid":
        process.pid = 456
    elif mismatch == "creation":
        session.binding.process_creation_filetime_utc = 999
    elif mismatch == "hash":
        process.executable_sha256 = ORIGINAL
    elif mismatch == "pointer":
        process.pointer_size = 8
    else:
        process.executable_name = "other.exe"
    with pytest.raises(ability.NativeAbilityCompatibilityError):
        ability.resolve_learned_ability(session, str(SHOT))
    assert process.reads == []
    session.require_current.assert_not_called()
    factory.assert_not_called()


@pytest.mark.parametrize("powers", [(), (entry(rank=0),), (entry(123),)])
def test_unlearned_or_zero_rank_id_never_reads_definition(setup, powers):
    session, process, reader, _ = setup
    reader.observe.return_value = SimpleNamespace(powers=powers)
    with pytest.raises(ability.NativeAbilityError, match="not learned"):
        ability.resolve_learned_ability(session, str(SHOT))
    assert process.reads == []


def test_numeric_id_does_not_read_other_learned_definitions(setup):
    session, process, reader, _ = setup
    reader.observe.return_value = SimpleNamespace(powers=(entry(1), entry()))
    # ID1 has no definition; explicit SHOT still resolves by its exact learned entry.
    assert ability.resolve_learned_ability(session, str(SHOT)).power_id == SHOT


def test_ambiguous_native_names_rejected_without_catalogue_fallback(setup):
    session, process, reader, _ = setup
    process.configure([(100, "Shot to the Leg"), (200, "SHOT TO THE LEG")])
    reader.observe.return_value = SimpleNamespace(powers=(entry(100), entry(200)))
    with pytest.raises(ability.NativeAbilityError, match="ambiguous"):
        ability.resolve_learned_ability(session, "shot to the leg")
    assert ability.resolve_learned_ability(session, "200").power_id == 200


@pytest.mark.parametrize("category,mode,delivery", [(2, 2, 0), (0, 3, 0), (0, 2, 1), (0, 10, 2)])
def test_unsupported_resolved_routing_rejected(setup, category, mode, delivery):
    session, process, _, _ = setup
    data = process.blocks[process.definitions[SHOT]]
    for offset, value in ((0x204, category), (0x1A8, mode), (0x1B4, delivery)):
        struct.pack_into("<I", data, offset, value)
    with pytest.raises(ability.NativeAbilityError, match="unsupported|requires delivery"):
        ability.resolve_learned_ability(session, str(SHOT))


def test_supported_direct_cast_recipient_preserved(setup):
    session, process, _, _ = setup
    struct.pack_into("<I", process.blocks[process.definitions[SHOT]], 0x1A8, 10)
    assert ability.resolve_learned_ability(session, str(SHOT)).recipient == "engagement_target"


@pytest.mark.parametrize("part", ["manager", "sentinel", "slot", "definition", "node", "string"])
def test_map_definition_and_string_mutations_fail_closed(setup, part):
    session, process, _, _ = setup
    process.mutate = {
        "manager": process.manager,
        "sentinel": process.sentinel,
        "slot": process.slot,
        "definition": process.definitions[SHOT],
        "node": process.nodes[SHOT],
        "string": process.strings[SHOT, 0x154],
    }[part]
    with pytest.raises(ability.NativeAbilityReadError, match="changed"):
        ability.resolve_learned_ability(session, str(SHOT))


@pytest.mark.parametrize("fault", ["span", "terminator", "utf16", "control", "cycle", "id"])
def test_corrupt_native_data_is_rejected(setup, fault):
    session, process, _, _ = setup
    data = process.blocks[process.definitions[SHOT]]
    raw = process.blocks[process.strings[SHOT, 0x154]]
    if fault == "span":
        struct.pack_into("<I", data, 0x154 + 8, 0x7FFFFFFF)
    elif fault == "terminator":
        raw[-2:] = b"xx"
    elif fault == "utf16":
        raw[:2] = b"\x00\xd8"
    elif fault == "control":
        raw[:2] = b"\0\0"
    elif fault == "cycle":
        struct.pack_into("<I", process.blocks[process.nodes[SHOT]], 16, SHOT + 1)
        struct.pack_into("<I", process.blocks[process.nodes[SHOT]], 8, process.nodes[SHOT])
    else:
        struct.pack_into("<I", data, 0x138, 1)
    with pytest.raises(ability.NativeAbilityReadError):
        ability.resolve_learned_ability(session, str(SHOT))


def test_learned_rank_change_during_definition_read_is_rejected(setup):
    session, _, reader, _ = setup
    reader.observe.side_effect = [
        SimpleNamespace(powers=(entry(),)),
        SimpleNamespace(powers=(replace(entry(), effective_rank_max=41),)),
    ]
    with pytest.raises(ability.NativeAbilityReadError, match="vector changed"):
        ability.resolve_learned_ability(session, str(SHOT))


def test_final_character_revocation_propagates_without_returning_ability(setup):
    session, _, reader, _ = setup

    def observe():
        if reader.observe.call_count == 2:
            session.require_current.side_effect = ActiveCharacterError("replaced character")
        return SimpleNamespace(powers=(entry(),))

    reader.observe.side_effect = observe
    with pytest.raises(ActiveCharacterError, match="replaced"):
        ability.resolve_learned_ability(session, str(SHOT))


@pytest.mark.parametrize("selector", ["", "0", "0xZZ", str(2**32), None])
def test_invalid_selector_rejected(setup, selector):
    session, process, _, _ = setup
    with pytest.raises(ability.NativeAbilityError):
        ability.resolve_learned_ability(session, selector)
    assert process.reads == []


def test_borrowed_handle_replacement_rejected_before_read(setup):
    session, process, _, _ = setup
    resolver = ability.NativeAbilityResolver(session)
    session.reader.process = Memory()
    with pytest.raises(ability.NativeAbilityReadError, match="handle changed"):
        resolver.resolve(str(SHOT))
    assert process.reads == []


def test_other_unsupported_learned_definition_does_not_block_unique_name(setup):
    session, process, reader, _ = setup
    process.configure([(100, "Another Power"), (SHOT, "Shot to the Leg")])
    reader.observe.return_value = SimpleNamespace(powers=(entry(100), entry()))
    struct.pack_into("<I", process.blocks[process.definitions[100]], 0x204, 9)
    assert ability.resolve_learned_ability(session, "Shot to the Leg").power_id == SHOT
