#!/usr/bin/env python3
"""Shared deterministic image helpers for WonderBane texture tools."""
from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rgba(path: Path) -> tuple[np.ndarray, np.ndarray | None, str]:
    with Image.open(path) as image:
        mode = image.mode
        rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[:, :, 3]
    source_alpha = None if np.all(alpha == 255) else alpha.copy()
    return rgba[:, :, :3].copy(), source_alpha, mode


def resize(array: np.ndarray, size: tuple[int, int], *, nearest: bool = False) -> np.ndarray:
    width, height = size
    src_h, src_w = array.shape[:2]
    if (src_w, src_h) == size:
        return array.copy()
    if nearest:
        interpolation = cv2.INTER_NEAREST
    elif width < src_w or height < src_h:
        interpolation = cv2.INTER_AREA
    else:
        interpolation = cv2.INTER_CUBIC
    return cv2.resize(array, size, interpolation=interpolation)


def low_frequency_noise(height: int, width: int, seed: int, cells: int = 8) -> np.ndarray:
    rng = np.random.default_rng(seed)
    shape = (max(3, cells), max(3, cells))
    small = rng.normal(0.0, 1.0, shape).astype(np.float32)
    noise = cv2.resize(small, (width, height), interpolation=cv2.INTER_CUBIC)
    sigma = max(1.0, min(width, height) / 45.0)
    noise = cv2.GaussianBlur(noise, (0, 0), sigmaX=sigma)
    noise -= float(noise.mean())
    std = float(noise.std())
    if std > 1e-6:
        noise /= std
    return np.clip(noise, -2.0, 2.0) / 2.0


def quantize_lab(
    rgb: np.ndarray,
    mask: np.ndarray,
    colors: int,
    seed: int = 1337,
) -> np.ndarray:
    if colors <= 0 or not np.any(mask > 0):
        return rgb.copy()
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    foreground = mask > 0
    pixels = lab[foreground].reshape(-1, 3).astype(np.float32)
    unique_count = len(np.unique(pixels.astype(np.uint8), axis=0))
    k = max(1, min(colors, unique_count, len(pixels)))
    if k == 1:
        result = rgb.copy()
        result[foreground] = np.mean(rgb[foreground], axis=0).astype(np.uint8)
        return result

    rng = np.random.default_rng(seed)
    sample = pixels
    if len(sample) > 50000:
        sample = sample[rng.choice(len(sample), 50000, replace=False)]
    criteria = (
        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER,
        35,
        0.35,
    )
    cv2.setRNGSeed(seed)
    _, _, centers = cv2.kmeans(
        sample,
        k,
        None,
        criteria,
        4,
        cv2.KMEANS_PP_CENTERS,
    )
    assigned = np.empty_like(pixels)
    for start in range(0, len(pixels), 20000):
        block = pixels[start : start + 20000]
        distances = np.sum((block[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        assigned[start : start + len(block)] = centers[np.argmin(distances, axis=1)]
    result_lab = lab.copy()
    result_lab[foreground] = np.clip(assigned, 0, 255).astype(np.uint8)
    return cv2.cvtColor(result_lab, cv2.COLOR_LAB2RGB)


def infer_border_key(rgb: np.ndarray, mode: str) -> tuple[int, int, int] | None:
    if mode == "none":
        return None
    if mode == "black":
        return (0, 0, 0)
    border = np.concatenate(
        [
            rgb[:4].reshape(-1, 3),
            rgb[-4:].reshape(-1, 3),
            rgb[:, :4].reshape(-1, 3),
            rgb[:, -4:].reshape(-1, 3),
        ]
    )
    median = np.median(border, axis=0)
    key = tuple(int(round(value)) for value in median)
    if mode == "border":
        return key
    distance = np.linalg.norm(border.astype(np.float32) - median[None, :], axis=1)
    key_is_dark = max(key) <= 22
    border_is_consistent = float(np.mean(distance < 10.0)) >= 0.72
    return key if key_is_dark and border_is_consistent else None


def alpha_from_source(
    rgb: np.ndarray,
    source_alpha: np.ndarray | None,
    key_mode: str,
) -> tuple[np.ndarray, tuple[int, int, int] | None]:
    if source_alpha is not None:
        return source_alpha.astype(np.float32) / 255.0, None
    key = infer_border_key(rgb, key_mode)
    if key is None:
        return np.ones(rgb.shape[:2], dtype=np.float32), None
    distance = np.linalg.norm(
        rgb.astype(np.float32) - np.asarray(key, dtype=np.float32),
        axis=2,
    )
    return np.clip((distance - 4.0) / 24.0, 0.0, 1.0), key


def load_safety_mask(
    path: Path | None,
    size: tuple[int, int],
    invert: bool = False,
) -> np.ndarray:
    if path is None:
        return np.full((size[1], size[0]), 255, dtype=np.uint8)
    with Image.open(path) as image:
        mask_image = image.convert("L")
    if mask_image.size != size:
        message = f"mask dimensions {mask_image.size} do not match texture dimensions {size}"
        raise ValueError(message)
    mask = np.asarray(mask_image, dtype=np.uint8)
    return 255 - mask if invert else mask


def save_rgb(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb.astype(np.uint8), "RGB").save(path, optimize=True)


def save_rgba(path: Path, rgb: np.ndarray, alpha: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba = np.dstack((rgb.astype(np.uint8), alpha.astype(np.uint8)))
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)
