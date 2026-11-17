"""The camera of a shot: keys resolved to page centre, zoom, yaw and pitch, on a smooth path through them."""

from __future__ import annotations

import math

from .geometry import slopes, spline
from .model import CameraKey, CameraSpec, Rect

# A `rect` key, and the default first key, fit the rect in this share of the frame.
FIT = 0.92


class Camera:
    def __init__(self, keys: list[CameraKey]):
        if not keys:
            raise ValueError("a camera needs at least one key")
        self.keys = sorted(keys, key=lambda k: k.t)
        self.times = [k.t for k in self.keys]
        fields = ([k.center[0] for k in self.keys], [k.center[1] for k in self.keys],
                  [math.log(k.zoom) for k in self.keys], [k.yaw for k in self.keys], [k.pitch for k in self.keys])
        self.paths = [(vs, slopes(self.times, vs)) for vs in fields]

    @classmethod
    def resolve(cls, specs: list[CameraSpec], page: Rect, frame: tuple[int, int], fill: bool = False) -> Camera:
        """Keys from the written specs. A missing field keeps the previous key's value; the first key's
        defaults frame the whole page rect `page`. A rect (and the default) fits in FIT of the frame, or, with
        `fill` (a picture shot), covers the frame."""
        w, h = frame
        px, py, pw, ph = page
        fit = (max if fill else min)(w / pw, h / ph)
        prev = CameraKey(0.0, (px + pw / 2, py + ph / 2), fit if fill else fit * FIT)
        keys = []
        for s in specs or [CameraSpec(t=0.0)]:
            center, zoom = prev.center, prev.zoom
            if s.rect is not None:
                rx, ry, rw, rh = s.rect
                center = (rx + rw / 2, ry + rh / 2)
                zoom = max(w / rw, h / rh) if fill else FIT * min(w / rw, h / rh)
            if s.center is not None:
                center = s.center
            if s.width is not None:
                zoom = w / s.width
            if s.zoom is not None:
                zoom = s.zoom
            prev = CameraKey(s.t, center, zoom, prev.yaw if s.yaw is None else s.yaw,
                             prev.pitch if s.pitch is None else s.pitch)
            keys.append(prev)
        return cls(keys)

    def at(self, t: float) -> CameraKey:
        """The camera at time t: every field on a smooth path through the keys (`geometry.spline`), the zoom
        in log scale (a zoom from 1x to 4x passes 2x half way). It eases out of the first key and into the
        last, and moves through the keys between without stopping."""
        k = self.keys
        if len(k) == 1 or t <= k[0].t:
            return k[0]
        if t >= k[-1].t:
            return k[-1]
        ts = self.times
        x, y, z, yaw, pitch = (spline(ts, vs, t, m) for vs, m in self.paths)
        return CameraKey(t, (x, y), math.exp(z), yaw, pitch)

    def max_zoom(self) -> float:
        return max(k.zoom for k in self.keys)
