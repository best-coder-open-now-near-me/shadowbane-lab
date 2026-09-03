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

from shadowbane_lab.client_extension.texture_cache import (
    TextureCacheError,
    build_texture_cache_plan,
)
from shadowbane_lab.client_extension.texture_export import (
    export_texture_png,
    export_texture_samples,
    main,
    scan_texture_resources,
)


def _payload(image: Image.Image, depth: int) -> bytes:
    mode = {1: "L", 3: "RGB", 4: "RGBA"}.get(depth, "L")
    converted = image.convert(mode)
    return (
        struct.pack("<III", converted.width, converted.height, depth)
        + bytes(14)
        + converted.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
    )


def _cache(
    path: Path,
    resources: list[tuple[int, int, bytes, bool]],
) -> None:
    data_offset = 16 + len(resources) * 20
    records: list[bytes] = []
    stored_values: list[bytes] = []
    cursor = data_offset
    for group_id, resource_id, payload, compressed in resources:
        stored = zlib.compress(payload) if compressed else payload
        records.append(
            struct.pack(
                "<IIIII",
                group_id,
                resource_id,
                cursor,
                len(payload),
                len(stored),
            )
        )
        stored_values.append(stored)
        cursor += len(stored)
    path.write_bytes(
        struct.pack("<IIII", len(resources), data_offset, cursor, 0xFFFFFFFF)
        + b"".join(records)
        + b"".join(stored_values)
    )


def _asymmetric(mode: str) -> Image.Image:
    if mode == "L":
        image = Image.new(mode, (3, 2))
        image.putdata((1, 2, 3, 201, 202, 203))
        return image
    if mode == "RGB":
        image = Image.new(mode, (3, 2))
        image.putdata(
            (
                (1, 2, 3),
                (4, 5, 6),
                (7, 8, 9),
                (201, 202, 203),
                (204, 205, 206),
                (207, 208, 209),
            )
        )
        return image
    image = Image.new(mode, (3, 2))
    image.putdata(
        (
            (1, 2, 3, 0),
            (4, 5, 6, 17),
            (7, 8, 9, 34),
            (201, 202, 203, 170),
            (204, 205, 206, 221),
            (207, 208, 209, 255),
        )
    )
    return image


