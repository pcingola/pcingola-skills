"""Particle-text targets and glyph texture of a text block, precomputed from a font file (`particle-text`).

A particle-text page (`assets/kit/particles.js`, technique `particle_text`) forms text from particles that fly to
points inside the letters, then reveals a glyph plane drawn from a texture. Both come from here, so no seek of
the page waits on a web font load.

`<name>_tex.png`: R the fill mask, G a blurred glow, B the letter index as (k + 1) * 8 (`LETTER_STEP`), one RGB
pixel per texture pixel at `SUPERSAMPLE` times the on-screen size. `<name>_targets.js`: sets
`window.PT_TARGETS[name]` to {w, h, em, n, half, letters, lines, lc, ly, ink, camera, xy, li}: the text box in
world units, the font size in world units, the point count, the quantisation half range, letter and line counts,
the letter centres, the ink width and height, the camera (frame, fov, distance, and `end`, the page's final
distance as a share of `distance`), the points as base64 little-endian Int16 pairs in units of half / 32767 and the
letter index of each point as base64 bytes. World units are centred on the text box, y up; the text measures
`size` pixels (the font's em) on a frame `width` x `height` seen by a camera of vertical field of view `fov` at
distance `distance`.
"""
from __future__ import annotations

import base64
import io
import json
import math
import re
import dataclasses
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SUPERSAMPLE = 2
LETTER_STEP = 8
MAX_LETTERS = 255 // LETTER_STEP  # 31 letters keep the blue channel below 256; the kit's uLock holds 32
MAX_TEXTURE = 8192
MAX_WIDTH = 0.8  # `particle-text` warns above this share of the frame width (title-safe)
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2"}


