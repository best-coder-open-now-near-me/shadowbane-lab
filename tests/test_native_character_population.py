from __future__ import annotations

import struct
import unittest
from pathlib import Path

from shadowbane_lab.client_observation import (
    NativeCharacterKind,
    NativeCharacterPopulationProfile,
    NativeCharacterPopulationReader,
    NativeCharacterPopulationReadError,
    NativeMemoryRegion,
    load_bundled_native_character_population_profile,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_registry import NativeObjectRegistryProfile


def _profile() -> NativeCharacterPopulationProfile:
    return NativeCharacterPopulationProfile(
        profile_id="test-population",
        executable_name="sb.exe",
        executable_sha256="a" * 64,
        pointer_size=4,
        player_pointer_rva=0x100,
        selected_pointer_rva=0x104,
        arc_character_vtable_rva=0x1000,
        object_type_offset=0x10,
        object_uuid_offset=0x14,
        player_object_uuid=53,
        npc_object_uuid=37,
        current_health_offset=0x20,
        maximum_health_offset=0x24,
        position_component_offset=0x28,
        component_value_offset=0,
        position_value_offset=0x20,
        action_target_pointer_offset=0x2C,
        sparse_data_offset=0x30,
        merchant_data_descriptor_rva=0x200,
        shopkeeper_descriptor_rva=0x208,
        banker_descriptor_rva=0x210,
        trainer_descriptor_rva=0x218,
        minion_descriptor_rva=0x220,
        pet_data_descriptor_rva=0x228,
        descriptor_key_offset=4,
        sparse_value_pointer_offset=4,
        maximum_sparse_table_bits=4,
        registry_profile=NativeObjectRegistryProfile(
            executable_name="sb.exe", executable_sha256s=("a" * 64,), pointer_size=4,
            world_pointer_rva=0x108, registry_pointer_offset=0x94, buckets_pointer_offset=4,
            exponent_offset=8, object_key_offset=0x10, maximum_table_bits=4, maximum_objects=32,
            minimum_user_address=0x10000, maximum_user_address=0x7FFF0000,
        ),
        maximum_candidate_characters=32,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFF0000,
        minimum_world_coordinate=0,
        maximum_world_coordinate=200000,
        minimum_altitude=-2000,
        maximum_altitude=20000,
    )


class FakeScanningProcess:
    pid = 73
    executable_name = "sb.exe"
    executable_path = Path("sb.exe")
    executable_sha256 = "a" * 64
    base_address = 0x400000
    pointer_size = 4

    def __init__(self, profile: NativeCharacterPopulationProfile) -> None:
        self.profile = profile
        self.memory: dict[int, bytes] = {}
        self.closed = False
        self.find_calls = 0
        self.block_sizes: list[int] = []
        self.identity_changes: dict[int, tuple[int, int]] = {}
        self.action_target_changes: dict[int, int] = {}
        self.block_reads: dict[int, int] = {}
        self.player = 0x10000
        self.crab = 0x20000
        self.trainer = 0x22000
        self._write(profile.player_pointer_rva + self.base_address, struct.pack("<I", self.player))
        self._write(
            profile.selected_pointer_rva + self.base_address,
            struct.pack("<I", self.trainer),
        )
        for index, rva in enumerate(
            (
                profile.merchant_data_descriptor_rva,
                profile.shopkeeper_descriptor_rva,
                profile.banker_descriptor_rva,
                profile.trainer_descriptor_rva,
                profile.minion_descriptor_rva,
                profile.pet_data_descriptor_rva,
            ),
            start=11,
        ):
            self._write(
                self.base_address + rva + profile.descriptor_key_offset,
                struct.pack("<I", index),
            )
        self._character(
            self.player,
            object_key=(1001, 53),
            health=(100.0, 100.0),
            position=(100.0, 5.0, -200.0),
            action_target=self.crab,
        )
        self._character(
            self.crab,
            object_key=(2001, 37),
            health=(75.0, 75.0),
            position=(108.0, 5.0, -206.0),
        )
        self._character(
            self.trainer,
            object_key=(2002, 37),
            health=(750.0, 750.0),
            position=(101.0, 5.0, -201.0),
            sparse=(14, 0x50000),
        )
        self._write(0x50000, struct.pack("<II", 14, 0x51000))
        self._write(0x51004, struct.pack("<I", 0x52000))
        self._write(0x52000, b"\x01")
        self.world, self.registry, self.buckets = 0x80000, 0x81000, 0x82000
        self._write(self.base_address + profile.registry_profile.world_pointer_rva,
                    struct.pack("<I", self.world))
        self._write(self.world + 0x94, struct.pack("<I", self.registry))
        self._write(self.registry + 4, struct.pack("<II", self.buckets, 2))
        self.set_registry(self.player, self.crab, self.trainer)

    def set_registry(self, *addresses):
        self._write(self.buckets, struct.pack("<IIII", *addresses, *([0] * (4-len(addresses)))))

    def _character(
        self,
        address: int,
        *,
        object_key: tuple[int, int],
        health: tuple[float, float],
        position: tuple[float, float, float],
        action_target: int = 0,
        sparse: tuple[int, int] | None = None,
    ) -> None:
        profile = self.profile
        block = bytearray(profile.object_read_size)
        struct.pack_into("<I", block, 0, self.base_address + profile.arc_character_vtable_rva)
        struct.pack_into("<II", block, profile.object_type_offset, *object_key)
        struct.pack_into("<ff", block, profile.current_health_offset, *health)
        component = address + 0x1000
        value = address + 0x1100
        struct.pack_into("<I", block, profile.position_component_offset, component)
        struct.pack_into("<I", block, profile.action_target_pointer_offset, action_target)
        if sparse is not None:
            _, buckets = sparse
            struct.pack_into("<II", block, profile.sparse_data_offset, buckets, 0)
        self._write(address, bytes(block))
        self._write(component, struct.pack("<I", value))
        self._write(value + profile.position_value_offset, struct.pack("<fff", *position))

    def _write(self, address: int, payload: bytes) -> None:
        self.memory[address] = payload

    def read(self, address: int, size: int) -> bytes:
        if not 0 < size <= 64:
            raise ValueError("production small read bound is 64 bytes")
        return self._read(address, size)

    def read_block(self, address: int, size: int) -> bytes:
        if not 0 < size <= 1024 * 1024:
            raise ValueError("production block read bound is 1MiB")
        self.block_sizes.append(size)
        if size != self.profile.object_read_size:
            return self._read(address, size)
        self.block_reads[address] = self.block_reads.get(address, 0) + 1
        if self.block_reads[address] == 2:
            block = bytearray(self._read(address, size))
            if address in self.identity_changes:
                struct.pack_into(
                    "<II", block, self.profile.object_type_offset, *self.identity_changes[address]
                )
            if address in self.action_target_changes:
                struct.pack_into(
                    "<I", block, self.profile.action_target_pointer_offset,
                    self.action_target_changes[address],
                )
            return bytes(block)
        return self._read(address, size)

    def _read(self, address: int, size: int) -> bytes:
        for base, payload in self.memory.items():
            if base <= address and address + size <= base + len(payload):
                offset = address - base
                return payload[offset : offset + size]
        raise OSError(f"unmapped read at 0x{address:x}")

    def query_region(self, address: int) -> NativeMemoryRegion:
        return NativeMemoryRegion(address, 0x1000, 4, 0x20000)

    def find_all(self, needles: tuple[bytes, ...], **_: object):
        self.find_calls += 1
        return {needles[0]: (self.player, self.crab, self.trainer, 0x24000)}

    def find_pointer_values_near(self, targets: tuple[int, ...], **_: object):
        return {target: () for target in targets}

    def close(self) -> None:
        self.closed = True


class NativeCharacterPopulationTests(unittest.TestCase):
    def _pet_process(self, owner: tuple[int, int] = (1001, 53)) -> FakeScanningProcess:
        process = FakeScanningProcess(_profile())
        block = bytearray(process.memory[process.crab])
        struct.pack_into("<II", block, process.profile.sparse_data_offset, 0x53000, 0)
        process.memory[process.crab] = bytes(block)
        process.memory[0x53000] = struct.pack("<II", 16, 0x54000)
        process.memory[0x54000] = struct.pack("<II", *owner)
        return process

    def test_pet_owner_is_inline_exact_key_and_protects_pet(self) -> None:
        process = self._pet_process()
        observation = NativeCharacterPopulationReader(process.profile, process).observe()
        pet = next(c for c in observation.characters if c.object_key == NativeObjectKey(2001, 37))
        self.assertEqual(NativeObjectKey(1001, 53), pet.owner_object_key)
        self.assertEqual(NativeCharacterKind.PET, pet.character_kind)
        self.assertEqual(("pet",), pet.protected_roles)
        self.assertFalse(pet.attack_eligible)
        self.assertFalse(pet.minion)

    def test_invalid_owner_key_rejects_candidate(self) -> None:
        for owner in ((0, 0), (1001, 0), (0, 53), (2001, 37)):
            with self.subTest(owner=owner):
                process = self._pet_process(owner)
                observation = NativeCharacterPopulationReader(process.profile, process).observe()
                self.assertEqual(1, len(observation.characters))
                self.assertEqual(1, observation.rejected_candidates)

    def test_unsigned_pet_and_owner_identity_are_preserved(self) -> None:
        process = self._pet_process((0xFFFFFF30, 53))
        observation = NativeCharacterPopulationReader(process.profile, process).observe()
        pet = next(c for c in observation.characters if c.character_kind == NativeCharacterKind.PET)
        self.assertEqual(0xFFFFFF30, pet.owner_object_key.object_type)

    def test_duplicate_pet_descriptor_rejects_candidate(self) -> None:
        process = self._pet_process()
        block = bytearray(process.memory[process.crab])
        struct.pack_into("<II", block, process.profile.sparse_data_offset, 0x53000, 1)
        process.memory[process.crab] = bytes(block)
        process.memory[0x53000] *= 2
        observation = NativeCharacterPopulationReader(process.profile, process).observe()
        self.assertEqual(1, len(observation.characters))

    def test_changing_owner_or_table_rejects_candidate(self) -> None:
        for changed_address in (0x54000, 0x53000):
            with self.subTest(address=changed_address):
                process = self._pet_process()
                original_read = process.read
                reads = 0

                def changing_read(
                    address: int, size: int, original_read=original_read,
                    changed_address=changed_address,
                ) -> bytes:
                    nonlocal reads
                    raw = original_read(address, size)
                    if address == changed_address:
                        reads += 1
                        if reads >= 2:
                            return struct.pack("<II", 999, 53)
                    return raw

                process.read = changing_read
                observation = NativeCharacterPopulationReader(process.profile, process).observe()
                self.assertEqual(1, len(observation.characters))

    def test_absent_pet_descriptor_does_not_prove_unowned(self) -> None:
        process = FakeScanningProcess(_profile())
        observation = NativeCharacterPopulationReader(process.profile, process).observe()
        self.assertTrue(all(c.owner_object_key is None for c in observation.characters))

    def test_dismissal_and_allocation_reuse_do_not_retain_old_pet_owner(self) -> None:
        for resummoned_pet in (True, False):
            with self.subTest(resummoned_pet=resummoned_pet):
                process = self._pet_process()
                reader = NativeCharacterPopulationReader(process.profile, process)
                first = reader.observe()
                original = next(
                    c for c in first.characters if c.character_kind == NativeCharacterKind.PET
                )
                dismissed_block = bytearray(process.memory[process.crab])
                struct.pack_into("<I", dismissed_block, 0, 0)
                process.memory[process.crab] = bytes(dismissed_block)
                process.memory[process.base_address + process.profile.selected_pointer_rva] = (
                    struct.pack("<I", 0)
                )
                process.set_registry(process.player, process.trainer)
                dismissed = reader.observe()
                self.assertIsNone(dismissed.selected_target_token)
                self.assertNotIn(original.object_key, [c.object_key for c in dismissed.characters])
                # Synthetic same-address reuse is stricter than the observed live
                # resummon, which allocated a different address as well as a new key.
                process._character(
                    process.crab, object_key=(2003, 37), health=(75, 75),
                    position=(108, 5, -206),
                    sparse=(16, 0x53000) if resummoned_pet else None,
                )
                process.set_registry(process.player, process.crab, process.trainer)
                refreshed = reader.observe()
                current = next(
                    c for c in refreshed.characters if c.object_key == NativeObjectKey(2003, 37)
                )
                self.assertEqual(original.token, current.token)
                self.assertNotEqual(original.object_key, current.object_key)
                self.assertEqual(0, process.find_calls)
                if resummoned_pet:
                    self.assertEqual(original.owner_object_key, current.owner_object_key)
                    self.assertFalse(current.attack_eligible)
                else:
                    self.assertIsNone(current.owner_object_key)
                    self.assertEqual(NativeCharacterKind.NPC, current.character_kind)
                self.assertEqual(NativeObjectKey(1001, 53), original.owner_object_key)

    def test_observes_loaded_characters_without_changing_selection(self) -> None:
        profile = _profile()
        process = FakeScanningProcess(profile)
        reader = NativeCharacterPopulationReader(
            profile,
            process,
        )

        observation = reader.observe()

        self.assertEqual(2, len(observation.characters))
        crab = next(item for item in observation.characters if item.maximum_health == 75)
        trainer = next(item for item in observation.characters if item.maximum_health == 750)
        self.assertEqual((108.0, 206.0, 5.0), (crab.lt, crab.lg, crab.altitude))
        self.assertTrue(crab.attack_eligible)
        self.assertEqual(("trainer",), trainer.protected_roles)
        self.assertFalse(trainer.attack_eligible)
        self.assertEqual(trainer.token, observation.selected_target_token)
        self.assertEqual(crab.token, observation.player_action_target_token)
        assert observation.local_player_object_key is not None
        assert crab.object_key is not None
        self.assertEqual(
            (1001, 53),
            (
                observation.local_player_object_key.object_type,
                observation.local_player_object_key.object_uuid,
            ),
        )
        self.assertEqual((2001, 37), (crab.object_key.object_type, crab.object_key.object_uuid))
        self.assertEqual(NativeCharacterKind.NPC, crab.character_kind)
        self.assertEqual(0, observation.rejected_candidates)
        self.assertEqual(1, observation.scan_generation)

    def test_registry_membership_is_refreshed_without_heap_scans(self) -> None:
        process = FakeScanningProcess(_profile())
        reader = NativeCharacterPopulationReader(process.profile, process)
        first = reader.observe()
        process.set_registry(process.player, process.trainer)
        second = reader.observe()
        self.assertEqual(2, len(first.characters))
        self.assertEqual(1, len(second.characters))
        self.assertEqual(0, process.find_calls)
        self.assertEqual(2, second.scan_generation)

    def test_local_action_target_must_stay_stable_through_population_scan(self) -> None:
        for changed_target in (0, 0x22000):
            with self.subTest(changed_target=changed_target):
                process = FakeScanningProcess(_profile())
                process.action_target_changes[process.player] = changed_target
                reader = NativeCharacterPopulationReader(process.profile, process)
                with self.assertRaisesRegex(
                    NativeCharacterPopulationReadError, "local player action target changed"
                ):
                    reader.observe()

    def test_candidate_action_target_change_rejects_only_that_candidate(self) -> None:
        process = FakeScanningProcess(_profile())
        process.action_target_changes[process.crab] = process.player
        observation = NativeCharacterPopulationReader(process.profile, process).observe()
        self.assertEqual(1, len(observation.characters))
        self.assertEqual(NativeObjectKey(2002, 37), observation.characters[0].object_key)
        self.assertEqual(1, observation.rejected_candidates)

    def test_local_action_target_rejects_unaligned_or_out_of_range_pointer(self) -> None:
        for pointer in (4, 0x20001, 0x7FFF0000, 0xFFFFFFFF):
            with self.subTest(pointer=pointer):
                process = FakeScanningProcess(_profile())
                block = bytearray(process.memory[process.player])
                struct.pack_into("<I", block, process.profile.action_target_pointer_offset, pointer)
                process.memory[process.player] = bytes(block)
                reader = NativeCharacterPopulationReader(process.profile, process)
                with self.assertRaisesRegex(
                    NativeCharacterPopulationReadError, "local player action target.*range"
                ):
                    reader.observe()

    def test_null_local_action_target_is_observed_without_inference_from_selection(self) -> None:
        process = FakeScanningProcess(_profile())
        block = bytearray(process.memory[process.player])
        struct.pack_into("<I", block, process.profile.action_target_pointer_offset, 0)
        process.memory[process.player] = bytes(block)
        observation = NativeCharacterPopulationReader(process.profile, process).observe()
        self.assertIsNone(observation.player_action_target_token)
        self.assertIsNotNone(observation.selected_target_token)

    def test_rejects_same_address_when_uuid_changes_during_read(self) -> None:
        profile = _profile()
        process = FakeScanningProcess(profile)
        process.identity_changes[process.crab] = (9999, 37)
        reader = NativeCharacterPopulationReader(profile, process)

        observation = reader.observe()

        self.assertNotIn(
            (2001, 37),
            tuple(
                (character.object_key.object_type, character.object_key.object_uuid)
                for character in observation.characters
                if character.object_key is not None
            ),
        )
        self.assertEqual(1, observation.rejected_candidates)

    def test_rejects_zero_identity_without_exposing_unknown_as_permission(self) -> None:
        profile = _profile()
        process = FakeScanningProcess(profile)
        process.identity_changes[process.crab] = (0, 0)
        reader = NativeCharacterPopulationReader(profile, process)

        observation = reader.observe()

        self.assertEqual(1, observation.rejected_candidates)

    def test_duplicate_native_keys_fail_the_coherent_snapshot(self) -> None:
        profile = _profile()
        process = FakeScanningProcess(profile)
        trainer = bytearray(process.memory[process.trainer])
        struct.pack_into("<II", trainer, profile.object_type_offset, 2001, 37)
        process.memory[process.trainer] = bytes(trainer)
        reader = NativeCharacterPopulationReader(profile, process)

        with self.assertRaisesRegex(
            NativeCharacterPopulationReadError,
            "object identities are duplicated",
        ):
            reader.observe()

    def test_unrecognized_object_uuid_remains_unknown(self) -> None:
        profile = _profile()
        process = FakeScanningProcess(profile)
        trainer = bytearray(process.memory[process.trainer])
        struct.pack_into("<II", trainer, profile.object_type_offset, 2002, 99)
        process.memory[process.trainer] = bytes(trainer)
        reader = NativeCharacterPopulationReader(profile, process)

        observation = reader.observe()

        unknown = next(
            character
            for character in observation.characters
            if character.object_key == NativeObjectKey(2002, 99)
        )
        self.assertEqual(NativeCharacterKind.UNKNOWN, unknown.character_kind)

    def test_bundled_profile_matches_current_wonderbane_layout(self) -> None:
        profile = load_bundled_native_character_population_profile()

        self.assertEqual("ef43784b", profile.executable_sha256[:8])
        self.assertEqual(0x114165C, profile.arc_character_vtable_rva)
        self.assertEqual((0x18, 0x1C), (profile.object_type_offset, profile.object_uuid_offset))
        self.assertEqual((53, 37), (profile.player_object_uuid, profile.npc_object_uuid))
        self.assertEqual(0x5CC, profile.current_health_offset)
        self.assertEqual(0x4B0, profile.position_component_offset)
        self.assertEqual(0xAF8, profile.action_target_pointer_offset)


if __name__ == "__main__":
    unittest.main()


def _zone_profile():
    from dataclasses import replace

    from shadowbane_lab.client_observation import load_bundled_native_zone_profile
    return replace(load_bundled_native_zone_profile(), executable_sha256="a" * 64,
                   player_pointer_rva=0x100)


def _put_zone(process, address=0x90000, *, name="Connauch Henge", key=(578, 79), parent=0):
    profile = _zone_profile()
    raw = bytearray(0x220)
    struct.pack_into("<II", raw, 0x10, 528, 0)
    struct.pack_into("<II", raw, 0x78, *key)
    struct.pack_into("<ffffff", raw, 0x8c, -128, 0, -128, 128, 0, 128)
    struct.pack_into("<ffff", raw, 0xa4, 1, 0, 0, 0)
    struct.pack_into("<ff", raw, 0xb4, 100, -200)
    struct.pack_into("<ff", raw, 0xbc, 0, 0)
    struct.pack_into("<I", raw, 0xec, parent)
    struct.pack_into("<ff", raw, 0xf0, 128, 128)
    text = name.encode("utf-16-le")
    buffer = address + 0x300
    struct.pack_into("<IIII", raw, 0x1bc, 0, buffer, buffer + len(text), buffer + len(text) + 2)
    process._write(address, bytes(raw))
    process._write(buffer, text + b"\0\0")
    for actor in (process.crab, process.trainer):
        process._write(actor + profile.current_zone_offset, struct.pack("<I", address))
    return address


class NativeNamedZonePopulationTests(unittest.TestCase):
    def test_opt_in_enriches_registered_npcs_without_changing_protection(self):
        process = FakeScanningProcess(_profile())
        _put_zone(process)
        frame = NativeCharacterPopulationReader(process.profile, process,
                                                zone_profile=_zone_profile()).observe()
        self.assertEqual(2, len(frame.characters))
        self.assertTrue(all(c.named_zone.name == "Connauch Henge" for c in frame.characters))
        self.assertEqual([False, True], sorted(c.attack_eligible for c in frame.characters))
        self.assertEqual(0, process.find_calls)
        self.assertTrue(all(c.named_zone.object_type == 578 for c in frame.characters))

    def test_default_does_not_read_or_publish_zone(self):
        process = FakeScanningProcess(_profile())
        _put_zone(process)
        frame = NativeCharacterPopulationReader(process.profile, process).observe()
        self.assertTrue(all(c.named_zone is None for c in frame.characters))

    def test_null_unreadable_and_invalid_placed_zones_are_unknown(self):
        for variant in ("null", "unreadable", "unplaced", "cycle"):
            with self.subTest(variant=variant):
                process = FakeScanningProcess(_profile())
                zone = _put_zone(process, key=(0, 0) if variant == "unplaced" else (578, 79),
                                 parent=0x90000 if variant == "cycle" else 0)
                if variant in ("null", "unreadable"):
                    process._write(process.crab + _zone_profile().current_zone_offset,
                                   struct.pack("<I", 0 if variant == "null" else zone + 0x10000))
                frame = NativeCharacterPopulationReader(process.profile, process,
                                                        zone_profile=_zone_profile()).observe()
                crab = next(c for c in frame.characters if c.object_key.object_type == 2001)
                self.assertIsNone(crab.named_zone)
                self.assertTrue(crab.attack_eligible)  # Existing eligibility remains separate.

    def test_zone_change_after_character_verification_drops_only_membership(self):
        process = FakeScanningProcess(_profile())
        _put_zone(process)
        original = process.read_block
        def changed(address, size):
            value = original(address, size)
            if address == process.crab and process.block_reads.get(address) == 2:
                process._write(process.crab + _zone_profile().current_zone_offset,
                               struct.pack("<I", 0))
            return value
        process.read_block = changed
        frame = NativeCharacterPopulationReader(process.profile, process,
                                                zone_profile=_zone_profile()).observe()
        crab = next(c for c in frame.characters if c.object_key.object_type == 2001)
        self.assertIsNone(crab.named_zone)
        self.assertEqual(0, frame.rejected_candidates)

    def test_character_reuse_during_zone_read_is_rejected(self):
        process = FakeScanningProcess(_profile())
        _put_zone(process)
        process.identity_changes[process.crab] = (2009, 37)
        frame = NativeCharacterPopulationReader(process.profile, process,
                                                zone_profile=_zone_profile()).observe()
        self.assertEqual(1, frame.rejected_candidates)
        self.assertFalse(any(c.object_key.object_type == 2001 for c in frame.characters))

    def test_pet_is_not_promoted_to_named_camp_npc(self):
        process = NativeCharacterPopulationTests()._pet_process()
        _put_zone(process)
        frame = NativeCharacterPopulationReader(process.profile, process,
                                                zone_profile=_zone_profile()).observe()
        pet = next(c for c in frame.characters if c.object_key.object_type == 2001)
        self.assertIsNone(pet.named_zone)
        self.assertEqual(NativeCharacterKind.PET, pet.character_kind)
        self.assertFalse(pet.attack_eligible)


    def test_public_factory_forwards_zone_profile_and_closes_one_owned_handle(self):
        from unittest.mock import patch

        from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
        from shadowbane_lab.client_observation.native_population import (
            open_windows_native_character_population_reader,
        )
        process = FakeScanningProcess(_profile())
        _put_zone(process)
        with patch.object(WindowsReadOnlyProcessMemory, "open_for_process", return_value=process):
            with open_windows_native_character_population_reader(
                process.profile, process_id=process.pid, zone_profile=_zone_profile(),
            ) as reader:
                self.assertTrue(all(c.named_zone is not None for c in reader.observe().characters))
        self.assertTrue(process.closed)

    def test_exact_detail_refresh_keeps_new_current_zone(self):
        from dataclasses import replace

        from test_pve_selection_independent_observation import readers

        process, _, action = readers()
        _put_zone(process)
        population = NativeCharacterPopulationReader(
            process.profile, process, zone_profile=replace(
                _zone_profile(), executable_sha256=process.executable_sha256))
        crab = next(c for c in population.observe().characters if c.object_key.object_type == 2001)
        _put_zone(process, name="Parent Region", key=(569, 79))
        detail = population.observe_character_detail(crab.token, crab.object_key, action)
        self.assertIsNotNone(detail)
        self.assertEqual("Parent Region", detail.character.named_zone.name)
        self.assertEqual(crab.object_key, detail.character.object_key)
