import json
import struct
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import pytest

from shadowbane_lab.client_observation import (
    NativePlayerActionObservation,
    NativeTargetActionCompatibilityError,
    NativeTargetActionObservation,
    NativeTargetActionReader,
    NativeTargetActionReadError,
    load_bundled_native_target_action_profile,
    load_native_target_action_profile_text,
    open_windows_native_target_action_reader,
)

ORIGINAL = "e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8"
PREPARED = "0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d"


def _profile():
    return replace(load_bundled_native_target_action_profile(),
        profile_id="target-action-test", executable_sha256="ab" * 32,
        player_pointer_rva=0x100, selected_pointer_rva=0x104,
        arc_character_vtable_rva=0x200, arc_motion_vtable_rva=0x300)


class FakeProcessMemory:
    pid = 41
    executable_name = "sb.exe"
    executable_path = Path("C:/Wonderbane/sb.exe")
    executable_sha256 = ORIGINAL
    base_address = 0x400000
    pointer_size = 4
    player, target, motion = 0x12300000, 0x12400000, 0x12500000
    state, vector = 0x12600000, 0x12700000

    def __init__(self, profile=None):
        self.profile = profile or _profile()
        self.memory = {}
        self.closed = False
        self.read_sizes = []
        self.mutate = None
        self.put(self.base_address + self.profile.player_pointer_rva, self.player)
        self.put(self.base_address + self.profile.selected_pointer_rva, self.target)
        self.put(self.motion, self.base_address + self.profile.arc_motion_vtable_rva)
        for obj in (self.player, self.target):
            self.put(obj, self.base_address + self.profile.arc_character_vtable_rva)
            self.put(obj + 0x988, self.motion, 106)
            self.put(obj + 0x9A8, 0xFFFFFFFF)
            self.put(obj + 0x9BC, 17)
            self.put(obj + 0xAF8, 0)
            self.put(obj + 0xAD0, self.state)
            self.put(obj + 0x65C, 0, 0, 0)
        self.put(self.state + 0x10, 5)
        self.put(self.state + 0x18, 1)
        self.put(self.state + 0x20, 2)

    def put(self, address, *values):
        for offset, byte in enumerate(struct.pack("<" + "I" * len(values), *values)):
            self.memory[address + offset] = byte

    def protocol(self, ids):
        self.put(self.vector, *ids)
        self.put(self.player + 0x65C, self.vector, self.vector + 4 * len(ids),
                 self.vector + 4 * len(ids))

    def read(self, address, size):
        assert 0 < size <= 64
        self.read_sizes.append(size)
        if self.mutate:
            self.mutate(address, size)
        return bytes(self.memory[address + offset] for offset in range(size))

    def close(self):
        self.closed = True


@pytest.mark.parametrize("digest", [ORIGINAL, PREPARED,
    "381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5",
    "a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a",
    "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e",
    "e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437",
    "1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c",
    "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903"])
def test_exact_reviewed_images(digest):
    memory = FakeProcessMemory()
    memory.executable_sha256 = digest
    action = NativeTargetActionReader(memory.profile, memory).observe_player()
    assert action.initiation_clear and action.action_state == 2
    assert action.animation_event_index == 17
    assert not hasattr(action, "phase") and not hasattr(action, "action_pending")


def test_unknown_image_rejected_before_memory():
    memory = FakeProcessMemory()
    memory.executable_sha256 = "ab" * 32
    with pytest.raises(NativeTargetActionCompatibilityError):
        NativeTargetActionReader(memory.profile, memory)
    assert not memory.read_sizes


@pytest.mark.parametrize("index", [0, 1, 2, 19, 0xFFFFFFFF])
def test_animation_event_index_never_implies_pending_or_new_action(index):
    memory = FakeProcessMemory()
    memory.put(memory.player + 0x9BC, index)
    memory.put(memory.player + 0x9A8, 50)
    action = NativeTargetActionReader(memory.profile, memory).observe_player()
    assert action.animation_event_index == index and action.animation_frame == 50
    assert action.initiation_clear


@pytest.mark.parametrize("state,ids", [(6, ()), (5, (563795161,)), (5, (1, 1)), (6, (1, 2))])
def test_initiation_state_or_multiset_is_pending_independently_of_action_or_animation(state, ids):
    memory = FakeProcessMemory()
    memory.put(memory.state + 0x10, state)
    memory.put(memory.state + 0x20, 1)
    memory.protocol(ids)
    action = NativeTargetActionReader(memory.profile, memory).observe_player()
    assert action.initiation_pending is True
    assert action.power_protocol_ids == ids


def test_full_multiset_reads_use_64_byte_blocks_and_preserve_duplicates():
    memory = FakeProcessMemory()
    ids = tuple(range(1, 129)) * 2
    memory.protocol(ids)
    action = NativeTargetActionReader(memory.profile, memory).observe_player()
    assert action.power_protocol_ids == ids and max(memory.read_sizes) == 64


@pytest.mark.parametrize("header", [(0, 4, 4), (0x12700000, 0x126FFFFC, 0x12700000),
    (0x12700000, 0x12700002, 0x12700004), (0x12700000, 0x12700004, 0x12700404),
    (0xFFFFFFF0, 0xFFFFFFF4, 0xFFFFFFF4)])
