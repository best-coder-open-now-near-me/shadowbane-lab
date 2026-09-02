from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from jsonschema import Draft202012Validator
from PIL import Image

from shadowbane_lab.client_extension.texture_cache import (
    compare_untargeted_payloads,
    validate_cache,
)
from shadowbane_lab.client_extension.texture_patch import author_texture_patch_manifest
from shadowbane_lab.integrity import load_strict_json, pretty_json_text
from shadowbane_lab.mods import (
    AssetModManifestError,
    AssetModPackage,
    TextureProfileConflictError,
    TextureProfileError,
    compile_texture_profile,
    load_asset_mod_manifest,
    load_asset_mod_package,
    materialize_texture_profile,
)


def _payload(image: Image.Image, channels: int) -> bytes:
    mode = {1: "L", 3: "RGB", 4: "RGBA"}[channels]
    converted = image.convert(mode)
    return (
        struct.pack("<III", converted.width, converted.height, channels)
        + bytes(14)
        + converted.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
    )


def _write_cache(path: Path, resources: list[tuple[int, int, bytes, bool]]) -> None:
    data_offset = 16 + len(resources) * 20
    records: list[bytes] = []
    stored_values: list[bytes] = []
    cursor = data_offset
    for group_id, resource_id, value, compressed in resources:
        stored = zlib.compress(value) if compressed else value
        records.append(
            struct.pack(
                "<IIIII",
                group_id,
                resource_id,
                cursor,
                len(value),
                len(stored),
            )
        )
        stored_values.append(stored)
        cursor += len(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        struct.pack("<IIII", len(resources), data_offset, cursor, 0xFFFFFFFF)
        + b"".join(records)
        + b"".join(stored_values)
    )


def _write_package(
    root: Path,
    cache: Path,
    *,
    mod_id: str,
    content_build_id: str,
    replacements: dict[tuple[int, int], tuple[int, ...]],
) -> AssetModPackage:
    artifact_root = root / "compiled" / content_build_id / "textures"
    artifact_root.mkdir(parents=True)
    artifacts: dict[tuple[int, int], Path] = {}
    for key, color in sorted(replacements.items()):
        artifact = artifact_root / f"{key[0]}-{key[1]}.png"
        mode = "RGBA" if len(color) == 4 else "RGB"
        size = (8, 8) if key[1] != 202 else (4, 4)
        Image.new(mode, size, color).save(artifact)
        artifacts[key] = artifact
    patch = author_texture_patch_manifest(
        cache,
        artifacts,
        patch_id=f"{mod_id}.textures-v1",
    )
    patch_relative = f"compiled/{content_build_id}/texture-patch.json"
    patch_path = root / patch_relative
    patch_path.write_text(pretty_json_text(patch.as_dict()), encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "mod_id": mod_id,
        "name": mod_id,
        "version": "0.1.0",
        "description": "test texture package",
        "components": [
            {
                "component_id": "textures",
                "kind": "texture-set",
                "activation": "relaunch",
                "variants": [
                    {
                        "content_build_id": content_build_id,
                        "texture_patch_manifest": patch_relative,
                        "artifact_root": (
                            f"compiled/{content_build_id}/textures"
                        ),
                    }
                ],
            }
        ],
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "mod.json").write_text(pretty_json_text(manifest), encoding="utf-8")
    return load_asset_mod_package(root)


