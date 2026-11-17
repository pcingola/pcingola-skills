"""Edits made to a page image before it is warped: patches painted over areas that must not show (a
tooltip, a resting cursor, an earlier run's log), boxes or ellipses drawn as a user draws them, and a tone
change (grade)."""

from __future__ import annotations

import cv2
import numpy as np

from .geometry import ease
from .model import Draw, Grade, Patch, Shape


def px(rect: tuple[float, ...], scale: float) -> tuple[int, ...]:
    return tuple(int(round(v * scale)) for v in rect)


def apply_patches(img: np.ndarray, patches: list[Patch], scale: float) -> np.ndarray:
    if not patches:
        return img
    img = img.copy()
    ih, iw = img.shape[:2]
    for p in patches:
        x, y, w, h = px(p.rect, scale)
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, iw), min(y + h, ih)
        if x1 <= x0 or y1 <= y0:
            continue
        if p.source is not None:
            sx, sy = px(p.source, scale)
            src = img[sy + (y0 - y):sy + (y1 - y), sx + (x0 - x):sx + (x1 - x)]
            if src.shape[:2] == (y1 - y0, x1 - x0):
                img[y0:y1, x0:x1] = src
                continue
        if p.color is not None:
            img[y0:y1, x0:x1] = p.color
            continue
        ring = img[max(y0 - 2, 0):min(y1 + 2, ih), max(x0 - 2, 0):min(x1 + 2, iw)].reshape(-1, 3)
        img[y0:y1, x0:x1] = np.median(ring, 0)
    return img


def draw_marks(img: np.ndarray, draws: list[Draw], u: float, scale: float) -> np.ndarray:
    """img with each mark drawn as far as shot time u has reached (a box from its top-left corner, an
    ellipse from its left end)."""
    live = [d for d in draws if u > d.start]
    if not live:
        return img
    img = img.copy()
    for d in live:
        a = ease((u - d.start) / (d.end - d.start)) if d.end > d.start else 1.0
        x, y, w, h = (v * scale for v in d.rect)
        th = max(1, int(round(d.width * scale)))
        if d.shape is Shape.BOX:
            cv2.rectangle(img, (int(x), int(y)), (int(x + w * a), int(y + h * a)), d.color, th, cv2.LINE_AA)
        else:
            cv2.ellipse(img, (int(x + w / 2), int(y + h / 2)), (int(w / 2), int(h / 2)), 0, 180, 180 + 360 * a,
                        d.color, th, cv2.LINE_AA)
    return img


def apply_grade(img: np.ndarray, grade: Grade | None) -> np.ndarray:
    """img with the tone change `grade` (unchanged without one)."""
    if grade is None:
        return img
    lut = np.clip(255 * grade.gain * (np.arange(256, dtype=np.float32) / 255) ** grade.gamma, 0, 255)
    r, g, b = grade.tint
    chans = [np.clip(lut * k, 0, 255).astype(np.uint8) for k in (b, g, r)]
    return cv2.merge([cv2.LUT(img[..., i], chans[i]) for i in range(3)])
