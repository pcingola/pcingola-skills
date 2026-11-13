"""Dense optical flow between keyframes and the flow morph along a key chain.

Flow per pair A, B: grayscale, Gaussian blur, half resolution, OpenCV DIS
(PRESET_MEDIUM) A->B and B->A, Gaussian smoothing of both flows, a
forward-backward confidence 1 - err/tolerance (blurred) multiplied in, so the
flow fades to zero (a plain blend) where the two flows disagree, then
upsampled. Frame at local time s: (1-s) * warp(A, s*F_ab) + s * warp(B, (1-s)*F_ba),
float32. Keys are warped in their own dtype (uint8 from the CLI). Frames are
asked for in increasing time, so only the flows of the current pair are kept.
The sigmas and the tolerance below hold on the 2304x1296 reference canvas and
scale with frames.canvas_scale.
"""

from __future__ import annotations

from bisect import bisect_right

import cv2
import numpy as np

from .frames import canvas_scale

GRAY_SIGMA = 2.0    # blur of the grayscale input, full-resolution px
FLOW_SCALE = 2      # flow computed at 1/FLOW_SCALE resolution
FLOW_SIGMA = 8.0    # smoothing of the flow, low-resolution px
FB_TOL = 8.0        # forward-backward error, low-resolution px, at which confidence is 0


def gray(img: np.ndarray, sigma: float = GRAY_SIGMA) -> np.ndarray:
    g = cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(g, (0, 0), sigma)


def grid(h: int, w: int) -> np.ndarray:
    """(h, w, 2) pixel coordinates x, y as float32."""
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return np.dstack([xs, ys])


def confidence(f: np.ndarray, g: np.ndarray, tol: float = FB_TOL) -> np.ndarray:
    """Per-pixel confidence of flow f given the reverse flow g: following f
    then g should return to the start; 1 - |f + g(x + f)| / tol, clipped."""
    h, w = f.shape[:2]
    m = grid(h, w) + f
    g_at = cv2.remap(g, m[..., 0], m[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    err = np.linalg.norm(f + g_at, axis=2)
    return np.clip(1.0 - err / tol, 0.0, 1.0).astype(np.float32)


def reliable(f: np.ndarray, g: np.ndarray, tol: float = FB_TOL, sigma: float = FLOW_SIGMA) -> np.ndarray:
    """f scaled by its blurred forward-backward confidence."""
    conf = cv2.GaussianBlur(confidence(f, g, tol), (0, 0), sigma)
    return f * conf[..., None]


def pair_flows(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Smoothed, confidence-weighted flows a->b and b->a at the size of a."""
    h, w = a.shape[:2]
    k = canvas_scale(w, h)
    sigma, tol = FLOW_SIGMA * k, FB_TOL * k
    lw, lh = max(1, w // FLOW_SCALE), max(1, h // FLOW_SCALE)
    ga = cv2.resize(gray(a, GRAY_SIGMA * k), (lw, lh), interpolation=cv2.INTER_AREA)
    gb = cv2.resize(gray(b, GRAY_SIGMA * k), (lw, lh), interpolation=cv2.INTER_AREA)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    fab = cv2.GaussianBlur(dis.calc(ga, gb, None), (0, 0), sigma)
    fba = cv2.GaussianBlur(dis.calc(gb, ga, None), (0, 0), sigma)
    fab, fba = reliable(fab, fba, tol, sigma), reliable(fba, fab, tol, sigma)
    sx, sy = w / lw, h / lh

    def up(f: np.ndarray) -> np.ndarray:
        f = cv2.resize(f, (w, h), interpolation=cv2.INTER_LINEAR)
        f[..., 0] *= sx
        f[..., 1] *= sy
        return f

    return up(fab), up(fba)


def check_times(times: list[float], n: int) -> list[float]:
    """Chain times of n keys: 0 first, 1 last, strictly increasing."""
    if len(times) != n or times[0] != 0 or times[-1] != 1 or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError(f"key times must run from 0 to 1, strictly increasing, one per key: {times}")
    return list(times)


class FlowChain:
    """Keyframes on one canvas and the flows of consecutive pairs, computed on
    first use; only the last pair's flows are kept. Key i sits at chain time
    times[i] (default equal spacing)."""

    def __init__(self, keys: list[np.ndarray], times: list[float] | None = None):
        if len(keys) < 2:
            raise ValueError("a flow chain needs at least 2 keyframes")
        n = len(keys)
        self.times = check_times(times, n) if times is not None else [i / (n - 1) for i in range(n)]
        self.keys = keys
        self._flows: tuple[int, tuple[np.ndarray, np.ndarray]] | None = None
        h, w = keys[0].shape[:2]
        self.grid = grid(h, w)

    @property
    def n_pairs(self) -> int:
        return len(self.keys) - 1

    def flows(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        """Flows key i -> i+1 and back; recomputed when another pair was used last."""
        if self._flows is None or self._flows[0] != i:
            self._flows = None  # free the previous pair before computing the next
            self._flows = (i, pair_flows(self.keys[i], self.keys[i + 1]))
        return self._flows[1]

    def warp(self, img: np.ndarray, flow: np.ndarray, s: float) -> np.ndarray:
        m = self.grid - s * flow
        return cv2.remap(img, m[..., 0], m[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    def blend(self, i: int, s: float) -> np.ndarray:
        """Frame at local time s in segment i (keys i -> i+1)."""
        a, b = self.keys[i], self.keys[i + 1]
        if s <= 0:
            return a
        if s >= 1:
            return b
        fab, fba = self.flows(i)
        return cv2.addWeighted(self.warp(a, fab, s), 1 - s, self.warp(b, fba, 1 - s), s, 0, dtype=cv2.CV_32F)

    def segment(self, u: float) -> tuple[int, float]:
        """(segment, local time) of chain time u in [0, 1]."""
        u = min(max(u, 0.0), 1.0)
        i = min(bisect_right(self.times, u) - 1, self.n_pairs - 1)
        t0, t1 = self.times[i], self.times[i + 1]
        return i, (u - t0) / (t1 - t0)

    def at(self, u: float) -> np.ndarray:
        """Frame at chain time u in [0, 1]."""
        return self.blend(*self.segment(u))
