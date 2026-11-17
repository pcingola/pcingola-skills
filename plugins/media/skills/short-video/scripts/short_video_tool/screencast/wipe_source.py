"""A before/after wipe: the `before` picture left of a keyed divider, the `after` picture (aligned to it)
right of it."""

from __future__ import annotations

import numpy as np

from . import pictures
from .geometry import keyed_value, tween
from .model import Wipe


class WipeSource:
    def __init__(self, spec: Wipe, upscale: int | None, scale: float, warn):
        self.spec = spec
        self.scale = scale
        self.before = pictures.load(spec.before, upscale)
        after = pictures.load(spec.after, upscale)
        if not spec.align:
            self.after = pictures.resized(after, self.before.shape)
            return
        self.after, ok = pictures.align(self.before, after)
        if not ok:
            warn(f"wipe: {spec.after.name} could not be aligned to {spec.before.name} (ECC did not converge); "
                 "the wipe shows them unaligned")

    @property
    def shape(self) -> tuple[int, ...]:
        return self.before.shape

    def x(self, u: float) -> float:
        """The divider's page x at shot time u."""
        return keyed_value(self.spec.divider, u)

    def frame(self, u: float) -> np.ndarray:
        xi = int(round(min(max(self.x(u) * self.scale, 0), self.before.shape[1])))
        img = self.after.copy()
        img[:, :xi] = self.before[:, :xi]
        return img

    def alpha(self, u: float) -> float:
        """Opacity of the divider and its labels (they fade out over `fade`)."""
        return 1.0 - (tween(u, *self.spec.fade) if self.spec.fade else 0.0)
