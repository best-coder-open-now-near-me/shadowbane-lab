#!/usr/bin/env python3
"""Add conservative broad-form flare without moving UV-compatible pixels."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from texture_common import (
    alpha_from_source,
    load_rgba,
    load_safety_mask,
    low_frequency_noise,
    quantize_lab,
    resize,
    save_rgb,
    save_rgba,
    sha256,
)


@dataclass(frozen=True)
class Preset:
    analysis: int
    flatten: float
    relief: float
    contrast: float
    variation: float
    saturation: float
    warmth: float
    grime: float
    moss: float
    foliage_volume: float
    top_light: float
    edge_light: float


PRESETS = {
    "subtle": Preset(
        256,
        0.16,
        0.12,
        0.08,
        0.025,
        0.025,
        0.015,
        0.035,
        0.0,
        0.10,
        0.07,
        0.025,
    ),
    "balanced": Preset(
        256,
        0.27,
        0.20,
        0.12,
        0.050,
        0.045,
        0.025,
        0.065,
        0.055,
        0.17,
        0.11,
        0.045,
    ),
    "weathered": Preset(
        224,
        0.34,
        0.25,
        0.14,
        0.065,
        -0.015,
        0.035,
        0.11,
        0.14,
        0.21,
        0.13,
        0.055,
    ),
}


def analysis_size(width: int, height: int, target: int) -> tuple[int, int]:
    largest = max(width, height)
    if largest <= target:
        return width, height
    ratio = target / largest
    return max(32, round(width * ratio)), max(32, round(height * ratio))


def hsv_adjust(
    rgb: np.ndarray,
    mask: np.ndarray,
    saturation: float,
    warmth: float,
) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    selected = mask > 0
    hsv[:, :, 1][selected] *= 1.0 + saturation
    clipped = np.clip(hsv, 0, 255).astype(np.uint8)
    result = cv2.cvtColor(clipped, cv2.COLOR_HSV2RGB).astype(np.float32)
    result[:, :, 0][selected] *= 1.0 + warmth
    result[:, :, 2][selected] *= 1.0 - warmth * 0.55
    return np.clip(result, 0, 255).astype(np.uint8)


def multiply(rgb: np.ndarray, multiplier: np.ndarray, mask: np.ndarray) -> np.ndarray:
    output = rgb.astype(np.float32).copy()
    selected = mask > 0
    output[selected] *= multiplier[selected, None]
    return np.clip(output, 0, 255).astype(np.uint8)


def bark_flare(
    rgb: np.ndarray,
    mask: np.ndarray,
    preset: Preset,
    seed: int,
    moss: float,
    grime: float,
    palette: int,
) -> np.ndarray:
    height, width = rgb.shape[:2]
    small_size = analysis_size(width, height, preset.analysis)
    small = resize(rgb, small_size)
    small_mask = resize(mask, small_size, nearest=True)
    diameter = max(3, round(min(small_size) / 56)) | 1
    filtered = cv2.bilateralFilter(
        small,
        diameter,
        22 + preset.flatten * 32,
        diameter,
    )
    mixed = small * (1 - preset.flatten) + filtered * preset.flatten
    small = np.clip(mixed, 0, 255).astype(np.uint8)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    blur_sigma = max(1.0, min(small_size) / 75.0)
    blur = cv2.GaussianBlur(gray, (0, 0), sigmaX=blur_sigma)
    gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    ridge = np.clip(-gx * 1.1 - gy * 0.25, -1.0, 1.0)
    local_sigma = max(2.0, min(small_size) / 24.0)
    local = gray - cv2.GaussianBlur(gray, (0, 0), sigmaX=local_sigma)
    multiplier = 1.0 + ridge * preset.relief + local * preset.contrast * 2.5
    dark = np.clip((0.50 - blur) * 2.0, 0.0, 1.0)
    multiplier -= dark * grime * 0.20
    small = multiply(small, np.clip(multiplier, 0.72, 1.28), small_mask)

    noise = low_frequency_noise(small_size[1], small_size[0], seed)
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32)
    selected = small_mask > 0
    lab[:, :, 1][selected] += noise[selected] * preset.variation * 18
    lab[:, :, 2][selected] += noise[selected] * preset.variation * 24
    if moss > 0:
        damp = np.clip(dark * (0.45 + 0.55 * (noise + 1) / 2), 0.0, 1.0) * moss
        lab[:, :, 1][selected] -= damp[selected] * 24
        lab[:, :, 2][selected] += damp[selected] * 8
    small = cv2.cvtColor(
        np.clip(lab, 0, 255).astype(np.uint8),
        cv2.COLOR_LAB2RGB,
    )
    small = hsv_adjust(small, small_mask, preset.saturation, preset.warmth)
    small = quantize_lab(small, small_mask, palette, seed)
    result = resize(small, (width, height))
    output = rgb.copy()
    output[mask > 0] = result[mask > 0]
    return output


def foliage_flare(
    rgb: np.ndarray,
    alpha: np.ndarray,
    mask: np.ndarray,
    preset: Preset,
    seed: int,
    palette: int,
) -> np.ndarray:
    height, width = rgb.shape[:2]
    small_size = analysis_size(width, height, preset.analysis)
    small = resize(rgb, small_size)
    small_mask = resize(mask, small_size, nearest=True)
    small_alpha = cv2.resize(alpha, small_size, interpolation=cv2.INTER_AREA)
    y = np.linspace(0.0, 1.0, small_size[1], dtype=np.float32)[:, None]
    top = (0.5 - y) * preset.top_light
    distance = cv2.distanceTransform(
        (small_mask > 0).astype(np.uint8),
        cv2.DIST_L2,
        5,
    )
    edge_scale = max(2.0, min(small_size) / 64.0)
    edge = np.clip(1.0 - distance / edge_scale, 0.0, 1.0)
    interior_sigma = max(1.0, min(small_size) / 25.0)
    interior = cv2.GaussianBlur(small_alpha, (0, 0), sigmaX=interior_sigma)
    if np.any(small_mask > 0):
        average = float(interior[small_mask > 0].mean())
        volume = (interior - average) * preset.foliage_volume
    else:
        volume = 0.0
    multiplier = np.clip(
        1.0 + top + volume + edge * preset.edge_light,
        0.75,
        1.25,
    )
    small = multiply(small, multiplier, small_mask)

    noise = low_frequency_noise(small_size[1], small_size[0], seed, 7)
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32)
    selected = small_mask > 0
    lab[:, :, 1][selected] += noise[selected] * preset.variation * 18
    lab[:, :, 2][selected] += noise[selected] * preset.variation * 24
    small = cv2.cvtColor(
        np.clip(lab, 0, 255).astype(np.uint8),
        cv2.COLOR_LAB2RGB,
    )
    small = hsv_adjust(
        small,
        small_mask,
        preset.saturation,
        preset.warmth * 0.4,
    )
    small = quantize_lab(small, small_mask, palette, seed)
    result = resize(small, (width, height))
    output = rgb.copy()
    output[mask > 0] = result[mask > 0]
    return output


def preview(path: Path, original: np.ndarray, result: np.ndarray) -> None:
    max_side = 600
    scale = min(1.0, max_side / max(original.shape[:2]))
    size = (
        max(1, round(original.shape[1] * scale)),
        max(1, round(original.shape[0] * scale)),
    )
    left = Image.fromarray(original, "RGB").resize(size, Image.Resampling.LANCZOS)
    right = Image.fromarray(result, "RGB").resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new(
        "RGB",
        (left.width * 2 + 84, left.height + 200),
        (29, 30, 33),
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((28, 18), "ORIGINAL", fill=(232, 232, 232), font=font)
    draw.text((56 + left.width, 18), "FLARED", fill=(232, 232, 232), font=font)
    canvas.paste(left, (28, 54))
    canvas.paste(right, (56 + left.width, 54))
    canvas.paste(
        left.resize((128, 128), Image.Resampling.LANCZOS),
        (28, left.height + 72),
    )
    canvas.paste(
        right.resize((128, 128), Image.Resampling.LANCZOS),
        (174, left.height + 72),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, optimize=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=("bark", "foliage"), required=True)
    parser.add_argument("--preset", choices=tuple(PRESETS), default="subtle")
    parser.add_argument(
        "--key",
        choices=("auto", "none", "black", "border"),
        default="auto",
    )
    parser.add_argument(
        "--output-mode",
        choices=("same", "rgba", "black-key"),
        default="same",
    )
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--palette", type=int, default=0)
    parser.add_argument("--moss", type=float)
    parser.add_argument("--grime", type=float)
    parser.add_argument("--mask", type=Path)
    parser.add_argument("--invert-mask", action="store_true")
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def output_mode(
    requested: str,
    source_alpha: np.ndarray | None,
    key: tuple[int, int, int] | None,
) -> str:
    if requested != "same":
        return requested
    if source_alpha is not None:
        return "rgba"
    if key is not None:
        return "black-key"
    return "rgb"


def main() -> int:
    args = parse_arguments()
    if not args.input.is_file():
        raise FileNotFoundError(args.input)
    if args.palette and not 2 <= args.palette <= 64:
        raise ValueError("--palette must be 0 or 2..64")

    rgb, source_alpha, original_mode = load_rgba(args.input)
    height, width = rgb.shape[:2]
    key_mode = args.key if args.mode == "foliage" else "none"
    alpha, key = alpha_from_source(rgb, source_alpha, key_mode)
    foreground = np.where(alpha >= 0.20, 255, 0).astype(np.uint8)
    user_mask = load_safety_mask(args.mask, (width, height), args.invert_mask)
    processing = np.where(
        (foreground > 0) & (user_mask >= 128),
        255,
        0,
    ).astype(np.uint8)

    preset = PRESETS[args.preset]
    moss = preset.moss if args.moss is None else args.moss
    grime = preset.grime if args.grime is None else args.grime
    if args.mode == "bark":
        result = bark_flare(
            rgb,
            processing,
            preset,
            args.seed,
            moss,
            grime,
            args.palette,
        )
    else:
        result = foliage_flare(
            rgb,
            alpha,
            processing,
            preset,
            args.seed,
            args.palette,
        )

    actual_mode = output_mode(args.output_mode, source_alpha, key)
    if actual_mode == "rgba":
        save_rgba(
            args.output,
            result,
            np.round(alpha * 255).astype(np.uint8),
        )
    elif actual_mode == "black-key":
        keyed = np.empty_like(result)
        keyed[:] = np.asarray(key or (0, 0, 0), dtype=np.uint8)
        keyed[foreground > 0] = result[foreground > 0]
        save_rgb(args.output, keyed)
    else:
        save_rgb(args.output, result)

    if args.preview:
        preview(args.preview, rgb, result)

    difference = np.abs(result.astype(np.int16) - rgb.astype(np.int16))
    if np.any(processing > 0):
        mean_change = float(np.mean(difference[processing > 0]))
    else:
        mean_change = 0.0
    report = {
        "input": str(args.input.resolve()),
        "output": str(args.output.resolve()),
        "input_sha256": sha256(args.input),
        "output_sha256": sha256(args.output),
        "input_mode": original_mode,
        "output_mode": actual_mode,
        "width": width,
        "height": height,
        "dimensions_preserved": True,
        "uv_layout_preserved": True,
        "mode": args.mode,
        "preset": args.preset,
        "preset_values": asdict(preset),
        "key_rgb": key,
        "seed": args.seed,
        "mask": str(args.mask.resolve()) if args.mask else None,
        "processing_coverage_percent": round(
            float(np.mean(processing > 0) * 100),
            4,
        ),
        "mean_absolute_channel_change": round(mean_change, 4),
        "maximum_channel_change": int(difference.max()),
    }
    report_path = args.report or args.output.with_suffix(
        args.output.suffix + ".report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