class TextureExportTests(unittest.TestCase):
    def test_exports_l_rgb_and_rgba_with_exact_orientation_and_alpha(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            images = ((101, _asymmetric("L"), 1), (102, _asymmetric("RGB"), 3))
            rgba = _asymmetric("RGBA")
            resources = [
                (0, resource_id, _payload(image, depth), resource_id % 2 == 0)
                for resource_id, image, depth in images
            ]
            resources.append((4, 103, _payload(rgba, 4), True))
            _cache(cache, resources)
            before = (cache.read_bytes(), cache.stat().st_mtime_ns)

            for group_id, resource_id, expected in (
                (0, 101, images[0][1]),
                (0, 102, images[1][1]),
                (4, 103, rgba),
            ):
                output = root / f"{group_id}-{resource_id}.png"
                receipt = export_texture_png(cache, group_id, resource_id, output)
                with Image.open(output) as actual:
                    actual.load()
                    self.assertEqual(expected.mode, actual.mode)
                    self.assertEqual(expected.size, actual.size)
                    self.assertEqual(expected.tobytes(), actual.tobytes())
                metadata = json.loads(output.with_suffix(".png.json").read_text())
                self.assertEqual(receipt.png_sha256, metadata["png_sha256"])

            self.assertEqual(before[0], cache.read_bytes())
            self.assertEqual(before[1], cache.stat().st_mtime_ns)

    def test_exported_png_round_trips_to_the_original_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            source = _asymmetric("RGBA")
            original = _payload(source, 4)
            _cache(cache, [(0, 101, original, True)])
            output = root / "original.png"

            receipt = export_texture_png(cache, 0, 101, output)
            plan = build_texture_cache_plan(cache, {(0, 101): output})

            self.assertEqual(hashlib.sha256(original).hexdigest(), receipt.resource.payload_sha256)
            self.assertEqual(receipt.resource.payload_sha256, plan.writes[0].result_payload_sha256)

    def test_scan_skips_nontextures_with_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            _cache(
                cache,
                [
                    (0, 101, _payload(_asymmetric("RGB"), 3), True),
                    (0, 202, b"not a texture", False),
                ],
            )

            receipt = scan_texture_resources(cache)

            self.assertEqual((101,), tuple(item.resource_id for item in receipt.textures))
            self.assertEqual(1, len(receipt.skipped))
            self.assertIn("26-byte header", receipt.skipped[0].reason)

    def test_duplicate_resource_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "Textures.cache"
            value = _payload(_asymmetric("RGB"), 3)
            _cache(cache, [(0, 101, value, True), (0, 101, value, False)])

            with self.assertRaisesRegex(TextureCacheError, "ambiguous"):
                scan_texture_resources(cache)

    def test_explicit_invalid_depth_and_missing_key_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            invalid = _payload(_asymmetric("L"), 2)
            _cache(cache, [(0, 101, invalid, False)])

            with self.assertRaisesRegex(TextureCacheError, "channel count"):
                export_texture_png(cache, 0, 101, root / "bad.png")
            with self.assertRaisesRegex(TextureCacheError, "no texture resource"):
                export_texture_png(cache, 0, 999, root / "missing.png")

    def test_repeated_export_is_deterministic_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            _cache(cache, [(0, 101, _payload(_asymmetric("RGB"), 3), True)])
            first = root / "first.png"
            second = root / "second.png"

            one = export_texture_png(cache, 0, 101, first)
            two = export_texture_png(cache, 0, 101, second)

            self.assertEqual(one.png_sha256, two.png_sha256)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            first_metadata = json.loads(first.with_suffix(".png.json").read_text())
            second_metadata = json.loads(second.with_suffix(".png.json").read_text())
            first_metadata["png_file"] = "normalized.png"
            first_metadata["metadata_file"] = "normalized.json"
            second_metadata["png_file"] = "normalized.png"
            second_metadata["metadata_file"] = "normalized.json"
            self.assertEqual(first_metadata, second_metadata)
            with self.assertRaisesRegex(TextureCacheError, "already exists"):
                export_texture_png(cache, 0, 101, first)

    def test_sample_selection_and_contact_sheet_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            resources = []
            for resource_id in range(100, 112):
                mode = "RGBA" if resource_id % 3 == 0 else "RGB"
                image = Image.effect_noise((128 + resource_id % 2 * 64, 128), resource_id)
                image = image.convert(mode)
                if mode == "RGBA":
                    image.putalpha((resource_id * 17) % 256)
                resources.append((0, resource_id, _payload(image, len(mode)), True))
            _cache(cache, resources)
            before = (cache.read_bytes(), cache.stat().st_mtime_ns)

            first = export_texture_samples(cache, root / "first", limit=7)
            second = export_texture_samples(cache, root / "second", limit=7)

            first_keys = tuple(item.resource.key for item in first.selected)
            second_keys = tuple(item.resource.key for item in second.selected)
            self.assertEqual(first_keys, second_keys)
            self.assertEqual(first.contact_sheet_sha256, second.contact_sheet_sha256)
            with Image.open(root / "first" / "contact-sheet.png") as sheet:
                sheet.verify()
            self.assertEqual(before[0], cache.read_bytes())
            self.assertEqual(before[1], cache.stat().st_mtime_ns)

    def test_cli_lists_exports_and_samples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "Textures.cache"
            image = Image.effect_noise((128, 128), 50).convert("RGB")
            _cache(cache, [(0, 101, _payload(image, 3), True)])
            index = root / "index.json"
            output = root / "one.png"

            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(("list", str(cache), "--output", str(index))),
                )
                self.assertEqual(
                    0,
                    main(("export", str(cache), "101", str(output))),
                )
                self.assertEqual(
                    0,
                    main(
                        (
                            "samples",
                            str(cache),
                            str(root / "samples"),
                            "--limit",
                            "1",
                        )
                    ),
                )
            self.assertEqual(1, json.loads(index.read_text())["valid_texture_count"])
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    2,
                    main(("export", str(cache), "101", str(output))),
                )


if __name__ == "__main__":
    unittest.main()
