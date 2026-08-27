import struct
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.world_data import (
    CacheArchive,
    ObjectNavigationFormatError,
    ObjectNavigationResolver,
    ZoneResourceKey,
    parse_mesh_navigation_bounds,
    parse_object_navigation_metadata,
    parse_render_navigation_metadata,
)


def _string(value: str) -> bytes:
    return struct.pack("<I", len(value)) + value.encode("utf-16-le")


def _key(resource_id: int, group_id: int = 0) -> bytes:
    return struct.pack("<II", group_id, resource_id)


def _object_payload(
    name: str,
    render_id: int,
    *,
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> bytes:
    return b"".join(
        (
            struct.pack("<II", 0x434C4E54, 3),
            _string(name),
            struct.pack("<B2f3f", 0, 1.0, 999_999.0, *scale),
            _key(render_id),
        )
    )


def _single_texture() -> bytes:
    return b"".join(
        (
            struct.pack("<I", 0),
            _key(901),
            struct.pack("<I4B", 0, 0, 0, 0, 1),
            _string("diffuse"),
            _string(""),
            struct.pack("<II2B", 255, 0, 0, 1),
        )
    )


def _render_payload(
    *,
    mesh_ids: tuple[int, ...] = (),
    child_ids: tuple[int, ...] = (),
    collides: bool,
    texture: bool = False,
) -> bytes:
    payload = bytearray()
    payload.extend(struct.pack("<BIBfIII", 0, 0, 0, 0.0, 0, 0, 0))
    payload.extend(_key(0))
    payload.extend(struct.pack("<fB", 0.0, bool(mesh_ids)))
    if mesh_ids:
        payload.extend(struct.pack("<I", len(mesh_ids)))
        for mesh_id in mesh_ids:
            payload.extend(_key(mesh_id))
            payload.extend(struct.pack("<2B", 0, 0))
    payload.extend(_string(""))
    payload.extend(struct.pack("<3fI", 1.0, 1.0, 1.0, bool(child_ids)))
    if child_ids:
        payload.extend(struct.pack("<3fI", 0.0, 0.0, 0.0, len(child_ids)))
        for child_id in child_ids:
            payload.extend(_key(child_id))
    payload.extend(struct.pack("<B", texture))
    if texture:
        payload.extend(struct.pack("<I", 1))
        payload.extend(_single_texture())
    payload.extend(struct.pack("<2B", collides, 1))
    return bytes(payload)


def _mesh_payload() -> bytes:
    return b"".join(
        (
            _string("trunk"),
            struct.pack("<f", 100.0),
            struct.pack("<3f", 0.0, 2.0, 0.0),
            struct.pack("<3f", -3.0, -1.0, -4.0),
            struct.pack("<3f", 3.0, 5.0, 4.0),
        )
    )


def _write_cache(path: Path, resources: list[tuple[int, int, bytes]]) -> None:
    data_offset = 16 + len(resources) * 20
    offsets = []
    cursor = data_offset
    for group_id, resource_id, payload in resources:
        offsets.append((group_id, resource_id, cursor, payload))
        cursor += len(payload)
    archive = bytearray(struct.pack("<IIII", len(resources), data_offset, cursor, 0))
    for group_id, resource_id, offset, payload in offsets:
        archive.extend(
            struct.pack("<IIIII", group_id, resource_id, offset, len(payload), len(payload))
        )
    for _, _, _, payload in offsets:
        archive.extend(payload)
    path.write_bytes(archive)


class ObjectNavigationTests(unittest.TestCase):
    def test_decodes_object_render_and_mesh_navigation_prefixes(self) -> None:
        obj = parse_object_navigation_metadata(
            _object_payload("Tree", 20, scale=(2.0, 1.0, 2.0))
        )
        render = parse_render_navigation_metadata(
            _render_payload(mesh_ids=(30,), child_ids=(21,), collides=True, texture=True)
        )
        mesh = parse_mesh_navigation_bounds(_mesh_payload())

        self.assertEqual("Tree", obj.name)
        self.assertEqual(ZoneResourceKey(0, 20), obj.render_key)
        self.assertEqual((ZoneResourceKey(0, 30),), render.mesh_keys)
        self.assertEqual((ZoneResourceKey(0, 21),), render.child_keys)
        self.assertTrue(render.collides)
        self.assertEqual(5.0, mesh.horizontal_radius)

    def test_resolver_requires_colliding_mesh_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            _write_cache(
                root / "CObjects.cache",
                [
                    (0, 10, _object_payload("Tree", 20, scale=(2.0, 1.0, 2.0))),
                    (0, 11, _object_payload("Mist", 21)),
                ],
            )
            _write_cache(
                root / "Render.cache",
                [
                    (0, 20, _render_payload(mesh_ids=(30,), collides=True)),
                    (0, 21, _render_payload(collides=True)),
                ],
            )
            _write_cache(root / "Mesh.cache", [(0, 30, _mesh_payload())])
            with (
                CacheArchive(root / "CObjects.cache") as objects,
                CacheArchive(root / "Render.cache") as renders,
                CacheArchive(root / "Mesh.cache") as meshes,
            ):
                resolver = ObjectNavigationResolver(objects, renders, meshes)
                tree = resolver.resolve(ZoneResourceKey(0, 10))
                mist = resolver.resolve(ZoneResourceKey(0, 11))

        self.assertTrue(tree.collides)
        self.assertEqual(10.0, tree.horizontal_radius)
        self.assertEqual((ZoneResourceKey(0, 30),), tree.colliding_mesh_keys)
        self.assertFalse(mist.collides)
        self.assertIsNone(mist.horizontal_radius)

    def test_rejects_truncated_and_reversed_bounds(self) -> None:
        with self.assertRaisesRegex(ObjectNavigationFormatError, "ended"):
            parse_render_navigation_metadata(_render_payload(collides=False)[:-1])
        reversed_bounds = bytearray(_mesh_payload())
        maximum_x_offset = len(_string("trunk")) + 4 + 12 + 12
        struct.pack_into("<f", reversed_bounds, maximum_x_offset, -4.0)
        with self.assertRaisesRegex(ObjectNavigationFormatError, "reversed"):
            parse_mesh_navigation_bounds(bytes(reversed_bounds))


if __name__ == "__main__":
    unittest.main()