def test_corrupt_protocol_geometry_is_unknown_never_clear(header):
    memory = FakeProcessMemory()
    memory.put(memory.player + 0x65C, *header)
    with pytest.raises(NativeTargetActionReadError):
        NativeTargetActionReader(memory.profile, memory).observe_player()


@pytest.mark.parametrize("field", ["payload", "state", "state_pointer", "header"])
def test_changing_snapshot_cannot_authorize_admission(field):
    memory = FakeProcessMemory()
    memory.protocol((123,))
    reads = 0
    def mutate(address, size):
        nonlocal reads
        if address == memory.player:
            reads += 1
            if field == "payload":
                memory.put(memory.vector, 123 + reads)
            elif field == "state":
                memory.put(memory.state + 0x10, 5 if reads % 2 else 6)
            elif field == "state_pointer":
                memory.put(memory.player + 0xAD0, memory.state if reads % 2 else 0)
            else:
                memory.put(memory.player + 0x65C, memory.vector,
                           memory.vector + (4 if reads % 2 else 0), memory.vector + 4)
    memory.mutate = mutate
    with pytest.raises(NativeTargetActionReadError):
        NativeTargetActionReader(memory.profile, memory).observe_player()


@pytest.mark.parametrize("state", [0, 8, 0xFFFFFFFF])
def test_unqualified_initiation_state_fails_closed(state):
    memory = FakeProcessMemory()
    memory.put(memory.state + 0x10, state)
    with pytest.raises(NativeTargetActionReadError):
        NativeTargetActionReader(memory.profile, memory).observe_player()


def test_zero_protocol_id_fails_closed():
    memory = FakeProcessMemory()
    memory.protocol((0,))
    with pytest.raises(NativeTargetActionReadError):
        NativeTargetActionReader(memory.profile, memory).observe_player()


def test_selected_and_bound_target_capture_same_honest_fields():
    memory = FakeProcessMemory()
    memory.put(memory.target + 0xAF8, memory.player)
    reader = NativeTargetActionReader(memory.profile, memory)
    action = reader.observe()
    assert action == reader.observe_character(memory.target)
    assert action.targeting_player and action.initiation_pending is False
    memory.put(memory.base_address + memory.profile.selected_pointer_rva, 0)
    assert reader.observe() == NativeTargetActionObservation(False)
    assert reader.observe_character(memory.target) == action


def test_ui_selection_changes_are_diagnostic_and_do_not_invalidate_player():
    memory = FakeProcessMemory()
    count = 0
    def mutate(address, size):
        nonlocal count
        if address == memory.base_address + memory.profile.selected_pointer_rva:
            count += 1
            memory.put(address, memory.target if count % 2 else 0)
    memory.mutate = mutate
    action = NativeTargetActionReader(memory.profile, memory).observe_player()
    assert not action.selection_observed and action.initiation_clear


def test_missing_initiation_observation_is_unknown():
    action = NativePlayerActionObservation(False, 21, 0, None, None, None)
    assert action.initiation_pending is None and not action.initiation_clear
    with pytest.raises(ValueError):
        replace(action, initiation_state=5)


def test_profile_schema_roundtrip_and_rejects_false_boolean_profile():
    profile = load_bundled_native_target_action_profile()
    assert load_native_target_action_profile_text(json.dumps(asdict(profile))) == profile
    data = asdict(profile)
    data["schema_version"] = 2
    with pytest.raises(ValueError):
        load_native_target_action_profile_text(json.dumps(data))


def test_explicit_process_open_and_close():
    memory = FakeProcessMemory()
    with patch("shadowbane_lab.client_observation.native_target_action."
               "WindowsReadOnlyProcessMemory.open_for_process", return_value=memory) as opener:
        reader = open_windows_native_target_action_reader(memory.profile, process_id=41)
    opener.assert_called_once_with("sb.exe", 41)
    reader.close()
    assert memory.closed
    with pytest.raises(NativeTargetActionReadError):
        reader.observe_player()


@pytest.mark.parametrize("address,value", [
    (FakeProcessMemory.player, 0), (FakeProcessMemory.motion, 0),
    (FakeProcessMemory.player + 0x988, 3),
    (FakeProcessMemory.player + 0x98C, 5000),
    (FakeProcessMemory.player + 0x9A8, 5000),
    (FakeProcessMemory.player + 0xAF8, 7),
    (FakeProcessMemory.player + 0xAD0, 0),
])
def test_invalid_native_pointer_type_or_telemetry_is_not_admission(address, value):
    memory = FakeProcessMemory()
    memory.put(address, value)
    with pytest.raises(NativeTargetActionReadError):
        NativeTargetActionReader(memory.profile, memory).observe_player()


def test_protocol_header_change_during_chunked_read_fails_closed():
    memory = FakeProcessMemory()
    memory.protocol(tuple(range(1, 33)))
    def mutate(address, size):
        if address == memory.vector + 64:
            memory.put(memory.player + 0x660, memory.vector + 4)
    memory.mutate = mutate
    with pytest.raises(NativeTargetActionReadError, match="storage changed"):
        NativeTargetActionReader(memory.profile, memory).observe_player()


def test_partial_backend_read_is_not_admission():
    memory = FakeProcessMemory()
    read = memory.read
    memory.read = lambda address, size: read(address, size)[:-1]
    with pytest.raises(NativeTargetActionReadError, match="partial"):
        NativeTargetActionReader(memory.profile, memory).observe_player()
