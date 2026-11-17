"""The background behind panels and cards: a diagonal two-colour gradient, soft glows drifting slowly,
optional particles rising and twinkling, and a vignette."""

from __future__ import annotations

import math

import cv2
import numpy as np

from .style import Background

# Seed of the particle positions, so every render of a shot list is the same.
PARTICLE_SEED = 7


class Backdrop:
    def __init__(self, look: Background, frame: tuple[int, int], vignette: float):
        self.look = look
        self.w, self.h = frame
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        u = np.clip(xx / self.w * 0.45 + yy / self.h * 0.55, 0, 1)[..., None]
        a, b = (np.array(c, np.float32) for c in look.colors)
        self.gradient = a * (1 - u) + b * u
        self.particles = np.random.default_rng(PARTICLE_SEED).random((look.particles, 4))
        self.k = min(self.w, self.h) / 1080
        # The vignette darkens the backdrop only: over a panel or a picture it would grey a white UI.
        d = ((xx - self.w / 2) / (self.w / 2)) ** 2 + ((yy - self.h / 2) / (self.h / 2)) ** 2
        self.vignette = (1 - vignette * np.clip(d - 0.25, 0, 1))[..., None]

    def at(self, t: float) -> np.ndarray:
        """The background at film time t as a float32 BGR frame."""
        img = self.gradient.copy()
        if self.look.glows:
            h4, w4 = self.h // 4, self.w // 4
            yy, xx = np.mgrid[0:h4, 0:w4].astype(np.float32)
            glow = np.zeros((h4, w4, 3), np.float32)
            for i, g in enumerate(self.look.glows):
                ph = 1.7 * i
                cx = (g.x + 0.05 * math.sin(t * 0.35 + ph)) * w4
                cy = (g.y + 0.05 * math.cos(t * 0.3 + ph)) * h4
                d = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (g.radius * w4) ** 2)))
                glow += d[..., None] * np.array(g.color, np.float32) * g.amount
            img += cv2.resize(glow, (self.w, self.h), interpolation=cv2.INTER_LINEAR)
        for px, py, sz, ph in self.particles:
            x = int(px * self.w)
            y = int(((py - t * (0.01 + 0.02 * sz)) % 1.0) * self.h)
            a = 0.35 + 0.35 * math.sin(t * 2 + ph * 6.28)
            cv2.circle(img, (x, y), max(1, int((1 + sz * 2) * self.k)),
                       tuple(float(v) * a for v in self.look.particle_color), -1, cv2.LINE_AA)
        return img * self.vignette
