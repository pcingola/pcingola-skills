"""Pictures: loading with an optional upscale, and the alignment of a before/after pair."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

# Unsharp mask after a Lanczos upscale: blur sigma (px) and the weight of the sharpened copy.
UNSHARP_SIGMA = 1.6
UNSHARP_AMOUNT = 0.45
# ECC alignment runs at this fraction of the picture size.
ALIGN_SCALE = 0.25


@lru_cache(maxsize=32)
def load(path: Path, upscale: int | None = None) -> np.ndarray:
    """A picture as BGR; with `upscale`, a picture narrower than that many px is enlarged to it (Lanczos)
    and sharpened with an unsharp mask, so it stays crisp when the camera zooms in."""
    im = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if im is None:
        raise ValueError(f"{path}: not a readable image")
    if upscale and im.shape[1] < upscale:
        f = upscale / im.shape[1]
        im = cv2.resize(im, None, fx=f, fy=f, interpolation=cv2.INTER_LANCZOS4)
        blur = cv2.GaussianBlur(im, (0, 0), UNSHARP_SIGMA)
        im = cv2.addWeighted(im, 1 + UNSHARP_AMOUNT, blur, -UNSHARP_AMOUNT, 0)
    im.setflags(write=False)
    return im


def upscale_factor(path: Path, upscale: int | None) -> float:
    """Width of `load(path, upscale)` over the picture's own width: how much `upscale` enlarged it."""
    return load(path, upscale).shape[1] / load(path, None).shape[1]


def resized(img: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    """img resized to the height and width of `shape` (unchanged when it has them)."""
    h, w = shape[:2]
    if img.shape[:2] == (h, w):
        return img
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA if img.shape[1] > w else cv2.INTER_CUBIC)


def align(ref: np.ndarray, mov: np.ndarray) -> tuple[np.ndarray, bool]:
    """`mov` resized to `ref`'s size and warped onto it (ECC, affine, at ALIGN_SCALE), so a wipe between them
    changes only what differs; (mov resized, False) when ECC does not converge."""
    h, w = ref.shape[:2]
    mov = resized(mov, ref.shape)
    a = cv2.resize(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), None, fx=ALIGN_SCALE, fy=ALIGN_SCALE).astype(np.float32)
    b = cv2.resize(cv2.cvtColor(mov, cv2.COLOR_BGR2GRAY), None, fx=ALIGN_SCALE, fy=ALIGN_SCALE).astype(np.float32)
    m = np.eye(2, 3, dtype=np.float32)
    try:
        _, m = cv2.findTransformECC(a, b, m, cv2.MOTION_AFFINE,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
    except cv2.error:
        return mov, False
    m[:, 2] /= ALIGN_SCALE
    return cv2.warpAffine(mov, m, (w, h), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE), True