@dataclass(frozen=True)
class ParticleText:
    """One text block (one or more centred lines) in one font, laid out for one frame and camera."""

    lines: tuple[str, ...]
    font: Path
    size: float = 150.0          # font size (em) in frame pixels at the camera distance
    tracking: float = 0.0        # extra space between letters, in em
    line_gap: float = 1.12       # line pitch, in em
    count: int = 24000           # particles (target points)
    edge_share: float = 0.34     # share of points on the letter outlines
    seed: int = 1
    width: int = 1920            # frame
    height: int = 1080
    fov: float = 35.0            # vertical field of view, degrees
    distance: float = 20.0       # camera distance at which the text measures `size` px
    end: float = 0.9             # the page's final camera distance as a share of `distance`

    def __post_init__(self) -> None:
        if not self.lines or not any(line.strip() for line in self.lines):
            raise ValueError("no text: give one or more lines")
        if self.font.suffix.lower() not in FONT_SUFFIXES:
            raise ValueError(f"{self.font}: not a font file ({', '.join(sorted(FONT_SUFFIXES))})")
        if not self.font.is_file():
            raise ValueError(f"{self.font}: font file not found")
        if min(self.size, self.count, self.distance, self.end) <= 0 or not 0 < self.fov < 180:
            raise ValueError("size, count, distance and end must be positive and fov in (0, 180)")
        if not 0 <= self.edge_share <= 1:
            raise ValueError("edge share must be in [0, 1]")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("frame width and height must be positive")
        letters = sum(1 for line in self.lines for ch in line if not ch.isspace())
        if letters > MAX_LETTERS:
            raise ValueError(f"{letters} letters: at most {MAX_LETTERS} per text block; split it into blocks")

    @property
    def px_per_unit(self) -> float:
        """Frame pixels per world unit at the camera distance."""
        return self.height / (2 * self.distance * math.tan(math.radians(self.fov / 2)))

    def load_font(self) -> ImageFont.FreeTypeFont:
        """The font at the texture size; a woff or woff2 file is converted to sfnt in memory."""
        px = round(self.size * SUPERSAMPLE)
        if self.font.suffix.lower() in (".woff", ".woff2"):
            f = TTFont(str(self.font))
            f.flavor = None
            buf = io.BytesIO()
            f.save(buf)
            buf.seek(0)
            return ImageFont.truetype(buf, px)
        return ImageFont.truetype(str(self.font), px)

    def _layout(self) -> tuple[np.ndarray, list, int, int]:
        """(fill mask cropped to the ink plus a pad, ink boxes per line and letter, crop left, crop top), in
        texture pixels."""
        S = SUPERSAMPLE
        font = self.load_font()
        em = self.size * S
        track = self.tracking * em
        asc, desc = font.getmetrics()
        pad = int(0.2 * em)
        widths = [font.getlength(line) + track * max(len(line) - 1, 0) for line in self.lines]
        lh = em * self.line_gap
        W = int(max(widths) + 2 * pad)
        H = int(2 * pad + lh * (len(self.lines) - 1) + asc + desc)
        if max(W, H) // S > MAX_TEXTURE:
            raise ValueError(f"text block {W // S}x{H // S} px: over {MAX_TEXTURE} px; lower --size or split lines")
        mask = Image.new("L", (W, H), 0)
        draw = ImageDraw.Draw(mask)
        boxes: list[list[tuple[float, float, float, float]]] = []  # per line, per letter: ink box
        for k, line in enumerate(self.lines):
            x0 = pad + (max(widths) - widths[k]) / 2
            y0 = pad + k * lh
            row = []
            for i, ch in enumerate(line):
                if ch.isspace():
                    continue
                at = (x0 + font.getlength(line[:i]) + track * i, y0)
                draw.text(at, ch, font=font, fill=255)
                row.append(draw.textbbox(at, ch, font=font))
            boxes.append(row)
        m = np.array(mask)
        rows, cols = np.nonzero(m.max(axis=1))[0], np.nonzero(m.max(axis=0))[0]
        if not len(rows):
            raise ValueError(f"{self.font.name} draws no ink for {list(self.lines)}")
        cy0, cy1 = max(rows[0] - pad, 0), min(rows[-1] + 1 + pad, H)
        cx0, cx1 = max(cols[0] - pad, 0), min(cols[-1] + 1 + pad, W)
        return m[cy0:cy1, cx0:cx1], [row for row in boxes if row], cx0, cy0

    @staticmethod
    def _ink(m: np.ndarray) -> tuple[int, int]:
        """Width and height of the ink in the mask, texture pixels."""
        rows, cols = np.nonzero(m.max(axis=1))[0], np.nonzero(m.max(axis=0))[0]
        return int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1)

    def measure(self) -> tuple[float, float]:
        """Width and height of the ink in frame pixels at the page's end distance (`end` x `distance`)."""
        w, h = self._ink(self._layout()[0])
        return w / SUPERSAMPLE / self.end, h / SUPERSAMPLE / self.end

    def fitted(self, fraction: float) -> "ParticleText":
        """This text block with the size at which its ink is `fraction` of the frame width at the end distance."""
        if not 0 < fraction <= 1:
            raise ValueError("fit must be in (0, 1]")
        size = self.size
        for _ in range(3):  # the ink width is close to linear in the size; hinting moves it a little
            size *= fraction * self.width / dataclasses.replace(self, size=size).measure()[0]
        return dataclasses.replace(self, size=round(size, 1))

    def render(self) -> tuple[np.ndarray, dict]:
        """(texture as an H x W x 3 uint8 array, the PT_TARGETS payload)."""
        S = SUPERSAMPLE
        em = self.size * S
        m, boxes, cx0, cy0 = self._layout()
        H, W = m.shape
        ink_w, ink_h = self._ink(m)
        # Letter centres (ink box centres) and line centres in texture pixels.
        lc = [[(b[0] + b[2]) / 2 - cx0 for b in row] for row in boxes]
        line_y = [(min(b[1] for b in row) + max(b[3] for b in row)) / 2 - cy0 for row in boxes]
        idx = self._letter_index(W, H, lc, line_y)
        glow = np.array(Image.fromarray(m).filter(ImageFilter.GaussianBlur(radius=0.09 * em)), dtype=np.float32)
        glow = np.clip(glow / max(glow.max(), 1) * 1.6, 0, 1) * 255
        rgb = np.dstack([m, glow.astype(np.uint8), ((idx + 1) * LETTER_STEP).astype(np.uint8)])
        px, py = self._sample(m)
        lidx = idx[np.clip(py.astype(int), 0, H - 1), np.clip(px.astype(int), 0, W - 1)].astype(np.uint8)
        scale = 1 / (S * self.px_per_unit)  # world units per texture pixel
        wx, wy = (px - W / 2) * scale, (H / 2 - py) * scale
        half = max(W, H) * scale / 2
        xy = np.empty(2 * self.count, dtype="<i2")
        xy[0::2] = np.clip(np.round(wx / half * 32767), -32767, 32767)
        xy[1::2] = np.clip(np.round(wy / half * 32767), -32767, 32767)
        xy, lidx = _no_leading_slashes(xy, lidx)
        payload = {
            "w": W * scale, "h": H * scale, "em": self.size / self.px_per_unit, "n": self.count, "half": half,
            "letters": sum(len(row) for row in lc), "lines": len(lc),
            "lc": [(x - W / 2) * scale for row in lc for x in row],
            "ly": [(H / 2 - y) * scale for row, y in zip(lc, line_y) for _ in row],
            "ink": [ink_w * scale, ink_h * scale],
            "camera": {"width": self.width, "height": self.height, "fov": self.fov, "distance": self.distance,
                       "end": self.end},
            "xy": base64.b64encode(xy.tobytes()).decode(), "li": base64.b64encode(lidx.tobytes()).decode(),
        }
        return rgb, payload

    @staticmethod
    def _letter_index(W: int, H: int, lc: list[list[float]], line_y: list[float]) -> np.ndarray:
        """Letter index per texture pixel: the line by y (split halfway between line centres), then the nearest
        letter centre in x within the line. Letters count left to right, line after line."""
        ys = np.arange(H) + 0.5
        line_of = np.searchsorted([(a + b) / 2 for a, b in zip(line_y, line_y[1:])], ys)
        idx = np.zeros((H, W), dtype=np.int32)
        first = np.cumsum([0] + [len(row) for row in lc])
        xs = np.arange(W) + 0.5
        for k, row in enumerate(lc):
            col = first[k] + np.searchsorted([(a + b) / 2 for a, b in zip(row, row[1:])], xs)
            idx[line_of == k] = col
        return idx

    def _sample(self, m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """`count` seeded points (texture pixel coordinates) inside the letters, `edge_share` of them on the
        outlines, in random order."""
        rng = np.random.default_rng(self.seed)
        inside = m > 127
        eroded = np.array(Image.fromarray(m).filter(ImageFilter.MinFilter(5))) > 127
        edge = inside & ~eroded
        ys_i, xs_i = np.nonzero(inside)
        ys_e, xs_e = np.nonzero(edge)
        if not len(ys_e):
            ys_e, xs_e = ys_i, xs_i
        ne = int(self.count * self.edge_share)
        ni = self.count - ne
        pi = rng.choice(len(ys_i), ni, replace=len(ys_i) < ni)
        pe = rng.choice(len(ys_e), ne, replace=len(ys_e) < ne)
        px = np.concatenate([xs_i[pi], xs_e[pe]]) + rng.random(self.count)
        py = np.concatenate([ys_i[pi], ys_e[pe]]) + rng.random(self.count)
        order = rng.permutation(self.count)
        return px[order], py[order]

    def write(self, name: str, out: Path) -> tuple[Path, Path]:
        """Write `<name>_targets.js` and `<name>_tex.png` into `out` (created). Returns their paths."""
        if not NAME_RE.match(name):
            raise ValueError(f"name {name!r}: letters, digits, _ and -, starting with a letter")
        rgb, payload = self.render()
        out.mkdir(parents=True, exist_ok=True)
        png, js = out / f"{name}_tex.png", out / f"{name}_targets.js"
        Image.fromarray(rgb, "RGB").save(png, optimize=True)
        js.write_text("window.PT_TARGETS = window.PT_TARGETS || {};\n"
                      f"window.PT_TARGETS[{json.dumps(name)}] = {json.dumps(payload)};\n", encoding="utf-8")
        return js, png


@dataclass(frozen=True)
class Written:
    """A text block `write_block` wrote: the text as written (its size after a fit), the targets and texture files,
    and the ink width and height in frame pixels at the end distance (`ParticleText.measure`)."""

    text: ParticleText
    files: tuple[Path, Path]
    ink: tuple[float, float]

    @property
    def too_wide(self) -> bool:
        """The ink is wider than `MAX_WIDTH` of the frame."""
        return self.ink[0] > MAX_WIDTH * self.text.width

    def report(self) -> list[str]:
        """The size report `particle-text` prints on stderr: the size and the ink's share of the frame, and a
        warning when the text is too wide."""
        t, (w, h) = self.text, self.ink
        lines = [f"size {t.size:g} px: text {w:.0f}x{h:.0f} px at the end distance, {w / t.width:.0%} x "
                 f"{h / t.height:.0%} of the {t.width}x{t.height} frame"]
        if self.too_wide:
            lines.append(f"warning: the text is wider than {MAX_WIDTH:.0%} of the frame; lower --size or "
                         f"pass --fit 0.7")
        return lines


def write_block(text: ParticleText, out: Path, name: str | None = None, fit: float | None = None) -> Written:
    """Write the targets and texture of `text` into `out` as `<name>_targets.js` and `<name>_tex.png` (`name`
    default: `default_name` of the text); with `fit`, at the size whose ink is `fit` of the frame width
    (`ParticleText.fitted`). Raises ValueError as `ParticleText`."""
    if fit is not None:
        text = text.fitted(fit)
    files = text.write(name or default_name(text.lines), out)
    return Written(text, files, text.measure())


def _no_leading_slashes(xy: np.ndarray, li: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Reorder the points so the base64 of `xy` does not start with "//": the page's determinism check reads a
    string starting with "//" as a remote URL."""
    for j in range(len(li)):
        if not base64.b64encode(xy[2 * j:2 * j + 2].tobytes()).startswith(b"//"):
            if j:
                xy, li = xy.copy(), li.copy()
                xy[[0, 1, 2 * j, 2 * j + 1]] = xy[[2 * j, 2 * j + 1, 0, 1]]
                li[[0, j]] = li[[j, 0]]
            return xy, li
    return xy, li


def default_name(lines: list[str] | tuple[str, ...]) -> str:
    """A targets name from the text: lower case letters and digits joined by _, `text` when none."""
    words = re.findall(r"[a-z0-9]+", " ".join(lines).lower())
    name = "_".join(words)[:32].strip("_")
    return name if name and name[0].isalpha() else "text" + ("_" + name if name else "")


def parse_frame(value: str) -> tuple[int, int]:
    """`1920x1080` -> (1920, 1080)."""
    m = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", value)
    if not m:
        raise ValueError(f"frame {value!r}: WIDTHxHEIGHT, e.g. 1080x1920")
    return int(m.group(1)), int(m.group(2))
