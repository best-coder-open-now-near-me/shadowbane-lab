from __future__ import annotations

import struct
import unittest
from pathlib import Path

from shadowbane_lab.client_observation import (
    NativeCharacterPopulationProfile,
    NativeCharacterPopulationReader,
    NativeMemoryRegion,
    load_bundled_native_character_population_profile,
)


def _profile() -> NativeCharacterPopulationProfile:
    return NativeCharacterPopulationProfile(
        profile_id="test-population",
        executable_name="sb.exe",
        executable_sha256="a" * 64,
        pointer_size=4,
        player_pointer_rva=0x100,
        selected_pointer_rva=0x104,
        arc_character_vtable_rva=0x1000,
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
        descriptor_key_offset=4,
        sparse_value_pointer_offset=4,
        maximum_sparse_table_bits=4,
        scan_memory_type=0x20000,
        scan_protection=4,
        maximum_scan_address=0x70000000,
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
            ),
            start=11,
        ):
            self._write(
                self.base_address + rva + profile.descriptor_key_offset,
                struct.pack("<I", index),
            )
        self._character(
            self.player,
            health=(100.0, 100.0),
            position=(100.0, 5.0, -200.0),
            action_target=self.crab,
        )
        self._character(self.crab, health=(75.0, 75.0), position=(108.0, 5.0, -206.0))
        self._character(
            self.trainer,
            health=(750.0, 750.0),
            position=(101.0, 5.0, -201.0),
            sparse=(14, 0x50000),
        )
        self._write(0x50000, struct.pack("<II", 14, 0x51000))
        self._write(0x51004, struct.pack("<I", 0x52000))
        self._write(0x52000, b"\x01")

    def _character(
        self,
        address: int,
        *,
        health: tuple[float, float],
        position: tuple[float, float, float],
        action_target: int = 0,
        sparse: tuple[int, int] | None = None,
    ) -> None:
        profile = self.profile
        block = bytearray(profile.object_read_size)
        struct.pack_into("<I", block, 0, self.base_address + profile.arc_character_vtable_rva)
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
        return self._read(address, size)

    def read_block(self, address: int, size: int) -> bytes:
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
    def test_observes_loaded_characters_without_changing_selection(self) -> None:
        profile = _profile()
        process = FakeScanningProcess(profile)
        now = [0.0]
        reader = NativeCharacterPopulationReader(
            profile,
            process,
            rescan_interval_seconds=15,
            clock=lambda: now[0],
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
        self.assertEqual(1, observation.rejected_candidates)
        self.assertEqual(1, observation.scan_generation)

    def test_reuses_candidate_pool_until_rescan_interval(self) -> None:
        profile = _profile()
        process = FakeScanningProcess(profile)
        now = [0.0]
        reader = NativeCharacterPopulationReader(
            profile,
            process,
            rescan_interval_seconds=15,
            clock=lambda: now[0],
        )

        reader.observe()
        now[0] = 14.9
        reader.observe()
        self.assertEqual(1, process.find_calls)
        now[0] = 15.0
        observation = reader.observe()
        self.assertEqual(2, process.find_calls)
        self.assertEqual(2, observation.scan_generation)

    def test_bundled_profile_matches_current_wonderbane_layout(self) -> None:
        profile = load_bundled_native_character_population_profile()

        self.assertEqual("ef43784b", profile.executable_sha256[:8])
        self.assertEqual(0x114165C, profile.arc_character_vtable_rva)
        self.assertEqual(0x5CC, profile.current_health_offset)
        self.assertEqual(0x4B0, profile.position_component_offset)
        self.assertEqual(0xAF8, profile.action_target_pointer_offset)


if __name__ == "__main__":
    unittest.main()
