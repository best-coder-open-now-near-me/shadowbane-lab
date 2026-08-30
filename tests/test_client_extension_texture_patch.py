from __future__ import annotations

import hashlib
import io
import json
import struct
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from PIL import Image

from shadowbane_lab.client_extension.__main__ import main
from shadowbane_lab.client_extension.baseline import freeze_client_baseline
from shadowbane_lab.client_extension.package import (
    prepare_patched_client_copy,
    verify_patched_client_copy,
)
from shadowbane_lab.client_extension.texture_patch import (
    TexturePatchError,
    apply_texture_patch_plan,
    author_texture_patch_manifest,
    build_texture_patch_evidence,
    build_texture_patch_plan,
    load_texture_patch_manifest,
)
from shadowbane_lab.world_data.cache import CacheArchive
from tests.test_client_extension_package import _extension_dll, _manifest, _source_executable


def _payload(image: Image.Image, depth: int) -> bytes:
    mode = {3: "RGB", 4: "RGBA"}[depth]
    converted = image.convert(mode)
    return (
        struct.pack("<III", converted.width, converted.height, depth)
        + bytes(14)
        + converted.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
    )


def _cache(path: Path, resources: list[tuple[int, int, bytes]]) -> None:
    data_offset = 16 + len(resources) * 20
    records = []
    stored_values = []
    cursor = data_offset
    for group_id, resource_id, payload in resources:
        stored = zlib.compress(payload)
        records.append(
            struct.pack("<IIIII", group_id, resource_id, cursor, len(payload), len(stored))
        )
        stored_values.append(stored)
        cursor += len(stored)
    path.write_bytes(
        struct.pack("<IIII", len(resources), data_offset, cursor, 0xFFFFFFFF)
        + b"".join(records)
        + b"".join(stored_values)
    )


class ClientExtensionTexturePatchTests(unittest.TestCase):
    def test_cli_authors_create_new_manifest_and_rejects_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            _cache(cache, [(0, 101, _payload(Image.new("RGB", (16, 16)), 3))])
            replacement = root / "wreck.png"
            Image.new("RGB", (16, 16), (90, 110, 130)).save(replacement)
            manifest_path = root / "texture-patch.json"
            arguments = (
                "author-texture-patch",
                str(cache),
                str(manifest_path),
                f"101={replacement}",
                "--patch-id",
                "fixture.wreck-textures-v1",
            )

            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(arguments))
            self.assertEqual(
                "fixture.wreck-textures-v1",
                load_texture_patch_manifest(manifest_path).patch_id,
            )
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(2, main(arguments))

    def test_prepare_copy_applies_overlay_before_immutable_package_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_executable = _source_executable()
            extension = _extension_dll()
            official = root / "official"
            (official / "cache").mkdir(parents=True)
            (official / "sb.exe").write_bytes(source_executable)
            source_cache = official / "cache" / "Textures.cache"
            _cache(source_cache, [(0, 101, _payload(Image.new("RGB", (16, 16)), 3))])
            frozen = root / "frozen"
            freeze_client_baseline(
                official,
                frozen,
                repository_revision="fixture-revision",
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()
            replacement = artifacts / "wreck.png"
            Image.new("RGB", (16, 16), (130, 75, 45)).save(replacement)
            texture_manifest = author_texture_patch_manifest(
                source_cache,
                {(0, 101): replacement},
                patch_id="fixture.wreck-textures-v1",
            )
            extension_path = root / "wonderbane-extension.dll"
            extension_path.write_bytes(extension)
            destination = root / "working"

            result = prepare_patched_client_copy(
                frozen,
                destination,
                _manifest(source_executable, extension),
                extension_path,
                texture_patch_manifest=texture_manifest,
                texture_artifact_directory=artifacts,
            )
            verified = verify_patched_client_copy(destination)

            self.assertIsNotNone(result.texture_plan)
            self.assertEqual(result.evidence, verified)
            self.assertTrue(
                (destination / ".wonderbane-extension" / "texture-patches.json").is_file()
            )
            with CacheArchive(destination / "cache" / "Textures.cache") as archive:
                entry = next(item for item in archive.entries if item.resource_id == 101)
                payload_sha256 = hashlib.sha256(archive.read_resource(entry)).hexdigest()
            self.assertEqual(
                texture_manifest.replacements[0].result_payload_sha256,
                payload_sha256,
            )

    def test_authors_plans_applies_and_evidences_exact_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Textures.cache"
            _cache(
                source,
                [
                    (0, 101, _payload(Image.new("RGB", (16, 16), (20, 30, 40)), 3)),
                    (0, 202, _payload(Image.new("RGBA", (8, 8), (1, 2, 3, 90)), 4)),
                ],
            )
            source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
            artifacts = root / "artifacts"
            artifacts.mkdir()
            replacement = artifacts / "wreck.png"
            Image.new("RGBA", (16, 16), (170, 95, 42, 127)).save(replacement)

            manifest = author_texture_patch_manifest(
                source,
                {(0, 101): replacement},
                patch_id="fixture.wreck-textures-v1",
            )
            manifest_path = root / "texture-patch.json"
            manifest_path.write_text(json.dumps(manifest.as_dict()), encoding="utf-8")
            loaded = load_texture_patch_manifest(manifest_path)
            self.assertEqual(manifest, loaded)

            target = root / "working.cache"
            target.write_bytes(source.read_bytes())
            plan = build_texture_patch_plan(target, loaded, artifacts)
            apply_texture_patch_plan(target, plan)
            evidence = build_texture_patch_evidence(loaded, plan, target)

            self.assertEqual(source_sha256, manifest.source_cache_sha256)
            self.assertNotEqual(source_sha256, evidence.result_cache_sha256)
            self.assertEqual(target.stat().st_size, evidence.result_cache_size)
            self.assertEqual(source_sha256, hashlib.sha256(source.read_bytes()).hexdigest())
            with CacheArchive(target) as archive:
                entry = next(item for item in archive.entries if item.resource_id == 101)
                self.assertEqual(
                    loaded.replacements[0].result_payload_sha256,
                    hashlib.sha256(archive.read_resource(entry)).hexdigest(),
                )

    def test_rejects_tampered_or_wrong_sized_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            _cache(cache, [(0, 101, _payload(Image.new("RGB", (16, 16)), 3))])
            artifacts = root / "artifacts"
            artifacts.mkdir()
            replacement = artifacts / "wreck.png"
            Image.new("RGB", (16, 16), (80, 90, 100)).save(replacement)
            manifest = author_texture_patch_manifest(
                cache,
                {(0, 101): replacement},
                patch_id="fixture.wreck-textures-v1",
            )
            Image.new("RGB", (8, 8), (80, 90, 100)).save(replacement)

            with self.assertRaisesRegex(TexturePatchError, "artifact differs"):
                build_texture_patch_plan(cache, manifest, artifacts)

    def test_rejects_noncanonical_cache_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            _cache(cache, [(0, 101, _payload(Image.new("RGB", (16, 16)), 3))])
            replacement = root / "wreck.png"
            Image.new("RGB", (16, 16), (90, 110, 130)).save(replacement)

            with self.assertRaisesRegex(ValueError, "cache_relative_path"):
                author_texture_patch_manifest(
                    cache,
                    {(0, 101): replacement},
                    patch_id="fixture.wreck-textures-v1",
                    cache_relative_path="cache//Textures.cache",
                )


if __name__ == "__main__":
    unittest.main()
