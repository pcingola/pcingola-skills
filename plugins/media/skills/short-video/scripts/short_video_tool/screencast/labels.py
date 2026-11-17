"""Labels: dark rounded pills with a coloured dot and a line of text, kept inside the title-safe area
(`safe_margin` px from every frame edge); captions centred vertically in the caption band."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .geometry import fade_in_out
from .model import Anchor, CameraKey, Label
from .projection import Projection
from .style import CaptionAlign, Style

# Label fade in and out, seconds.
LABEL_FADE = 0.35


@lru_cache(maxsize=16)
def font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    """The font file at `path` (TrueType or OpenType), or Pillow's built-in font when None."""
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


class LabelPainter:
    def __init__(self, style: Style, frame: tuple[int, int], project: Projection):
        self.style = style
        self.w, self.h = frame
        self.project = project
        # Style sizes are px of a 1080 px frame side.
        self.k = min(self.w, self.h) / 1080
        self.margin = style.safe_margin * self.k

    def label(self, out: np.ndarray, u: float, cam: CameraKey | None, lb: Label) -> np.ndarray:
        """Draw label `lb` at shot time u (camera `cam` places a page-anchored one)."""
        alpha = fade_in_out(u, lb.start, lb.end, LABEL_FADE)
        if alpha <= 0:
            return out
        size = self.size(lb.size or (self.style.caption.size if lb.caption else self.style.label.size))
        pill = self.render(lb.text, lb.color, size)
        ph, pw = pill.shape[:2]
        if lb.caption:
            m = self.margin
            x = m if self.style.caption.align is CaptionAlign.LEFT else (self.w - pw) / 2
            y = self.h - self.style.caption.height * self.k / 2 - ph / 2
            return self.paste(out, pill, x, y, alpha, clamp=False)
        if lb.page and cam is not None:
            x, y = self.project([lb.at], cam)[0]
        else:
            x, y = lb.at
        if lb.anchor is Anchor.RIGHT:
            x -= pw
        elif lb.anchor is Anchor.CENTER:
            x -= pw / 2
        return self.paste(out, pill, x, y, alpha)

    def size(self, size: float) -> int:
        """A style or label font size as px of this frame."""
        return max(6, int(round(size * self.k)))

    def render(self, text: str, color: tuple, size: int) -> np.ndarray:
        """The pill as a BGRA float image."""
        look = self.style.label
        f = font(look.font, size)
        tw = f.getbbox(text)[2]
        pad, dot = int(size * 0.55), int(size * 0.32)
        w, h = tw + pad * 3 + dot, int(size * 1.7)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        fill = tuple(int(v) for v in look.fill[::-1]) + (int(255 * look.fill_opacity),)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=fill,
                            outline=(255, 255, 255, int(255 * look.outline_opacity)), width=2)
        d.ellipse((pad, h // 2 - dot // 2, pad + dot, h // 2 + dot // 2), fill=tuple(int(v) for v in color[::-1]) + (255,))
        d.text((pad * 2 + dot, h // 2), text, font=f, fill=tuple(int(v) for v in look.text[::-1]) + (255,), anchor="lm")
        a = np.asarray(im, np.float32)
        return a[..., [2, 1, 0, 3]]

    def paste(self, out: np.ndarray, pill: np.ndarray, x: float, y: float, alpha: float,
              clamp: bool = True) -> np.ndarray:
        ph, pw = pill.shape[:2]
        if clamp:
            m = self.margin
            x = min(max(x, m), max(m, self.w - m - pw))
            y = min(max(y, m), max(m, self.h - m - ph))
        x, y = int(round(x)), int(round(y))
        y0, x0, y1, x1 = max(y, 0), max(x, 0), min(y + ph, self.h), min(x + pw, self.w)
        if y1 <= y0 or x1 <= x0:
            return out
        sub = pill[y0 - y:y1 - y, x0 - x:x1 - x]
        a = sub[..., 3:] / 255 * alpha
        out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1 - a) + sub[..., :3] * a
        return out
