"""The base of the shot renderers: a shot's length, its crossfade, its labels and its wipe divider."""

from __future__ import annotations

import numpy as np

from .camera import Camera
from .context import RenderContext
from .model import CameraKey, LabelEdge, Shot
from .wipe_source import WipeSource


class ShotRenderer:
    # The caption band darkens the bottom of this kind of shot when the shot list has captions.
    banded = False

    def __init__(self, shot: Shot, ctx: RenderContext):
        self.shot, self.ctx = shot, ctx
        self.camera: Camera | None = None
        self.wipe: WipeSource | None = None

    @property
    def length(self) -> float:
        return self.shot.length

    def prepare(self, times: list[float]) -> None:
        """Load what frames at these shot times need (video frames); called once before rendering."""

    def release(self) -> None:
        """Drop loaded frames once the shot is past."""

    def frame(self, u: float, t: float) -> np.ndarray:
        """The float32 BGR frame at shot time u, film time t."""
        raise NotImplementedError

    def overlays(self, out: np.ndarray, u: float, cam: CameraKey | None) -> np.ndarray:
        if self.ctx.band and self.banded:
            out = self.ctx.stage.band(out)
        for lb in self.shot.labels:
            out = self.ctx.labels.label(out, u, cam, lb)
        return out

    def divider(self, out: np.ndarray, u: float, top: np.ndarray, bottom: np.ndarray) -> np.ndarray:
        """The wipe's divider between frame points top and bottom, with its two labels beside it."""
        w = self.wipe
        a = w.alpha(u)
        if a <= 0 or not (-20 < top[0] < self.ctx.frame[0] + 20 or -20 < bottom[0] < self.ctx.frame[0] + 20):
            return out
        out = self.ctx.stage.divider(out, top, bottom, w.spec.color, a)
        if w.spec.labels:
            painter = self.ctx.labels
            size = painter.size(self.ctx.style.label.size * 0.87)
            c0, c1 = w.spec.label_colors or (w.spec.color, w.spec.color)
            m = painter.margin
            if w.spec.label_edge is LabelEdge.TOP:
                x, y = top[0], max(top[1] + 30, m)
            else:
                x = bottom[0]
                y = min(bottom[1], self.ctx.frame[1]) - m - size * 1.7
            gap = 24 * self.ctx.stage.k
            left = painter.render(w.spec.labels[0], c0, size)
            right = painter.render(w.spec.labels[1], c1, size)
            out = painter.paste(out, left, x - gap - left.shape[1], y, a, clamp=False)
            out = painter.paste(out, right, x + gap, y, a, clamp=False)
        return out
