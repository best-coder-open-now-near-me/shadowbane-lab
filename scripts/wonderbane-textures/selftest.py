#!/usr/bin/env python3
"""Offline safety checks for the WonderBane texture tools."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
FLARE = ROOT / "wonderbane_texture_flare.py"
SCULPTOR = ROOT / "wonderbane_texture_sculptor.py"


def run(*arguments: object) -> None:
    command = [sys.executable, *map(str, arguments)]
    subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_inputs(root: Path) -> tuple[Path, Path, Path, Path]:
    width = height = 64
    yy, xx = np.mgrid[0:height, 0:width]
    bark = np.zeros((height, width, 3), dtype=np.uint8)
    bark[:, :, 0] = np.clip(88 + 38 * np.sin(xx / 4.0) + yy // 6, 0, 255)
    bark[:, :, 1] = np.clip(62 + 24 * np.sin(xx / 5.0) + yy // 9, 0, 255)
    bark[:, :, 2] = np.clip(43 + 16 * np.sin(xx / 6.0), 0, 255)
    bark_path = root / "bark.png"
    Image.fromarray(bark, "RGB").save(bark_path)

    foliage = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(foliage)
    draw.ellipse((6, 8, 34, 39), fill=(48, 118, 36))
    draw.ellipse((25, 20, 58, 55), fill=(92, 151, 49))
    foliage_path = root / "foliage_black.png"
    foliage.save(foliage_path)

    rgba = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(rgba)
    draw.ellipse((8, 8, 52, 54), fill=(54, 127, 43, 210))
    rgba_path = root / "foliage_rgba.png"
    rgba.save(rgba_path)

    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rectangle((0, 0, 31, 63), fill=255)
    mask_path = root / "left_half_mask.png"
    mask.save(mask_path)
    return bark_path, foliage_path, rgba_path, mask_path


def assert_image(path: Path, mode: str, size: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        assert image.mode == mode, (path, image.mode, mode)
        assert image.size == size, (path, image.size, size)
        return np.asarray(image).copy()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="wonderbane-textures-") as temporary:
        root = Path(temporary)
        bark, foliage, rgba, mask = make_inputs(root)

        bark_out = root / "bark_flared.png"
        bark_out_repeat = root / "bark_flared_repeat.png"
        bark_report = root / "bark_report.json"
        run(
            FLARE,
            bark,
            bark_out,
            "--mode",
            "bark",
            "--preset",
            "subtle",
            "--mask",
            mask,
            "--report",
            bark_report,
        )
        run(
            FLARE,
            bark,
            bark_out_repeat,
            "--mode",
            "bark",
            "--preset",
            "subtle",
            "--mask",
            mask,
        )
        original_bark = assert_image(bark, "RGB", (64, 64))
        flared_bark = assert_image(bark_out, "RGB", (64, 64))
        assert np.array_equal(
            original_bark[:, 32:],
            flared_bark[:, 32:],
        ), "mask changed protected pixels"
        assert digest(bark_out) == digest(bark_out_repeat), (
            "flare output is not deterministic"
        )
        report = json.loads(bark_report.read_text(encoding="utf-8"))
        assert report["dimensions_preserved"] and report["uv_layout_preserved"]

        rgba_out = root / "rgba_flared.png"
        run(
            FLARE,
            rgba,
            rgba_out,
            "--mode",
            "foliage",
            "--key",
            "none",
            "--output-mode",
            "rgba",
        )
        source_rgba = assert_image(rgba, "RGBA", (64, 64))
        result_rgba = assert_image(rgba_out, "RGBA", (64, 64))
        assert np.array_equal(source_rgba[:, :, 3], result_rgba[:, :, 3]), (
            "source alpha changed"
        )

        keyed_out = root / "keyed_flared.png"
        run(
            FLARE,
            foliage,
            keyed_out,
            "--mode",
            "foliage",
            "--key",
            "black",
            "--output-mode",
            "black-key",
        )
        source_keyed = assert_image(foliage, "RGB", (64, 64))
        result_keyed = assert_image(keyed_out, "RGB", (64, 64))
        background = np.all(source_keyed == 0, axis=2)
        assert np.all(result_keyed[background] == 0), (
            "pure-black key background changed"
        )

        bark_dir = root / "sculpt_bark"
        run(
            SCULPTOR,
            bark,
            bark_dir,
            "--mode",
            "bark",
            "--sizes",
            64,
            32,
            "--strength",
            "medium",
        )
        assert_image(
            bark_dir / "bark_medium_64_diffuse.png",
            "RGB",
            (64, 64),
        )
        assert_image(
            bark_dir / "bark_medium_32_diffuse.png",
            "RGB",
            (32, 32),
        )

        foliage_dir = root / "sculpt_foliage"
        run(
            SCULPTOR,
            foliage,
            foliage_dir,
            "--mode",
            "foliage",
            "--sizes",
            64,
            "--strength",
            "medium",
        )
        assert_image(
            foliage_dir / "foliage_black_medium_64_rgba.png",
            "RGBA",
            (64, 64),
        )
        assert_image(
            foliage_dir / "foliage_black_medium_64_black_key.png",
            "RGB",
            (64, 64),
        )
        assert_image(
            foliage_dir / "foliage_black_medium_64_mask.png",
            "L",
            (64, 64),
        )

    print("WonderBane texture tool self-test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
