import struct
import unittest

from shadowbane_lab.world_data import (
    ZoneMetadataFormatError,
    ZoneResourceKey,
    ZoneSeaLevelType,
    parse_zone_navigation_metadata,
)


def _key(group_id: int, resource_id: int) -> bytes:
    return struct.pack("<II", group_id, resource_id)


def _zone_prefix(*, water: bool = True, terrain_type: int = 7) -> bytes:
    name = "Tainted Glade"
    payload = bytearray()
    payload.extend(struct.pack("<I", 1))
    payload.extend(struct.pack("<I", len(name)))
    payload.extend(name.encode("utf-16-le"))
    payload.extend(_key(0, 0))
    payload.extend(struct.pack("<IIII", 8192, 8192, 0, 0))
    payload.extend(struct.pack("<BBB", 0, 0, 0))
    payload.extend(
        struct.pack(
            "<10f",
            384.0,
            384.0,
            100.0,
            500.0,
            0.0,
            0.0,
            -2.0,
            10.0,
            -100000.0,
            100000.0,
        )
    )
    payload.extend(struct.pack("<IfIIfIf", 1, 0.02, 0, 0, 4.0, 2, 1.0))
    payload.extend(_key(0, 0))
    payload.extend(_key(0, 0))
    payload.extend(struct.pack("<B", 0))
    payload.extend(struct.pack("<I", 0))
    payload.extend(struct.pack("<B", water))
    if water:
        payload.extend(_key(22, 33))
        payload.extend(
            struct.pack(
                "<18f",
                0.0,
                0.0,
                0.0,
                0.0,
                12.0,
                14.0,
                1.0,
                2.0,
                0.0,
                0.25,
                4.0,
                1.0,
                0.1,
                0.2,
                0.3,
                1.0,
                0.5,
                0.75,
            )
        )
    payload.extend(struct.pack("<B", 1))
    payload.extend(struct.pack("<I", terrain_type))
    if terrain_type == 7:
        payload.extend(struct.pack("<6f", 384.0, 384.0, 768.0, 768.0, -20.0, 80.0))
        payload.extend(_key(4101, 0x91000001))
    payload.extend(struct.pack("<III", 0, 0, 1))
    payload.extend(_key(0, 50214))
    payload.extend(struct.pack("<ffI", 1.0, 1.0, 8))
    payload.extend(struct.pack("<6f", 1.0, 1.0, -100.0, 1000.0, 0.0, 0.5))
    payload.extend(struct.pack("<IBI", 15, 0, 0))
    payload.extend(struct.pack("<f", 0.0))
    payload.extend(_key(4101, 0x91000002))
    payload.extend(struct.pack("<2f", 0.0, 1.0))
    return bytes(payload)


class ZoneNavigationMetadataTests(unittest.TestCase):
    def test_parses_explicit_water_and_image_terrain_contract(self) -> None:
        payload = _zone_prefix()

        metadata = parse_zone_navigation_metadata(payload)

        self.assertEqual("Tainted Glade", metadata.name)
        self.assertEqual(ZoneSeaLevelType.SELF, metadata.sea_level_type)
        self.assertTrue(metadata.has_water)
        assert metadata.water is not None
        self.assertEqual(ZoneResourceKey(22, 33), metadata.water.texture)
        self.assertEqual(0.25, metadata.water.amplitude)
        assert metadata.terrain_generation is not None
        self.assertEqual(ZoneResourceKey(4101, 0x91000001), metadata.terrain_generation.image)
        self.assertEqual(-20.0, metadata.terrain_generation.sample_height(0))
        self.assertAlmostEqual(79.609375, metadata.terrain_generation.sample_height(255))
        self.assertAlmostEqual(61.44, metadata.local_water_sample_threshold())
        self.assertEqual(1, len(metadata.terrain_object_populations))
        population = metadata.terrain_object_populations[0]
        self.assertEqual(ZoneResourceKey(0, 50214), population.object_key)
        self.assertEqual(1, population.population_layer_index(metadata.terrain_generation))
        self.assertEqual(15, population.maximum_population)
        self.assertEqual(len(payload), metadata.parsed_size)

    def test_water_threshold_is_absent_without_an_explicit_water_plane(self) -> None:
        metadata = parse_zone_navigation_metadata(_zone_prefix(water=False))

        self.assertFalse(metadata.has_water)
        self.assertIsNone(metadata.local_water_sample_threshold())

    def test_rejects_truncated_and_non_binary_payloads(self) -> None:
        with self.assertRaisesRegex(ZoneMetadataFormatError, "ended while reading"):
            parse_zone_navigation_metadata(_zone_prefix()[:-1])
        malformed = bytearray(_zone_prefix())
        name_bytes = len("Tainted Glade") * 2
        water_flag_offset = 4 + 4 + name_bytes + 8 + 16 + 3 + 40 + 28 + 16 + 1 + 4
        malformed[water_flag_offset] = 2
        with self.assertRaisesRegex(ZoneMetadataFormatError, "water flag"):
            parse_zone_navigation_metadata(bytes(malformed))


if __name__ == "__main__":
    unittest.main()
