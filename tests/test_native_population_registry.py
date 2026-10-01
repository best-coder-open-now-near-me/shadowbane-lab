"""Heap remnants never own population identity after registry replacement."""

import struct

import pytest
from test_native_character_population import FakeScanningProcess, _profile
from test_pve_selection_independent_observation import readers

from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterPopulationReader,
    NativeCharacterPopulationReadError,
)


def respawn(process):
    block = bytearray(process.memory[process.crab])
    struct.pack_into("<f", block, process.profile.current_health_offset, 0.0)
    process.memory[process.crab] = bytes(block)
    replacement = 0x24000
    process._character(replacement, object_key=(2001, 37), health=(75, 75), position=(108, 5, -206))
    process.set_registry(process.player, replacement, process.trainer)
    return replacement


def test_dead_heap_remnant_and_same_key_respawn_do_not_share_target_identity():
    process, population, action = readers()
    before = population.observe()
    old = next(c for c in before.characters if c.object_key == NativeObjectKey(2001, 37))
    replacement = respawn(process)
    after = population.observe()
    new = next(c for c in after.characters if c.object_key == old.object_key)
    assert new.token != old.token and new.alive
    assert after.player_action_target_token == old.token  # AF8 is not rebound by key reuse.
    with pytest.raises(NativeCharacterPopulationReadError, match="canonical"):
        population.resolve_combat_addresses(
            local_key=before.local_player_object_key,
            target_key=old.object_key,
            target_token=old.token,
        )
    assert population.observe_character_detail(old.token, old.object_key, action) is None
    assert population.resolve_combat_addresses(
        local_key=after.local_player_object_key, target_key=new.object_key, target_token=new.token
    ) == (process.player, replacement)
    assert process.find_calls == 0


def test_unreadable_registered_object_is_not_silently_dropped():
    process = FakeScanningProcess(_profile())
    reader = NativeCharacterPopulationReader(process.profile, process)
    del process.memory[process.crab]
    with pytest.raises(NativeCharacterPopulationReadError, match="registry read failed"):
        reader.observe()


def test_registry_unregistration_during_field_refresh_rejects_population():
    process = FakeScanningProcess(_profile())
    reader = NativeCharacterPopulationReader(process.profile, process)
    original = process.read_block

    def change(address, size):
        value = original(address, size)
        if address == process.crab and size == process.profile.object_read_size:
            process.set_registry(process.player, process.trainer)
        return value

    process.read_block = change
    with pytest.raises(NativeCharacterPopulationReadError, match="membership changed"):
        reader.observe()


def test_registry_membership_change_during_detail_read_rejects_before_publish():
    process, population, action = readers()
    frame = population.observe()
    crab = next(c for c in frame.characters if c.object_key == NativeObjectKey(2001, 37))
    original = action.observe_character

    def change(address):
        value = original(address)
        process.set_registry(process.player, process.trainer)
        return value

    action.observe_character = change
    with pytest.raises(NativeCharacterPopulationReadError, match="membership changed"):
        population.observe_character_detail(crab.token, crab.object_key, action)


def test_local_actor_must_belong_to_same_registry():
    process = FakeScanningProcess(_profile())
    process.set_registry(process.crab, process.trainer)
    reader = NativeCharacterPopulationReader(process.profile, process)
    with pytest.raises(NativeCharacterPopulationReadError, match="local actor.*registry"):
        reader.observe()


@pytest.mark.parametrize("operation", ["observe", "resolve", "detail"])
def test_actor_replacement_during_final_registry_verify_is_rejected(operation):
    process, population, action = readers()
    frame = population.observe()
    crab = next(c for c in frame.characters if c.object_key == NativeObjectKey(2001, 37))
    original = population._verify_registry

    def change(snapshot):
        original(snapshot)
        process.memory[process.base_address + process.profile.player_pointer_rva] = struct.pack(
            "<I", process.trainer
        )

    population._verify_registry = change
    with pytest.raises(NativeCharacterPopulationReadError, match="local actor changed"):
        if operation == "observe":
            population.observe()
        elif operation == "resolve":
            population.resolve_combat_addresses(
                local_key=frame.local_player_object_key,
                target_key=crab.object_key,
                target_token=crab.token,
            )
        else:
            population.observe_character_detail(crab.token, crab.object_key, action)


