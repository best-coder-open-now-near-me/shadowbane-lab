import io
import json
import struct
import unittest
import zlib
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from shadowbane_lab.cli import main
from shadowbane_lab.world_data import (
    CacheArchive,
    CacheArchiveFormatError,
    TerrainAlphaFormatError,
    TerrainAlphaTile,
    TerrainTileAddress,
    WorldDefinitionFormatError,
    index_terrain_alpha_maps,
    parse_world_definition,
)


def _write_cache(path: Path, resources: list[tuple[int, int, bytes, bool]]) -> None:
    data_offset = 16 + 20 * len(resources)
    directory = bytearray()
    payload = bytearray()
    for group_id, resource_id, raw, compress in resources:
        stored = zlib.compress(raw) if compress else raw
        directory.extend(
            struct.pack(
                "<IIIII",
                group_id,
                resource_id,
                data_offset + len(payload),
                len(raw),
                len(stored),
            )
        )
        payload.extend(stored)
    file_size = data_offset + len(payload)
    path.write_bytes(
        struct.pack("<IIII", len(resources), data_offset, file_size, 0xFFFF_FFFF)
        + directory
        + payload
    )


def _terrain_payload(samples: bytes, *, width: int = 2, height: int = 2) -> bytes:
    return struct.pack("<IIIII2BI", width, height, 1, 1, 0, 1, 1, len(samples)) + samples


class CacheArchiveTests(unittest.TestCase):
    def test_reads_compressed_and_raw_resources_and_preserves_duplicate_ids(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.cache"
            _write_cache(
                path,
                [
                    (7, 42, b"compressed resource", True),
                    (8, 42, b"raw resource", False),
                ],
            )

            with CacheArchive(path) as archive:
                self.assertEqual(2, archive.header.resource_count)
                self.assertEqual(0xFFFF_FFFF, archive.header.marker)
                self.assertEqual(2, len(archive.entries_for_id(42)))
                self.assertEqual(b"compressed resource", archive.read_resource(archive.entries[0]))
                self.assertEqual(b"raw resource", archive.read_resource(archive.entries[1]))

    def test_rejects_data_offset_that_overlaps_directory(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "broken.cache"
            path.write_bytes(struct.pack("<IIII", 1, 16, 16, 0xFFFF_FFFF))

            with self.assertRaisesRegex(CacheArchiveFormatError, "overlaps the directory"):
                CacheArchive(path)


class TerrainAlphaTests(unittest.TestCase):
    def test_decodes_packed_map_and_tile_coordinates(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "TerrainAlpha.cache"
            _write_cache(path, [(1176, 0x2E003AA8, _terrain_payload(b"\x00\x01\x02\x03"), True)])

            with CacheArchive(path) as archive:
                address = TerrainTileAddress.from_entry(archive.entries[0])

        self.assertEqual(1176, address.group_id)
        self.assertEqual(0x2E, address.map_id)
        self.assertEqual(15, address.tile_x)
        self.assertEqual(15, address.tile_y)

    def test_indexes_rectangular_maps_without_decoding_every_tile(self) -> None:
        resources = []
        for x in range(2):
            for y in range(3):
                resource_id = (7 << 24) | (x * 1_000 + y + 1)
                resources.append((99, resource_id, _terrain_payload(b"\x00\x01\x02\x03"), True))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "TerrainAlpha.cache"
            _write_cache(path, resources)

            with CacheArchive(path) as archive:
                maps = index_terrain_alpha_maps(archive)

        self.assertEqual(1, len(maps))
        self.assertEqual((2, 3), (maps[0].width_tiles, maps[0].height_tiles))
        self.assertTrue(maps[0].is_complete)

    def test_parses_raw_samples_in_stored_row_major_order(self) -> None:
        tile = TerrainAlphaTile.parse(_terrain_payload(bytes((10, 11, 20, 21))))

        self.assertEqual(10, tile.sample(0, 0))
        self.assertEqual(21, tile.sample(1, 1))
        with self.assertRaises(IndexError):
            tile.sample(2, 0)

    def test_rejects_sample_count_that_does_not_match_dimensions(self) -> None:
        with self.assertRaisesRegex(TerrainAlphaFormatError, "dimensions"):
            TerrainAlphaTile.parse(_terrain_payload(b"\x00\x01\x02", width=2, height=2))


class WorldDefinitionTests(unittest.TestCase):
    def test_parses_nested_zone_placements_and_preserves_unknown_attributes(self) -> None:
        world = parse_world_definition(
            """
            WORLDNAME= Aerynth
            WORLDNUM= 1
            LENGTH= 512
            WIDTH= 384
            CUSTOM= retained
            <BEGINZONE> 1
                CENTX= 65536
                CENTZ= -49152
                YROT= 90
                <BEGINZONE> 200
                    YOFFSET= 650
                    PEACEZONE= TRUE
                    ZONELOADFILE= OutskirtsA.cfg
                <ENDZONE>
            <ENDZONE>
            """
        )

        self.assertEqual(("CUSTOM", "retained"), world.attributes[0])
        self.assertEqual(2, len(world.walk_zones()))
        root, child = world.walk_zones()
        self.assertEqual((65536, -49152, 90), (root.center_x, root.center_z, root.y_rotation))
        self.assertEqual(200, child.template_id)
        self.assertEqual(650, child.y_offset)
        self.assertTrue(child.peace_zone)
        self.assertEqual("OutskirtsA.cfg", child.zone_load_file)

    def test_rejects_unbalanced_zone_tree(self) -> None:
        with self.assertRaisesRegex(WorldDefinitionFormatError, "before every zone was closed"):
            parse_world_definition(
                """
                WORLDNAME= Aerynth
                WORLDNUM= 1
                LENGTH= 512
                WIDTH= 384
                <BEGINZONE> 1
                """
            )


class WorldDataCliTests(unittest.TestCase):
    def test_reports_cache_and_terrain_map_summary(self) -> None:
        output = io.StringIO()
        resources = []
        for x in range(2):
            for y in range(2):
                resource_id = (9 << 24) | (x * 1_000 + y + 1)
                resources.append((12, resource_id, _terrain_payload(b"\x00\x01\x02\x03"), True))
        with TemporaryDirectory() as directory:
            cache_directory = Path(directory)
            _write_cache(cache_directory / "TerrainAlpha.cache", resources)
            with redirect_stdout(output):
                result = main(
                    (
                        "client",
                        "inspect-world-data",
                        str(cache_directory),
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["ok"])
        self.assertEqual(4, payload["terrain_alpha"]["tiles"])
        self.assertEqual(["2x2"], payload["terrain_alpha"]["map_shapes"])


if __name__ == "__main__":
    unittest.main()
