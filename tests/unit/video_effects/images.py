"""Small synthetic images for the video-effects tests."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def texture(w: int = 320, h: int = 180, cells: int = 6, seed: int = 0) -> np.ndarray:
    """Smooth grey noise, float32 BGR in 60..210."""
    rng = np.random.default_rng(seed)
    g = cv2.resize(rng.random((cells, int(cells * w / h) + 1)).astype(np.float32), (w, h),
                   interpolation=cv2.INTER_CUBIC)
    return np.dstack([g * 150 + 60] * 3).astype(np.float32)


def with_disc(img: np.ndarray, cx: int, cy: int, r: int, color=(0, 0, 0)) -> np.ndarray:
    out = img.copy()
    cv2.circle(out, (cx, cy), r, color, -1)
    return out


def gradient(w: int, h: int, flip: bool = False) -> np.ndarray:
    """Horizontal colour gradient, uint8 BGR."""
    x = np.linspace(0, 255, w, dtype=np.float32)
    if flip:
        x = x[::-1]
    img = np.zeros((h, w, 3), np.float32)
    img[..., 0] = x[None, :]
    img[..., 1] = np.linspace(40, 200, h, dtype=np.float32)[:, None]
    img[..., 2] = 255 - x[None, :]
    return img.astype(np.uint8)


def flat(w: int, h: int, value: int) -> np.ndarray:
    return np.full((h, w, 3), value, np.uint8)


def save(path: Path, img: np.ndarray) -> Path:
    cv2.imwrite(str(path), np.clip(img, 0, 255).astype(np.uint8))
    return path
