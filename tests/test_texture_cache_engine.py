from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import struct
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from pathlib import Path

from PIL import Image

from shadowbane_lab.client_extension.texture_cache import (
    TextureCacheError,
    apply_texture_cache_plan,
    atomic_replace_exact,
    build_texture_cache_plan,
    compare_untargeted_payloads,
    create_resource_backup,
    parse_texture_payload,
    restore_resource_backup,
    sha256_file,
    validate_cache,
)
from shadowbane_lab.client_extension.texture_patch import (
    TexturePatchError,
    apply_texture_patch_plan,
    author_texture_patch_manifest,
    build_texture_patch_plan,
)
from shadowbane_lab.world_data.cache import CacheArchive


def payload(image: Image.Image, channels: int) -> bytes:
    mode = {1: "L", 3: "RGB", 4: "RGBA"}[channels]
    converted = image.convert(mode)
    return (
        struct.pack("<III", converted.width, converted.height, channels)
        + bytes(14)
        + converted.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
    )


def write_cache(path: Path, resources: list[tuple[int, int, bytes, bool]]) -> None:
    data_offset = 16 + len(resources) * 20
    records: list[bytes] = []
    stored_values: list[bytes] = []
    cursor = data_offset
    for group_id, resource_id, value, compressed in resources:
        stored = zlib.compress(value) if compressed else value
        records.append(
            struct.pack("<IIIII", group_id, resource_id, cursor, len(value), len(stored))
        )
        stored_values.append(stored)
        cursor += len(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        struct.pack("<IIII", len(resources), data_offset, cursor, 0xFFFFFFFF)
        + b"".join(records)
        + b"".join(stored_values)
    )


