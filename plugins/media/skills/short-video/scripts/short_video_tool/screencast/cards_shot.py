"""A cards shot: pictures as rounded cards with soft shadows and an edge light over the backdrop, each with
its own eased keys (centre, width, angle, opacity, in screen px), drawn in list order."""

from __future__ import annotations

import math
from functools import lru_cache

import cv2
import numpy as np

from . import pictures
from .context import RenderContext
from .geometry import rrect, spline
from .model import CardPose, Shot
from .renderer import ShotRenderer

CARD_RADIUS = 18
EDGE_COLOR = (255.0, 240.0, 230.0)


@lru_cache(maxsize=64)
def round_mask(w: int, h: int, r: int) -> np.ndarray:
    """Anti-aliased rounded-rect mask, drawn at 4x and reduced."""
    m = np.zeros((h * 4, w * 4), np.uint8)
    cv2.fillPoly(m, [np.round(rrect(0, 0, w * 4 - 1, h * 4 - 1, r * 4, 8)).astype(np.int32)], 255, cv2.LINE_AA)
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255


def pose(keys: list[CardPose], u: float) -> CardPose:
    """The card's pose at shot time u, every field on the smooth path of `geometry.spline`."""
    if len(keys) == 1 or u <= keys[0].t:
        return keys[0]
    ts = [p.t for p in keys]

    def f(get) -> float:
        return spline(ts, [get(p) for p in keys], u)
    return CardPose(u, (f(lambda p: p.center[0]), f(lambda p: p.center[1])), f(lambda p: p.width),
                    f(lambda p: p.angle), f(lambda p: p.alpha))


class CardsShot(ShotRenderer):
    def __init__(self, shot: Shot, ctx: RenderContext):
        super().__init__(shot, ctx)
        self.images = [pictures.load(c.image, c.upscale) for c in shot.cards]

    def frame(self, u: float, t: float) -> np.ndarray:
        out = self.ctx.stage.backdrop.at(t)
        for card, img in zip(self.shot.cards, self.images):
            out = self.card(out, img, pose(card.keys, u))
        return self.overlays(out, u, None)

    def card(self, out: np.ndarray, img: np.ndarray, p: CardPose) -> np.ndarray:
        fw, fh = self.ctx.frame
        if p.alpha <= 0.01 or p.width < 4:
            return out
        sw = max(8, int(round(p.width)))
        sh = max(8, int(round(p.width * img.shape[0] / img.shape[1])))
        small = cv2.resize(img, (sw, sh), interpolation=cv2.INTER_AREA if img.shape[1] > sw else cv2.INTER_CUBIC)
        mask = round_mask(sw, sh, int(CARD_RADIUS * self.ctx.stage.k))
        a = math.radians(p.angle)
        ca, sa = math.cos(a), math.sin(a)
        cx, cy = p.center
        m = np.float32([[ca, -sa, cx - ca * sw / 2 + sa * sh / 2], [sa, ca, cy - sa * sw / 2 - ca * sh / 2]])
        col = cv2.warpAffine(small, m, (fw, fh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        mk = cv2.warpAffine(mask, m, (fw, fh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        q = cv2.resize(mk, (fw // 4, fh // 4), interpolation=cv2.INTER_AREA)
        q = cv2.GaussianBlur(np.roll(q, max(2, int(p.width / 120)), 0), (0, 0), max(3.0, p.width / 60))
        s = cv2.resize(q, (fw, fh))[..., None]
        out = out * (1 - 0.7 * p.alpha * s)
        if self.shot.glow is not None:
            out = out + s * np.array(self.shot.glow, np.float32) * 0.35 * p.alpha
        m3 = (mk * p.alpha)[..., None]
        out = out * (1 - m3) + col.astype(np.float32) * m3
        edge = cv2.morphologyEx(mk, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
        return out + (edge * p.alpha * 0.35)[..., None] * np.array(EDGE_COLOR, np.float32)