class AssetModFacadeTests(unittest.TestCase):
    def test_public_schema_accepts_the_canonical_manifest(self) -> None:
        repository = Path(__file__).parents[1]
        schema = json.loads(
            (repository / "schemas" / "asset-mod-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        manifest = {
            "schema_version": 1,
            "mod_id": "org.example.mod",
            "name": "Example",
            "version": "0.1.0",
            "description": "example texture package",
            "components": [
                {
                    "component_id": "textures",
                    "kind": "texture-set",
                    "activation": "relaunch",
                    "variants": [
                        {
                            "content_build_id": "wb-test",
                            "texture_patch_manifest": "compiled/patch.json",
                            "artifact_root": "compiled/textures",
                        }
                    ],
                }
            ],
        }

        Draft202012Validator(schema).validate(manifest)

    def test_two_texture_mods_compile_from_one_pristine_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            _write_cache(
                cache,
                [
                    (0, 101, _payload(Image.new("RGB", (8, 8), (1, 2, 3)), 3), True),
                    (0, 202, _payload(Image.new("RGB", (4, 4), (4, 5, 6)), 3), False),
                    (0, 303, _payload(Image.new("RGB", (8, 8), (7, 8, 9)), 3), True),
                ],
            )
            first = _write_package(
                root / "first",
                cache,
                mod_id="org.example.first",
                content_build_id="wb-test",
                replacements={(0, 101): (200, 20, 20)},
            )
            second = _write_package(
                root / "second",
                cache,
                mod_id="org.example.second",
                content_build_id="wb-test",
                replacements={(0, 202): (20, 200, 20)},
            )

            plan = compile_texture_profile(
                cache,
                (second, first),
                content_build_id="wb-test",
                profile_id="visual",
            )
            destination = root / "profiles" / "visual"
            receipt = materialize_texture_profile(plan, destination)

            self.assertEqual(2, len(plan.selected))
            self.assertEqual(
                ["org.example.first", "org.example.second"],
                [item.manifest.mod_id for item in plan.packages],
            )
            self.assertEqual(plan.profile_sha256, receipt.profile_sha256)
            self.assertTrue((destination / "texture-profile.json").is_file())
            result_cache = destination / "Textures.cache"
            self.assertEqual(receipt.result_cache_sha256, validate_cache(result_cache).cache_sha256)
            compare_untargeted_payloads(cache, result_cache, plan.targeted_keys)
            durable = load_strict_json(destination / "texture-profile.json")
            self.assertEqual("visual", durable["profile"]["profile_id"])
            self.assertEqual(2, len(durable["profile"]["selected_resources"]))

    def test_conflict_requires_an_explicit_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            _write_cache(
                cache,
                [(0, 101, _payload(Image.new("RGB", (8, 8), (1, 2, 3)), 3), True)],
            )
            red = _write_package(
                root / "red",
                cache,
                mod_id="org.example.red",
                content_build_id="wb-test",
                replacements={(0, 101): (200, 10, 10)},
            )
            blue = _write_package(
                root / "blue",
                cache,
                mod_id="org.example.blue",
                content_build_id="wb-test",
                replacements={(0, 101): (10, 10, 200)},
            )

            with self.assertRaises(TextureProfileConflictError) as raised:
                compile_texture_profile(
                    cache,
                    (red, blue),
                    content_build_id="wb-test",
                    profile_id="visual",
                )
            self.assertEqual((0, 101), raised.exception.conflicts[0].providers[0].key)

            plan = compile_texture_profile(
                cache,
                (red, blue),
                content_build_id="wb-test",
                profile_id="visual",
                resolutions={(0, 101): "org.example.blue:textures"},
            )
            self.assertEqual("org.example.blue", plan.selected[0].mod_id)

    def test_identical_results_deduplicate_without_load_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            _write_cache(
                cache,
                [(0, 101, _payload(Image.new("RGB", (8, 8), (1, 2, 3)), 3), True)],
            )
            first = _write_package(
                root / "first",
                cache,
                mod_id="org.example.a",
                content_build_id="wb-test",
                replacements={(0, 101): (100, 100, 100)},
            )
            second = _write_package(
                root / "second",
                cache,
                mod_id="org.example.b",
                content_build_id="wb-test",
                replacements={(0, 101): (100, 100, 100)},
            )

            plan = compile_texture_profile(
                cache,
                (second, first),
                content_build_id="wb-test",
                profile_id="visual",
            )

            self.assertEqual(1, len(plan.selected))
            self.assertEqual("org.example.a:textures", plan.selected[0].provider_id)

    def test_build_mismatch_and_changed_source_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            _write_cache(
                cache,
                [(0, 101, _payload(Image.new("RGB", (8, 8), (1, 2, 3)), 3), True)],
            )
            package = _write_package(
                root / "package",
                cache,
                mod_id="org.example.mod",
                content_build_id="wb-a",
                replacements={(0, 101): (20, 30, 40)},
            )
            with self.assertRaisesRegex(TextureProfileError, "does not support"):
                compile_texture_profile(
                    cache,
                    (package,),
                    content_build_id="wb-b",
                    profile_id="visual",
                )

            plan = compile_texture_profile(
                cache,
                (package,),
                content_build_id="wb-a",
                profile_id="visual",
            )
            cache.write_bytes(cache.read_bytes() + b"changed")
            destination = root / "profile"
            with self.assertRaisesRegex(TextureProfileError, "changed after"):
                materialize_texture_profile(plan, destination)
            self.assertFalse(destination.exists())

    def test_manifest_rejects_path_escape_and_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "schema_version": 1,
                "mod_id": "org.example.mod",
                "name": "Example",
                "version": "0.1.0",
                "description": "",
                "components": [
                    {
                        "component_id": "textures",
                        "kind": "texture-set",
                        "activation": "relaunch",
                        "variants": [
                            {
                                "content_build_id": "wb-test",
                                "texture_patch_manifest": "../escape.json",
                                "artifact_root": "textures",
                            }
                        ],
                    }
                ],
            }
            path = root / "mod.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(AssetModManifestError):
                load_asset_mod_manifest(path)

            manifest["components"][0]["variants"][0][
                "texture_patch_manifest"
            ] = "texture-patch.json"
            manifest["unexpected"] = True
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(AssetModManifestError, "fields differ"):
                load_asset_mod_manifest(path)


if __name__ == "__main__":
    unittest.main()