class TextureCacheEngineTests(unittest.TestCase):
    def test_plan_apply_and_validate_multiple_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            write_cache(
                cache,
                [
                    (0, 101, payload(Image.new("RGB", (16, 16), (1, 2, 3)), 3), True),
                    (4, 202, payload(Image.new("RGBA", (8, 8), (4, 5, 6, 77)), 4), False),
                    (0, 303, payload(Image.new("RGB", (4, 4), (7, 8, 9)), 3), True),
                ],
            )
            baseline = root / "baseline.cache"
            baseline.write_bytes(cache.read_bytes())
            first = root / "first.png"
            second = root / "second.png"
            Image.new("RGB", (16, 16), (200, 100, 50)).save(first)
            Image.new("RGBA", (8, 8), (30, 40, 50, 90)).save(second)

            plan = build_texture_cache_plan(cache, {(0, 101): first, (4, 202): second})
            result_sha256, result_size = apply_texture_cache_plan(cache, plan)
            validation = validate_cache(cache)

            self.assertEqual(result_sha256, validation.cache_sha256)
            self.assertEqual(result_size, validation.cache_size)
            self.assertEqual(3, validation.resource_count)
            compare_untargeted_payloads(baseline, cache, plan.targeted_keys)
            with CacheArchive(cache) as archive:
                indexed = {(item.group_id, item.resource_id): item for item in archive.entries}
                self.assertEqual(
                    plan.writes[0].result_payload_sha256,
                    hashlib.sha256(archive.read_resource(indexed[(0, 101)])).hexdigest(),
                )
                self.assertEqual(
                    plan.writes[1].result_payload_sha256,
                    hashlib.sha256(archive.read_resource(indexed[(4, 202)])).hexdigest(),
                )

    def test_compact_backup_restores_exact_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            write_cache(
                cache,
                [(0, 101, payload(Image.new("RGB", (8, 8), (1, 2, 3)), 3), True)],
            )
            original = cache.read_bytes()
            artifact = root / "replacement.png"
            Image.effect_noise((8, 8), 100).convert("RGB").save(artifact)
            plan = build_texture_cache_plan(cache, {(0, 101): artifact})
            backup = root / "exact.wbt-backup.zip"
            create_resource_backup(cache, backup, plan)
            apply_texture_cache_plan(cache, plan)
            self.assertNotEqual(original, cache.read_bytes())
            restored = restore_resource_backup(backup)
            self.assertEqual(cache.resolve(), restored)
            self.assertEqual(original, cache.read_bytes())
            self.assertEqual(plan.source_cache_sha256, sha256_file(cache))

    def test_plan_rejects_changed_cache_and_tampered_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            write_cache(
                cache,
                [(0, 101, payload(Image.new("RGB", (8, 8), (1, 2, 3)), 3), True)],
            )
            artifact = root / "replacement.png"
            Image.new("RGB", (8, 8), (8, 9, 10)).save(artifact)
            manifest = author_texture_patch_manifest(
                cache, {(0, 101): artifact}, patch_id="fixture.texture-v1"
            )
            Image.new("RGB", (4, 4), (8, 9, 10)).save(artifact)
            with self.assertRaisesRegex(TexturePatchError, "artifact differs"):
                build_texture_patch_plan(cache, manifest, root)

            Image.new("RGB", (8, 8), (8, 9, 10)).save(artifact)
            plan = build_texture_cache_plan(cache, {(0, 101): artifact})
            cache.write_bytes(cache.read_bytes() + b"changed")
            with self.assertRaisesRegex(TextureCacheError, "changed after"):
                apply_texture_cache_plan(cache, plan)

    def test_client_extension_wrapper_preserves_manifest_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            write_cache(
                cache,
                [(0, 101, payload(Image.new("RGB", (8, 8), (1, 2, 3)), 3), True)],
            )
            artifact = root / "replacement.png"
            Image.new("RGB", (8, 8), (80, 90, 100)).save(artifact)
            manifest = author_texture_patch_manifest(
                cache, {(0, 101): artifact}, patch_id="fixture.texture-v1"
            )
            plan = build_texture_patch_plan(cache, manifest, root)
            apply_texture_patch_plan(cache, plan)
            self.assertEqual(1, len(plan.writes))
            self.assertEqual(3, manifest.replacements[0].depth)
            self.assertEqual(
                manifest.replacements[0].result_payload_sha256,
                validate_cache(cache).resources[0].payload_sha256,
            )

    def test_untargeted_comparison_and_payload_parser_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = root / "before.cache"
            after = root / "after.cache"
            resources = [
                (0, 1, payload(Image.new("RGB", (4, 4), (1, 2, 3)), 3), True),
                (0, 2, payload(Image.new("RGB", (4, 4), (4, 5, 6)), 3), True),
            ]
            write_cache(before, resources)
            write_cache(after, resources)
            artifact = root / "changed.png"
            Image.new("RGB", (4, 4), (9, 9, 9)).save(artifact)
            apply_texture_cache_plan(after, build_texture_cache_plan(after, {(0, 2): artifact}))
            with self.assertRaisesRegex(TextureCacheError, "untargeted"):
                compare_untargeted_payloads(before, after, {(0, 1)})
            with self.assertRaises(TextureCacheError):
                parse_texture_payload(bytes(26))

    def test_atomic_replace_and_compatibility_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"new")
            destination.write_bytes(b"old")
            digest = sha256_file(source)
            self.assertEqual(digest, atomic_replace_exact(source, destination, expected_sha256=digest))
            self.assertEqual(b"new", destination.read_bytes())

            cache = root / "Textures.cache"
            write_cache(
                cache,
                [(0, 101, payload(Image.new("RGB", (4, 4), (1, 2, 3)), 3), True)],
            )
            artifact = root / "replacement.png"
            Image.new("RGB", (4, 4), (10, 20, 30)).save(artifact)
            script = (
                Path(__file__).parents[1]
                / "scripts"
                / "wonderbane-textures"
                / "wonderbane_texture_cache.py"
            )
            spec = importlib.util.spec_from_file_location("texture_cache_cli", script)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, module.main(["plan", str(cache), f"101={artifact}"]))
            parsed = json.loads(output.getvalue())
            self.assertEqual(101, parsed["replacements"][0]["resource_id"])


if __name__ == "__main__":
    unittest.main()