def test_respawn_does_not_transfer_controller_engagement_or_grant_kill_credit():
    from dataclasses import replace

    from test_pve_native_proposals import ack, observe

    from shadowbane_lab.client_observation import NativePlayerPositionObservation
    from shadowbane_lab.pve.controller import PvEController
    from shadowbane_lab.pve.model import PvEControllerConfig, PvEPhase

    process = FakeScanningProcess(_profile())
    process.memory[process.base_address + process.profile.selected_pointer_rva] = struct.pack(
        "<I", 0
    )
    block = bytearray(process.memory[process.player])
    struct.pack_into("<I", block, process.profile.action_target_pointer_offset, 0)
    process.memory[process.player] = bytes(block)
    reader = NativeCharacterPopulationReader(process.profile, process)
    frame = reader.observe()
    controller = PvEController(PvEControllerConfig(camp_radius=120, selection_loss_grace_ms=1))
    position = NativePlayerPositionObservation(100, 200, 5)
    initial = replace(observe(), population=frame, player_position=position)
    proposal = controller.step(initial).combat_proposal
    assert proposal is not None
    ack(controller, proposal)
    respawn(process)
    replacement = replace(observe(100), population=reader.observe(), player_position=position)
    tracked = controller.tracked_target(replacement)
    assert tracked.character is None and tracked.token == proposal.target_token
    controller.step(replacement)
    decision = controller.step(replace(replacement, now_ms=101))
    assert decision.phase is PvEPhase.DISENGAGING
    assert decision.cleanup_request.target_token == proposal.target_token
    assert decision.cleanup_request.object_key == proposal.target_key
    assert decision.kill_confirmation is None and decision.combat_proposal is None


def test_deadline_stops_field_refresh_before_next_character():
    process = FakeScanningProcess(_profile())
    reader = NativeCharacterPopulationReader(process.profile, process)
    now = [0.0]
    reader._registry._clock = lambda: now[0]
    original = reader._read_character
    visited = []

    def slow(address):
        visited.append(address)
        value = original(address)
        now[0] = 1.0
        return value

    reader._read_character = slow
    with pytest.raises(NativeCharacterPopulationReadError, match="budget"):
        reader.observe()
    assert visited == [process.crab]


def test_public_opener_uses_bounded_block_backend_for_registry_and_character_fields(monkeypatch):
    from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
    from shadowbane_lab.client_observation.native_population import (
        open_windows_native_character_population_reader,
    )

    process = FakeScanningProcess(_profile())
    # 32 buckets require a 128-byte registry block; character records and sparse
    # role tables also exceed the backend's distinct 64-byte scalar-read limit.
    process.profile = __import__("dataclasses").replace(
        process.profile,
        registry_profile=__import__("dataclasses").replace(
            process.profile.registry_profile, maximum_table_bits=5
        ),
    )
    process.memory[process.registry + 4] = struct.pack("<II", process.buckets, 5)
    process.memory[process.buckets] += bytes(112)
    block = bytearray(process.memory[process.trainer])
    struct.pack_into("<II", block, process.profile.sparse_data_offset, 0x50000, 4)
    process.memory[process.trainer] = bytes(block)
    process.memory[0x50000] += bytes(120)
    monkeypatch.setattr(WindowsReadOnlyProcessMemory, "open_for_process", lambda name, pid: process)
    with open_windows_native_character_population_reader(
        process.profile, process_id=process.pid
    ) as reader:
        result = reader.observe()
        assert len(result.characters) == 2
        assert ("trainer",) == next(
            c.protected_roles for c in result.characters if c.maximum_health == 750
        )
    assert 128 in process.block_sizes and process.profile.object_read_size in process.block_sizes
    assert process.closed and process.find_calls == 0
