"""Easing, rounded-rect outlines and anti-aliased masks shared by the renderers."""

from __future__ import annotations

import math

import cv2
import numpy as np

# Sub-pixel bits of the OpenCV drawing calls (coordinates times 16).
SHIFT = 4
SUB = 1 << SHIFT


def ease(x: float) -> float:
    """Cubic ease-in-out of x clamped to 0..1."""
    x = min(max(x, 0.0), 1.0)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def tween(u: float, t0: float, t1: float) -> float:
    """Eased progress of time u from t0 to t1 (a step at t0 when t1 <= t0)."""
    return ease((u - t0) / (t1 - t0)) if t1 > t0 else float(u >= t0)


def fade_in_out(u: float, t0: float, t1: float, f: float = 0.35) -> float:
    """Opacity of something shown from t0 to t1 with linear fades of f seconds."""
    if u < t0 or u > t1:
        return 0.0
    if f <= 0:
        return 1.0
    return min(1.0, (u - t0) / f, (t1 - u) / f)


def piecewise(points: list[tuple[float, float]], x: float) -> float:
    """Linear interpolation through (x, y) points sorted by x, held at the ends."""
    xs, ys = zip(*points)
    return float(np.interp(x, xs, ys))


def slopes(ts: list[float], vs: list[float]) -> list[float]:
    """Tangents of a smooth path through (t, v) keys: zero at the first and last key (ease in and out), the
    Catmull-Rom slope at an inner key, zero where the path turns back, limited so no segment overshoots
    (Fritsch-Carlson)."""
    n = len(ts)
    d = [(vs[i + 1] - vs[i]) / (ts[i + 1] - ts[i]) if ts[i + 1] > ts[i] else 0.0 for i in range(n - 1)]
    m = [0.0] * n
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0 or ts[i + 1] <= ts[i - 1]:
            continue
        s = (vs[i + 1] - vs[i - 1]) / (ts[i + 1] - ts[i - 1])
        m[i] = math.copysign(min(abs(s), 3 * abs(d[i - 1]), 3 * abs(d[i])), s)
    return m


def spline(ts: list[float], vs: list[float], t: float, m: list[float] | None = None) -> float:
    """The value at time t on the path through (t, v) keys (cubic Hermite with `slopes`), held at the ends.
    Between two keys alone it eases in and out; at an inner key it keeps moving."""
    if t <= ts[0]:
        return vs[0]
    if t >= ts[-1]:
        return vs[-1]
    m = slopes(ts, vs) if m is None else m
    i = max(j for j in range(len(ts) - 1) if ts[j] <= t)
    h = ts[i + 1] - ts[i]
    if h <= 0:
        return vs[i + 1]
    x = (t - ts[i]) / h
    h00, h10, h01, h11 = 2 * x ** 3 - 3 * x ** 2 + 1, x ** 3 - 2 * x ** 2 + x, -2 * x ** 3 + 3 * x ** 2, x ** 3 - x ** 2
    return h00 * vs[i] + h10 * h * m[i] + h01 * vs[i + 1] + h11 * h * m[i + 1]


def keyed_value(keys: list[tuple[float, float]], t: float) -> float:
    """A value keyed at times, on the smooth path of `spline`."""
    ts, vs = zip(*keys)
    return spline(list(ts), list(vs), t)


def rrect(x: float, y: float, w: float, h: float, r: float, n: int = 6) -> np.ndarray:
    """Points of a rounded rectangle outline, clockwise from the top-right corner."""
    r = max(0.0, min(r, w / 2, h / 2))
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90),
                       (x + r, y + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return np.array(pts, np.float64)


def ellipse(x: float, y: float, w: float, h: float, n: int = 72, sweep: float = 1.0) -> np.ndarray:
    """Points of the ellipse inscribed in a rect, from its left end, `sweep` of a full turn."""
    a = np.linspace(math.pi, math.pi + 2 * math.pi * sweep, max(2, int(n * sweep) + 1))
    return np.stack([x + w / 2 + w / 2 * np.cos(a), y + h / 2 + h / 2 * np.sin(a)], 1)


def fixed(pts: np.ndarray) -> list[np.ndarray]:
    """Points as the int32 sub-pixel polygon list OpenCV draws with `shift=SHIFT`."""
    return [np.round(np.asarray(pts) * SUB).astype(np.int32)]


def fill_mask(poly: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Anti-aliased float mask (0..1) of a filled polygon."""
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, fixed(poly), 255, cv2.LINE_AA, shift=SHIFT)
    return m.astype(np.float32) / 255


def line_mask(poly: np.ndarray, shape: tuple[int, int], width: int, closed: bool = True) -> np.ndarray:
    """Anti-aliased float mask (0..1) of a polyline."""
    m = np.zeros(shape, np.float32)
    cv2.polylines(m, fixed(poly), closed, 1.0, max(1, int(round(width))), cv2.LINE_AA, shift=SHIFT)
    return m


def blend(out: np.ndarray, color: tuple[float, float, float], mask: np.ndarray) -> np.ndarray:
    """out with `color` laid over it through a 2-D mask (0..1)."""
    m = mask[..., None]
    return out * (1 - m) + np.array(color, np.float32) * m
