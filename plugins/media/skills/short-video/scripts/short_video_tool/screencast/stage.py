"""The panel stage: a page drawn as a rounded panel turned in 3D over the backdrop, with a soft shadow, an
ambient glow and an edge light; glowing outlines on controls, click ripples, video inserted into page
rects; and the caption band."""

from __future__ import annotations

import math

import cv2
import numpy as np

from .backdrop import Backdrop
from .geometry import ease, ellipse, fade_in_out, fill_mask, fixed, line_mask, rrect, SHIFT
from .model import CameraKey, Click, Highlight, Rect, Shape
from .projection import Projection
from .pyramid import Pyramid
from .style import Style

# Highlight: page px between the control and its outline, outline corner radius, pulse frequency (Hz). Click ripple: duration (s), start and end radius (page px).
HL_PAD, HL_RADIUS, HL_PULSE = 8, 12, 1.2
RIPPLE_SECONDS, RIPPLE_R0, RIPPLE_R1 = 0.7, 10, 80
EDGE_COLOR = (255.0, 235.0, 225.0)


class Stage:
    def __init__(self, style: Style, frame: tuple[int, int]):
        self.style = style
        self.w, self.h = frame
        # Screen sizes of the style and of the drawing (blur radii, line widths) are px of a 1080 px frame side.
        self.k = min(self.w, self.h) / 1080
        self.backdrop = Backdrop(style.background, frame, style.vignette)
        self.project = Projection(frame, style.focal)
        c = style.caption
        top = self.h - c.height * self.k
        ramp = np.clip((np.arange(self.h, dtype=np.float32) - top) / max(c.ramp * self.k, 1.0), 0, 1)
        ramp *= c.band_opacity
        self.band_ramp = ramp[:, None, None]

    # ---- panel ----
    def panel(self, t: float, cam: CameraKey, pyr: Pyramid, rect: Rect, radius: float,
              inserts: list[tuple[np.ndarray, Rect]] = ()) -> np.ndarray:
        """The backdrop at film time t with the page (pyramid `pyr`, visible page rect `rect`) as a panel."""
        look = self.style.panel
        out = self.backdrop.at(t)
        x, y, w, h = rect
        outline = self.project(rrect(x, y, w, h, radius), cam)
        small = fill_mask(outline / 4, (self.h // 4, self.w // 4))
        drop = int(10 * min(cam.zoom, 2) * self.k)
        shadow = cv2.resize(cv2.GaussianBlur(np.roll(small, drop, 0), (0, 0), 14 * self.k), (self.w, self.h))
        out *= 1 - look.shadow * shadow[..., None]
        amb = cv2.resize(cv2.GaussianBlur(small, (0, 0), 22 * self.k), (self.w, self.h))[..., None]
        out += amb * np.array(look.ambient_color, np.float32) * look.ambient
        mask = fill_mask(outline, (self.h, self.w))[..., None]
        k, im = pyr.pick(cam.zoom)
        content = self.warp(im, k, (0, 0, im.shape[1] / k, im.shape[0] / k), cam)
        for img, r in inserts:
            m = fill_mask(self.project.quad(r, cam), (self.h, self.w))[..., None]
            content = content * (1 - m) + self.warp(img, img.shape[1] / r[2], r, cam) * m
        out = out * (1 - mask) + content * mask
        edge = line_mask(outline, (self.h, self.w), 2)
        return out + edge[..., None] * np.array(EDGE_COLOR, np.float32) * look.edge_light

    def warp(self, img: np.ndarray, k: float, rect: Rect, cam: CameraKey) -> np.ndarray:
        """img (k px per page px) warped so that it covers page rect `rect` as projected."""
        ih, iw = img.shape[:2]
        src = np.float32([[0, 0], [iw, 0], [iw, ih], [0, ih]])
        m = cv2.getPerspectiveTransform(src, np.float32(self.project.quad(rect, cam)))
        return cv2.warpPerspective(img, m, (self.w, self.h), flags=cv2.INTER_CUBIC,
                                   borderMode=cv2.BORDER_CONSTANT).astype(np.float32)

    # ---- marks on the page ----
    def highlight(self, out: np.ndarray, u: float, cam: CameraKey, hl: Highlight) -> np.ndarray:
        a = fade_in_out(u, hl.start, hl.end, hl.fade)
        if a <= 0:
            return out
        if hl.pulse:
            a *= 0.85 + 0.15 * math.sin((u - hl.start) * 2 * math.pi * HL_PULSE)
        g = ease((u - hl.start) / 0.4) if hl.grow else 1.0
        bx, by, bw, bh = hl.rect
        if hl.shape is Shape.ELLIPSE:
            pts = ellipse(bx - HL_PAD, by - HL_PAD, bw + 2 * HL_PAD, bh + 2 * HL_PAD, sweep=g)
            closed = g >= 1
        else:
            pts = rrect(bx - HL_PAD, by - HL_PAD, (bw + 2 * HL_PAD) * g, (bh + 2 * HL_PAD) * g, HL_RADIUS)
            closed = True
        poly = self.project(pts, cam)
        wide = line_mask(poly, (self.h, self.w), 16 * self.k, closed)
        glow = np.clip(cv2.GaussianBlur(wide, (0, 0), 10 * self.k) * 1.6, 0, 1) * 0.55 * a
        core = line_mask(poly, (self.h, self.w), 4 * self.k, closed)
        m = np.maximum(glow, core * a)[..., None]
        out = out * (1 - m) + np.array(hl.color, np.float32) * m
        return out + (core * a * 40)[..., None]

    def click(self, out: np.ndarray, u: float, cam: CameraKey, c: Click) -> np.ndarray:
        p = (u - c.t) / RIPPLE_SECONDS
        if not 0 <= p <= 1:
            return out
        r = RIPPLE_R0 + (RIPPLE_R1 - RIPPLE_R0) * ease(p)
        a = np.linspace(0, 2 * math.pi, 48)
        circ = np.stack([c.at[0] + r * np.cos(a), c.at[1] + r * np.sin(a)], 1)
        ring = np.zeros((self.h, self.w, 3), np.float32)
        cv2.polylines(ring, fixed(self.project(circ, cam)), True, tuple(v * (1 - p) for v in c.color),
                      max(1, int(4 * self.k)), cv2.LINE_AA, shift=SHIFT)
        return out + cv2.GaussianBlur(ring, (0, 0), 3 * self.k) * 1.5 + ring

    def divider(self, out: np.ndarray, top: np.ndarray, bottom: np.ndarray, color: tuple, alpha: float) -> np.ndarray:
        """A glowing wipe divider from frame point `top` to `bottom`, with a round handle half way."""
        line = line_mask(np.array([top, bottom]), (self.h, self.w), 5 * self.k, closed=False)
        glow = np.clip(cv2.GaussianBlur(line, (0, 0), 9 * self.k) * 2.2, 0, 1)
        m = (np.maximum(line, glow * 0.7) * alpha)[..., None]
        base = out
        out = out * (1 - m) + np.array(color, np.float32) * m + line[..., None] * 90 * alpha
        mid = (np.asarray(top) + np.asarray(bottom)) / 2
        cx, cy = int(mid[0]), int(np.clip(mid[1], 80 * self.k, self.h - 80 * self.k))
        rad = int(18 * self.k)
        cv2.circle(out, (cx, cy), rad, (245, 245, 245), -1, cv2.LINE_AA)
        cv2.circle(out, (cx, cy), rad, tuple(float(v) for v in color), max(1, int(3 * self.k)), cv2.LINE_AA)
        return out if alpha >= 1 else base * (1 - alpha) + out * alpha

    # ---- finish ----
    def band(self, out: np.ndarray) -> np.ndarray:
        """The caption band: the lower `caption.height` px darkened towards `caption.band_color`."""
        return out * (1 - self.band_ramp) + np.array(self.style.caption.band_color, np.float32) * self.band_ramp

    def finish(self, out: np.ndarray) -> np.ndarray:
        return np.clip(out, 0, 255).astype(np.uint8)
