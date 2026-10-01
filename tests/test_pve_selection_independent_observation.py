"""Production reader composition: UI selection never owns tracked object state."""

import struct
import unittest
from dataclasses import replace

from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import (
    NativeCharacterPopulationReader,
    NativeCharacterPopulationReadError,
    NativeTargetActionReader,
    NativeTargetHealthReadError,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.pve import PvEController, PvEControllerConfig, PvERunner
from shadowbane_lab.pve.guarded_runtime import (
    NativePvEObservationSource,
    PvEObservationCoherenceError,
)
from shadowbane_lab.pve.model import PvECombatKind, PvETrackedTarget
from tests.test_native_character_population import FakeScanningProcess
from tests.test_native_character_population import _profile as population_profile
from tests.test_native_target_action import _profile as action_profile
from tests.test_pve_controller import ConfirmedCleanup, RecordingPvEDispatcher
from tests.test_pve_observation_boundary import (
    AdvancingClock,
    ConstantHealthSource,
    ConstantVitalsSource,
    _absent,
    _player,
    _target,
)


def readers():
    profile = replace(population_profile(), action_target_pointer_offset=0xAF8,
                      sparse_data_offset=0xB00)
    process = FakeScanningProcess(profile)
    action_layout = replace(action_profile(), executable_sha256="a" * 64,
                            arc_character_vtable_rva=profile.arc_character_vtable_rva)
    for index, address in enumerate((process.player, process.crab, process.trainer)):
        block = bytearray(process.memory[address])
        motion = 0x60000 + index * 0x100
        state = 0x70000 + index * 0x100
        struct.pack_into("<II", block, action_layout.current_motion_pointer_offset, motion, 107)
        struct.pack_into("<i", block, action_layout.impact_frame_offset, -1)
        struct.pack_into("<I", block, action_layout.action_pending_offset, 0)
        struct.pack_into("<I", block, action_layout.actor_state_pointer_offset, state)
        if address == process.crab:
            struct.pack_into("<I", block, action_layout.target_of_target_pointer_offset,
                             process.player)
        process.memory[address] = bytes(block)
        process.memory[motion] = struct.pack("<I", process.base_address + 0x300)
        state_block = bytearray(0x24)
        struct.pack_into("<I", state_block, 0x18, 2)
        struct.pack_into("<I", state_block, 0x20, 4)
        process.memory[state] = bytes(state_block)
    population = NativeCharacterPopulationReader(profile, process)
    action = NativeTargetActionReader(action_layout, process)
    return process, population, action


def set_key(process, address, key):
    block = bytearray(process.memory[address])
    struct.pack_into("<II", block, process.profile.object_type_offset, *key)
    process.memory[address] = bytes(block)


class SelectionIndependentObservationTests(unittest.TestCase):
    def test_population_selection_churn_preserves_actor_and_characters(self):
        process, population, _ = readers()
        read = process.read
        calls = 0

        def changing_selection(address, size):
            nonlocal calls
            if address == process.base_address + process.profile.selected_pointer_rva:
                calls += 1
                return struct.pack("<I", process.crab if calls == 1 else process.trainer)
            return read(address, size)

        process.read = changing_selection
        frame = population.observe()
        self.assertFalse(frame.selection_observed)
        self.assertIsNone(frame.selected_target_token)
        self.assertEqual(NativeObjectKey(1001, 53), frame.local_player_object_key)
        self.assertEqual(2, len(frame.characters))
        self.assertIsNotNone(frame.player_action_target_token)

    def test_local_action_survives_selection_churn_and_invalid_selection_pointer(self):
        for selected in (0, 1, 0xFFFFFFFF, 0x22000):
            with self.subTest(selected=selected):
                process, _, action = readers()
                read = process.read
                calls = 0

                def changing_selection(
                    address, size, process=process, selected=selected, read=read,
                ):
                    nonlocal calls
                    if address == process.base_address + process.profile.selected_pointer_rva:
                        calls += 1
                        return struct.pack("<I", process.crab if calls == 1 else selected)
                    return read(address, size)

                process.read = changing_selection
                frame = action.observe_player()
                self.assertFalse(frame.selection_observed)
                self.assertFalse(frame.targeting_selected)
                self.assertIsNone(frame.selected_target_token)
                self.assertIsNotNone(frame.action_target_token)
                self.assertEqual(4, frame.action_state)
                self.assertFalse(frame.native_action_idle)

    def test_bound_action_uses_existing_population_without_reading_selection_or_rescanning(self):
        process, population, action = readers()
        frame = population.observe()
        crab = next(c for c in frame.characters if c.object_key == NativeObjectKey(2001, 37))
        read = process.read

        def no_selection(address, size):
            if address == process.base_address + process.profile.selected_pointer_rva:
                raise AssertionError("bound action consulted selection")
            return read(address, size)

        process.read = no_selection
        detail = population.observe_character_detail(crab.token, crab.object_key, action)
        self.assertEqual(crab.token, detail.action.target_token)
        self.assertTrue(detail.action.targeting_player)
        self.assertEqual(0, process.find_calls)
        # Repeated stable action observations do not invent a fresh transition.
        self.assertEqual(detail.action.action_sequence,
                         population.observe_character_detail(crab.token, crab.object_key,
                                                          action).action.action_sequence)

    def test_bound_action_rejects_pointer_reuse_and_disappearance(self):
        for replacement in (None, (9001, 37)):
            with self.subTest(replacement=replacement):
                process, population, action = readers()
                frame = population.observe()
                crab = next(
                    c for c in frame.characters if c.object_key == NativeObjectKey(2001, 37)
                )
                if replacement is None:
                    process.set_registry(process.player, process.trainer)
                    del process.memory[process.crab]
                else:
                    set_key(process, process.crab, replacement)
                self.assertIsNone(population.observe_character_detail(crab.token, crab.object_key,
                                                                   action))
                self.assertEqual(0, process.find_calls)

    def test_bound_action_never_reads_unknown_token_or_wrong_process(self):
        process, population, action = readers()
        population.observe()
        self.assertIsNone(
            population.observe_character_detail("unseen", NativeObjectKey(999, 37), action)
        )
        other_process, _, other_action = readers()
        other_process.pid = process.pid + 1
        with self.assertRaisesRegex(ValueError, "population process"):
            population.observe_character_detail("unseen", NativeObjectKey(999, 37), other_action)

    def test_bound_action_rejects_local_actor_replacement_during_detail(self):
        process, population, action = readers()
        frame = population.observe()
        crab = next(c for c in frame.characters if c.object_key == NativeObjectKey(2001, 37))
        observe = action.observe_character

        def replace_actor(address):
            detail = observe(address)
            set_key(process, process.player, (1002, 53))
            return detail

        action.observe_character = replace_actor
        with self.assertRaisesRegex(NativeCharacterPopulationReadError, "local actor changed"):
            population.observe_character_detail(crab.token, crab.object_key, action)

    def test_frame_preserves_owned_action_when_selected_diagnostics_are_unreadable(self):
        process, population, action = readers()
        frame = population.observe()
        crab = next(c for c in frame.characters if c.object_key == NativeObjectKey(2001, 37))
        binding = PvETrackedTarget(crab.token, crab.object_key, crab)

        class UnreadableSelection:
            process_id = process.pid

            def observe(self):
                raise NativeTargetHealthReadError("UI selection changed")

        source = NativePvEObservationSource(
            health_reader=UnreadableSelection(),
            player_vitals_reader=ConstantVitalsSource(_player(), process_id=process.pid),
            population_reader=population, player_action_reader=action,
            target_action_reader=action, tracked_target=lambda: binding,
        )
        result = source.observe(now_ms=10, target_action_active=True, player_action_active=True)
        self.assertFalse(result.selection_observed)
        self.assertFalse(result.target.target_present)
        self.assertEqual(crab.token, result.player_action.action_target_token)
        self.assertEqual(crab.object_key, result.tracked_target_action.object_key)
        self.assertEqual(crab.token, result.tracked_target_action.action.target_token)
        self.assertNotEqual(result.player_action.selected_target_token, crab.token)
        self.assertEqual(0, process.find_calls)

    def test_frame_rejects_actor_replacement_even_when_selection_is_unchanged(self):
        process, population, action = readers()
        frame = population.observe()
        selected = frame.selected_target_token
        observe = action.observe_player

        def replace_actor():
            detail = observe()
            set_key(process, process.player, (1002, 53))
            return detail

        action.observe_player = replace_actor
        source = NativePvEObservationSource(
            health_reader=ConstantHealthSource(_target(selected)),
            player_vitals_reader=ConstantVitalsSource(_player()), population_reader=population,
            player_action_reader=action,
        )
        with self.assertRaisesRegex(PvEObservationCoherenceError, "local actor changed"):
            source.observe(now_ms=0, target_action_active=False, player_action_active=True)

    def test_frame_rejects_actual_action_target_change(self):
        process, population, action = readers()
        observe = action.observe_player

        def change_actual_target():
            block = bytearray(process.memory[process.player])
            struct.pack_into("<I", block, process.profile.action_target_pointer_offset, 0)
            process.memory[process.player] = bytes(block)
            return observe()

        action.observe_player = change_actual_target
        source = NativePvEObservationSource(
            health_reader=ConstantHealthSource(_absent()),
            player_vitals_reader=ConstantVitalsSource(_player()), population_reader=population,
            player_action_reader=action,
        )
        with self.assertRaisesRegex(PvEObservationCoherenceError, "local actor changed"):
            source.observe(now_ms=0, target_action_active=False, player_action_active=True)

    def test_unreadable_selection_global_does_not_block_population_or_actor_action(self):
        process, population, action = readers()
        read = process.read

        def no_ui_pointer(address, size):
            if address == process.base_address + process.profile.selected_pointer_rva:
                raise OSError("selection unavailable")
            return read(address, size)

        process.read = no_ui_pointer
        frame = population.observe()
        actual = action.observe_player()
        self.assertFalse(frame.selection_observed)
        self.assertFalse(actual.selection_observed)
        self.assertEqual(frame.player_action_target_token, actual.action_target_token)
        self.assertEqual(2, len(frame.characters))
        self.assertEqual(4, actual.action_state)

    def test_unavailable_action_detail_preserves_exact_character_state(self):
        process, population, action = readers()
        frame = population.observe()
        crab = next(c for c in frame.characters if c.object_key == NativeObjectKey(2001, 37))
        block = bytearray(process.memory[process.crab])
        struct.pack_into("<I", block, action.profile.current_motion_pointer_offset, 0)
        process.memory[process.crab] = bytes(block)
        detail = population.observe_character_detail(crab.token, crab.object_key, action)
        self.assertEqual(crab, detail.character)
        self.assertIsNone(detail.action)

    def test_frame_drops_replaced_object_instead_of_reusing_its_prior_health(self):
        process, population, action = readers()
        frame = population.observe()
        crab = next(c for c in frame.characters if c.object_key == NativeObjectKey(2001, 37))
        binding = PvETrackedTarget(crab.token, crab.object_key, crab)
        observe = action.observe_character

        def replace_object(address):
            detail = observe(address)
            set_key(process, address, (9001, 37))
            return detail

        action.observe_character = replace_object
        source = NativePvEObservationSource(
            health_reader=ConstantHealthSource(_absent()),
            player_vitals_reader=ConstantVitalsSource(_player()), population_reader=population,
            player_action_reader=action, target_action_reader=action,
            tracked_target=lambda: binding,
        )
        result = source.observe(now_ms=10, target_action_active=True, player_action_active=True)
        self.assertIsNone(result.tracked_target_action)
        self.assertFalse(any(c.token == crab.token for c in result.population.characters))

    def test_public_runner_carries_bound_action_into_controller_and_journal(self):
        process, population, action = readers()
        clock = AdvancingClock()
        stop = EventEmergencyStop()
        dispatcher = RecordingPvEDispatcher()
        steps = []

        def trace(step):
            steps.append(step)
            if step.tracked_target_action is not None:
                stop.trip()

        runner = PvERunner(
            controller=PvEController(PvEControllerConfig()),
            health_reader=ConstantHealthSource(_absent()),
            player_vitals_reader=ConstantVitalsSource(_player()),
            population_reader=population, player_action_reader=action,
            target_action_reader=action, dispatcher=dispatcher,
            combat_cleanup=ConfirmedCleanup(), stop_signal=stop,
            clock=clock, sleeper=clock.sleep, trace_sink=trace,
        )
        runner.run()
        detail_step = next(step for step in steps if step.tracked_target_action is not None)
        self.assertEqual(NativeObjectKey(2001, 37), detail_step.tracked_target_action.object_key)
        self.assertEqual(detail_step.decision.tracked_target.token,
                         detail_step.tracked_target_action.token)
        self.assertEqual([2001, 37], detail_step.as_dict()["tracked_target_action"]["object_key"])
        self.assertEqual(1, len(dispatcher.proposals))
        self.assertIs(dispatcher.proposals[0].kind, PvECombatKind.BIND)
        self.assertEqual(NativeObjectKey(2001, 37), dispatcher.proposals[0].target_key)
        self.assertTrue(dispatcher.proposals[0].adopted_existing_action)
        self.assertEqual(0, process.find_calls)
