"""The transformations. Each takes keyframes already cover-fitted to the work
canvas (uint8 from the CLI, float32 works too) and returns a function t -> canvas frame, t from 0 (start) to
1 (end) linear in clip time; easing is applied here."""

from __future__ import annotations

import math
from typing import Callable

import cv2
import numpy as np

from .flow import FlowChain
from .frames import canvas_scale, smoothstep

Frame = Callable[[float], np.ndarray]

# Delay-field constants of the region effect, defined on the reference canvas;
# the blur sigmas scale with frames.canvas_scale.
NOISE_OCTAVES = ((3, 1.0), (6, 0.5), (12, 0.25))  # cells vertically, amplitude
LUM_SIGMA = 40.0
DELAY_SIGMA = 25.0


def morph(keys: list[np.ndarray], times: list[float] | None = None) -> Frame:
    """Optical-flow morph along the chain (key i at chain time times[i]);
    global time smoothstep-eased."""
    chain = FlowChain(keys, times)
    return lambda t: chain.at(float(smoothstep(t)))


def _norm(x: np.ndarray) -> np.ndarray:
    return (x - x.min()) / (x.max() - x.min() + 1e-6)


def noise_shape(cells: int, w: int, h: int) -> tuple[int, int]:
    """Rows and columns of one noise octave: `cells` rows, int(cells*w/h) + 1 columns."""
    return cells, max(2, int(cells * w / h) + 1)


def delay_field(end: np.ndarray, seed: int, lum_weight: float) -> np.ndarray:
    """Per-pixel delay in [0, 1]: smooth multi-octave noise mixed with the
    inverted blurred luminance of the end image, so bright areas change first."""
    h, w = end.shape[:2]
    scale = canvas_scale(w, h)
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    for cells, amp in NOISE_OCTAVES:
        g = rng.random(noise_shape(cells, w, h)).astype(np.float32)
        acc += amp * cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC)
    lum = cv2.cvtColor(np.clip(end, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    lum = cv2.GaussianBlur(lum, (0, 0), LUM_SIGMA * scale)
    d = (1 - lum_weight) * _norm(acc) + lum_weight * (1 - _norm(lum))
    return _norm(cv2.GaussianBlur(d, (0, 0), DELAY_SIGMA * scale)).astype(np.float32)


def local_time(T: float, delay: np.ndarray, spread: float) -> np.ndarray:
    """Per-pixel eased time at clip time T: smoothstep((T - spread*d) / (1 - spread))."""
    return smoothstep((T - spread * delay) / (1 - spread))


def region(keys: list[np.ndarray], steps: int, spread: float, lum_weight: float, seed: int,
           times: list[float] | None = None) -> Frame:
    """Parts of the image change at different times: a linear-time flow
    sequence of `steps` frames (uint8), each pixel reading it at its own time."""
    chain = FlowChain(keys, times)
    h, w = keys[0].shape[:2]
    seq = np.empty((steps, h * w, 3), np.uint8)
    for j in range(steps):
        seq[j] = np.clip(chain.at(j / (steps - 1)), 0, 255).round().astype(np.uint8).reshape(-1, 3)
    flat = seq.reshape(-1, 3)
    delay = delay_field(keys[-1], seed, lum_weight)
    pix = np.arange(h * w, dtype=np.int64)
    m = steps - 1

    def frame(T: float) -> np.ndarray:
        lt = local_time(T, delay, spread).ravel() * m  # float32 in [0, m]
        fl = np.floor(lt)
        i0 = fl.astype(np.int64)
        i1 = np.minimum(i0 + 1, m)
        wt = (lt - fl)[:, None]
        a = flat[i0 * (h * w) + pix].astype(np.float32)
        b = flat[i1 * (h * w) + pix].astype(np.float32)
        return ((1 - wt) * a + wt * b).reshape(h, w, 3)

    return frame


def crossfade(a: np.ndarray, b: np.ndarray) -> Frame:
    """Eased blend of a into b."""
    def frame(t: float) -> np.ndarray:
        e = float(smoothstep(t))
        return cv2.addWeighted(a, 1 - e, b, e, 0, dtype=cv2.CV_32F)
    return frame


def blur_crossfade(a: np.ndarray, b: np.ndarray, sigma: float) -> Frame:
    """Eased blend under a Gaussian blur of both images whose sigma (canvas
    px) rises to `sigma` at mid-transition and falls back to 0."""
    def frame(t: float) -> np.ndarray:
        e = float(smoothstep(t))
        s = sigma * math.sin(math.pi * min(max(t, 0.0), 1.0))
        if s > 0.05:
            ba = cv2.GaussianBlur(a, (0, 0), s)
            bb = cv2.GaussianBlur(b, (0, 0), s)
        else:
            ba, bb = a, b
        return cv2.addWeighted(ba, 1 - e, bb, e, 0, dtype=cv2.CV_32F)
    return frame
