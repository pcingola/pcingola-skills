"""An image with halved copies, so a warp samples the level closest to the zoom (no aliasing when zoomed
out, full detail of a 2x source when zoomed in)."""

from __future__ import annotations

import cv2
import numpy as np

# A level is used while its px per page px is at most zoom / MIN_RATIO: a warp shrinks it no more than this.
MIN_RATIO = 0.6


class Pyramid:
    def __init__(self, img: np.ndarray, scale: float):
        """`img` at `scale` image px per page px."""
        self.levels = [(scale, img)]
        while self.levels[-1][0] > MIN_RATIO and min(self.levels[-1][1].shape[:2]) > 16:
            k, im = self.levels[-1]
            self.levels.append((k / 2, cv2.resize(im, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)))

    def pick(self, zoom: float) -> tuple[float, np.ndarray]:
        """(px per page px, image) of the largest level the zoom shrinks by at most MIN_RATIO."""
        for k, im in self.levels:
            if k <= zoom / MIN_RATIO:
                return k, im
        return self.levels[-1]
