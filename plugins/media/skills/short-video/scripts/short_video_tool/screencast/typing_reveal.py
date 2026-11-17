"""Typing rebuilt from a screenshot of the finished text: the text rect is split into lines (rows with ink)
and each line into glyphs (the ends of ink column runs); at a fraction of the typing time that fraction of
the glyphs shows, the rest painted with the field's background, a caret after the last one."""

from __future__ import annotations

import numpy as np

from .model import Typing

# Blank rows inside a line that still count as one line (descenders, accents), in source px per page px.
LINE_GAP = 2
CARET_HZ = 2.0


class TypingReveal:
    def __init__(self, img: np.ndarray, spec: Typing, scale: float):
        self.spec = spec
        x, y, w, h = (int(round(v * scale)) for v in spec.rect)
        self.x0, self.y0 = x, y
        sub = img[y:y + h, x:x + w].astype(np.int16)
        if sub.size == 0:
            raise ValueError(f"typing rect {spec.rect} lies outside the image")
        border = np.concatenate([sub[0], sub[-1], sub[:, 0], sub[:, -1]])
        self.bg = np.median(border, 0).astype(np.uint8)
        ink = np.abs(sub - self.bg.astype(np.int16)).max(2) > spec.threshold
        self.caret_color = spec.caret_color or self.ink_color(sub, ink)
        self.lines: list[tuple[int, int, int, list[int]]] = []   # (row0, row1, col0, glyph ends) in rect px
        rows = ink.any(1)
        gap = int(LINE_GAP * scale)
        r = 0
        while r < len(rows):
            if not rows[r]:
                r += 1
                continue
            r0 = r
            blank = 0
            while r < len(rows) and blank <= gap:
                blank = 0 if rows[r] else blank + 1
                r += 1
            r1 = r - blank
            cols = ink[r0:r1].any(0)
            ends = [i + 1 for i in range(len(cols)) if cols[i] and (i + 1 == len(cols) or not cols[i + 1])]
            start = int(np.argmax(cols))
            self.lines.append((r0, r1, start, ends))
        self.width = w
        self.glyphs = sum(len(e) for *_, e in self.lines)
        self.scale = scale

    @staticmethod
    def ink_color(sub: np.ndarray, ink: np.ndarray) -> tuple[float, float, float]:
        if not ink.any():
            return (128.0, 128.0, 128.0)
        return tuple(float(v) for v in np.median(sub[ink], 0))

    def frame(self, img: np.ndarray, u: float) -> np.ndarray:
        """img with the text typed up to shot time u (glyphs at a constant rate from start to end)."""
        sp = self.spec
        a = min(max((u - sp.start) / (sp.end - sp.start), 0.0), 1.0) if sp.end > sp.start else float(u >= sp.start)
        n = int(round(a * self.glyphs))
        img = img.copy()
        caret = None
        for i, (r0, r1, start, ends) in enumerate(self.lines):
            y0, y1 = self.y0 + r0, self.y0 + r1
            if n >= len(ends):
                n -= len(ends)
                caret = (self.x0 + ends[-1], y0, y1)
                continue
            # the first line not typed in full: blank it after the n-th glyph, and every line after it
            x = self.x0 + (ends[n - 1] if n > 0 else start)
            img[y0:y1, x:self.x0 + self.width] = self.bg
            for rr0, rr1, _, _ in self.lines[i + 1:]:
                img[self.y0 + rr0:self.y0 + rr1, self.x0:self.x0 + self.width] = self.bg
            if n > 0 or caret is None:
                caret = (x, y0, y1)
            break
        blink = a < 1 or (u * CARET_HZ) % 1 < 0.5
        if caret and sp.caret and blink and u < sp.end + 1.0 and u >= sp.start:
            x, y0, y1 = caret
            cw = max(1, int(round(self.scale)))
            img[y0:y1, x + cw:x + 2 * cw] = self.caret_color
        return img
