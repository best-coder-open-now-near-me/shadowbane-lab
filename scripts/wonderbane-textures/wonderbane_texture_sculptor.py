#!/usr/bin/env python3
"""Simplify source texture detail for a legacy Shadowbane renderer."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from texture_common import (
    alpha_from_source,
    load_rgba,
    quantize_lab,
    resize,
    save_rgb,
    save_rgba,
)


@dataclass(frozen=True)
class Preset:
    median: int
    spatial: int
    color: int
    bark_palette: int
    foliage_palette: int
    mask_scale: float
    close: int
    open: int
    min_component: float
    feather: float
    contrast: float


PRESETS = {
    "mild": Preset(3, 6, 12, 18, 14, 0.60, 1, 0, 0.00010, 0.60, 0.10),
    "medium": Preset(5, 8, 18, 14, 10, 0.42, 2, 1, 0.00025, 0.75, 0.14),
    "hard": Preset(7, 12, 24, 10, 7, 0.28, 3, 1, 0.00055, 0.90, 0.18),
}


def flatten(
    rgb: np.ndarray,
    mask: np.ndarray,
    preset: Preset,
    palette: int,
) -> np.ndarray:
    kernel = preset.median if preset.median % 2 else preset.median + 1
    result = cv2.medianBlur(rgb, max(3, kernel))
    result = cv2.pyrMeanShiftFiltering(
        result,
        sp=preset.spatial,
        sr=preset.color,
        maxLevel=1,
    )
    result = quantize_lab(result, mask, palette)
    broad = cv2.GaussianBlur(result, (0, 0), sigmaX=2.2)
    enhanced = cv2.addWeighted(
        result,
        1.0 + preset.contrast,
        broad,
        -preset.contrast,
        0,
    )
    output = rgb.copy()
    output[mask > 0] = enhanced[mask > 0]
    return output


def tile_edges(rgb: np.ndarray, ratio: float = 0.075) -> np.ndarray:
    output = rgb.astype(np.float32).copy()
    height, width = output.shape[:2]
    horizontal_band = max(2, round(width * ratio))
    for index in range(horizontal_band):
        t = index / max(1, horizontal_band - 1)
        t = t * t * (3 - 2 * t)
        shared = (output[:, index] + output[:, width - 1 - index]) * 0.5
        output[:, index] = shared * (1 - t) + output[:, index] * t
        output[:, width - 1 - index] = (
            shared * (1 - t) + output[:, width - 1 - index] * t
        )
    vertical_band = max(2, round(height * ratio))
    for index in range(vertical_band):
        t = index / max(1, vertical_band - 1)
        t = t * t * (3 - 2 * t)
        shared = (output[index] + output[height - 1 - index]) * 0.5
        output[index] = shared * (1 - t) + output[index] * t
        output[height - 1 - index] = (
            shared * (1 - t) + output[height - 1 - index] * t
        )
    return np.clip(output, 0, 255).astype(np.uint8)


def simplify_alpha(
    alpha: np.ndarray,
    size: int,
    preset: Preset,
) -> tuple[np.ndarray, np.ndarray]:
    coarse_size = max(32, round(size * preset.mask_scale))
    coarse = cv2.resize(
        alpha,
        (coarse_size, coarse_size),
        interpolation=cv2.INTER_AREA,
    )
    coarse = cv2.GaussianBlur(coarse, (0, 0), sigmaX=0.55)
    binary = np.where(coarse >= 0.17, 255, 0).astype(np.uint8)
    if preset.close:
        diameter = preset.close * 2 + 1
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (diameter, diameter),
        )
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    if preset.open:
        diameter = preset.open * 2 + 1
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (diameter, diameter),
        )
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary,
        connectivity=8,
    )
    cleaned = np.zeros_like(binary)
    minimum = max(
        2,
        round(coarse_size * coarse_size * preset.min_component),
    )
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] >= minimum:
            cleaned[labels == label] = 255
    hard = cv2.resize(
        cleaned,
        (size, size),
        interpolation=cv2.INTER_NEAREST,
    )
    soft = cv2.GaussianBlur(
        hard.astype(np.float32) / 255.0,
        (0, 0),
        preset.feather,
    )
    soft = np.clip((soft - 0.04) / 0.92, 0.0, 1.0)
    return hard, soft


def bleed(rgb: np.ndarray, mask: np.ndarray, iterations: int) -> np.ndarray:
    output = rgb.astype(np.float32).copy()
    known = (mask > 0).astype(np.uint8)
    for _ in range(iterations):
        expanded = cv2.dilate(known, np.ones((3, 3), np.uint8))
        ring = (expanded > 0) & (known == 0)
        if not np.any(ring):
            break
        count = cv2.boxFilter(
            known.astype(np.float32),
            -1,
            (3, 3),
            normalize=False,
        )
        for channel in range(3):
            values = cv2.boxFilter(
                output[:, :, channel] * known,
                -1,
                (3, 3),
                normalize=False,
            )
            output[:, :, channel][ring] = (
                values / np.maximum(count, 1.0)
            )[ring]
        known[ring] = 1
    return np.clip(output, 0, 255).astype(np.uint8)


def process(
    source: Path,
    output: Path,
    mode: str,
    sizes: list[int],
    strength: str,
    palette: int | None,
) -> list[Path]:
    rgb, source_alpha, _ = load_rgba(source)
    preset = PRESETS[strength]
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for size in sizes:
        if not 32 <= size <= 4096:
            raise ValueError("target sizes must be between 32 and 4096")
        resized = resize(rgb, (size, size))
        stem = f"{source.stem}_{strength}_{size}"
        if mode == "bark":
            mask = np.full((size, size), 255, dtype=np.uint8)
            colors = palette or preset.bark_palette
            result = tile_edges(flatten(resized, mask, preset, colors))
            path = output / f"{stem}_diffuse.png"
            save_rgb(path, result)
            written.append(path)
            continue

        alpha, _ = alpha_from_source(rgb, source_alpha, "black")
        alpha = cv2.resize(alpha, (size, size), interpolation=cv2.INTER_AREA)
        hard, soft = simplify_alpha(alpha, size, preset)
        colors = palette or preset.foliage_palette
        color = flatten(resized, hard, preset, colors)
        color = bleed(color, hard, max(3, round(size / 64)))
        rgba_path = output / f"{stem}_rgba.png"
        key_path = output / f"{stem}_black_key.png"
        mask_path = output / f"{stem}_mask.png"
        save_rgba(
            rgba_path,
            color,
            np.round(soft * 255).astype(np.uint8),
        )
        black = np.zeros_like(color)
        black[hard > 0] = color[hard > 0]
        save_rgb(key_path, black)
        Image.fromarray(hard, "L").save(mask_path, optimize=True)
        written.extend((rgba_path, key_path, mask_path))
    return written


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--mode", choices=("bark", "foliage"), required=True)
    parser.add_argument("--sizes", nargs="+", type=int, default=[256, 128])
    parser.add_argument("--strength", choices=tuple(PRESETS), default="medium")
    parser.add_argument("--palette", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    if not args.input.is_file():
        raise FileNotFoundError(args.input)
    if args.palette is not None and not 2 <= args.palette <= 64:
        raise ValueError("--palette must be between 2 and 64")
    paths = process(
        args.input,
        args.output_dir,
        args.mode,
        args.sizes,
        args.strength,
        args.palette,
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
