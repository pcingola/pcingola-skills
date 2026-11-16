"""Stills of a scene page at given times, without an MP4.

`hyperframes snapshot --at` loads the page in the render browser and seeks it
the way `render` does (the GSAP timeline `window.__timelines[<id>]`, or the
`hf-seek` event for anime.js, Motion and three.js pages) at each exact time. A
world scene's time `t` is world time `start + t`. The PNGs go to
`<page dir>/stills/` as `at_<t>.png` (a world scene: `<scene>_at_<t>.png`), in
scene time.

Each time is seeked twice, first `WARM` s later, and only the second shot is
kept. On the hardware GPU (ANGLE on the GPU driver), the first three.js
draw that links new shader programs can come out all black (`readPixels` reads
0,0,0 while the context is live); a second draw of the same state is correct.
GSAP calls no `onUpdate` for a seek to the time it is at, so the warm-up time
differs. A WebGL page's still that is still blank (at least `BLANK_FRACTION` of
its pixels exactly #000000) is taken again once in a new browser; a second
blank still fails. SwiftShader (`--no-browser-gpu`) draws no black frame, but
its software compositor paints a rectangle in the page colour over the canvas
at a DOM overlay's position mirrored vertically, so the snapshot keeps the GPU.

`--mark` draws a red point (`x,y`) or rectangle (`x,y,w,h`), in frame pixels,
on a copy `..._mark.png`. `--sheet` joins the stills into one labelled contact
sheet (`contact_sheet.width` and `columns` of settings).
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import media, scenes, settings
from .pages import Page
from .scenes import SceneError

STILLS = "stills"
RED = "red"
# The share of exact #000000 pixels at which a WebGL page's still counts as blank (a blank canvas read 0.8).
BLANK_FRACTION = 0.5
# The warm-up seek before each still, in seconds: under one frame at 30 fps, so the same programs draw.
WARM = 0.005
_WEBGL = re.compile(r"WebGLRenderer|getContext\(\s*[\"']webgl", re.I)


@dataclass(frozen=True)
class Mark:
    """A point (`w`, `h` None) or a rectangle in frame pixels."""

    x: float
    y: float
    w: float | None = None
    h: float | None = None

    @classmethod
    def parse(cls, text: str) -> Mark:
        """`x,y` or `x,y,w,h`; ValueError otherwise."""
        parts = [float(v) for v in text.split(",")]
        if len(parts) == 2:
            return cls(*parts)
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return cls(*parts)
        raise ValueError(f"--mark takes x,y or x,y,w,h (w, h > 0), not {text!r}")

    def filter(self) -> str:
        """The FFmpeg `drawbox` chain that draws the mark: a rectangle outline, or a ring with a dot for a point."""
        if self.w is not None:
            return f"drawbox=x={self.x:.0f}:y={self.y:.0f}:w={self.w:.0f}:h={self.h:.0f}:color={RED}:t=6"
        return (f"drawbox=x={self.x - 22:.0f}:y={self.y - 22:.0f}:w=44:h=44:color={RED}:t=5,"
                f"drawbox=x={self.x - 4:.0f}:y={self.y - 4:.0f}:w=8:h=8:color={RED}:t=fill")


def parse_times(text: str) -> list[float]:
    """Comma-separated seconds; ValueError when one is not a number."""
    times = [float(t) for t in text.split(",") if t.strip()]
    if not times:
        raise ValueError("no time given")
    return times


def still_name(scene_id: str, page: Page, t: float) -> str:
    return (f"{scene_id}_" if page.world else "") + f"at_{t:07.3f}.png"


_SNAP = re.compile(r"^frame-(\d+)-at-.*\.png$")


def warm_times(page_times: list[float]) -> list[float]:
    """Each time preceded by its warm-up time, `WARM` s later (later keeps time 0 valid)."""
    return [x for t in page_times for x in (t + WARM, t)]


def snapshot(page_dir: Path, page_times: list[float], node_dir: Path) -> list[Path]:
    """PNGs of `page_dir/index.html` at each page time, in order, from `hyperframes snapshot` (each time after its
    warm-up seek), in a temporary directory the caller moves them out of."""
    out = Path(tempfile.mkdtemp(prefix="stills-"))
    asked = len(page_times)
    media.run([str(node_dir / scenes.HYPERFRAMES_REL), "snapshot", str(page_dir),
               "--at", ",".join(f"{t:.4f}" for t in warm_times(page_times)), "--no-end", "-o", str(out),
               "--describe", "false"],
              cwd=page_dir, env=scenes.node_env(node_dir))
    shots = sorted((int(m.group(1)), p) for p in out.iterdir() if (m := _SNAP.match(p.name)))
    if len(shots) != 2 * asked:
        raise SceneError(f"hyperframes snapshot wrote {len(shots)} PNGs for {2 * asked} times in {out}")
    for _, p in shots[0::2]:
        p.unlink()
    return [p for _, p in shots[1::2]]


def uses_webgl(html: str) -> bool:
    """True when the page creates a WebGL context (a three.js renderer or `getContext("webgl...")`)."""
    return bool(_WEBGL.search(html))


def black_fraction(png: Path) -> float:
    """The share of pixels of `png` that are exactly #000000."""
    w, h = media.video_size(png)
    raw = media.run([media.which("ffmpeg"), "-v", "error", "-i", png, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                    text=False).stdout
    px = np.frombuffer(raw, dtype=np.uint8).reshape(h * w, 3)
    return float(np.mean(~px.any(axis=1)))


def is_blank(png: Path) -> bool:
    return black_fraction(png) >= BLANK_FRACTION


def snapshot_checked(page_dir: Path, page_times: list[float], node_dir: Path, webgl: bool) -> list[Path]:
    """`snapshot`, then for a WebGL page each blank still taken again once; SceneError when it stays blank."""
    shots = snapshot(page_dir, page_times, node_dir)
    if not webgl:
        return shots
    blank = [i for i, p in enumerate(shots) if is_blank(p)]
    if not blank:
        return shots
    again = snapshot(page_dir, [page_times[i] for i in blank], node_dir)
    for i, p in zip(blank, again):
        shutil.move(p, shots[i])
    shutil.rmtree(again[0].parent, ignore_errors=True)
    still_blank = [page_times[i] for i in blank if is_blank(shots[i])]
    if still_blank:
        shutil.rmtree(shots[0].parent, ignore_errors=True)
        raise SceneError(f"stills at page times {', '.join(f'{t:g}' for t in still_blank)} s are blank twice: at least "
                         f"{BLANK_FRACTION:.0%} of the frame is exactly #000000, the WebGL canvas drew nothing. "
                         "Check the page's console errors and its draw at that time; a ground meant to be black "
                         "uses a near-black such as #050505.")
    return shots


def draw_mark(src: Path, mark: Mark) -> Path:
    """`src` with the mark drawn, as `<stem>_mark.png` next to it."""
    out = src.with_name(src.stem + "_mark.png")
    media.run([media.which("ffmpeg"), "-y", "-v", "error", "-i", src, "-vf", mark.filter(), out])
    return out


def sheet_filter(labels: list[str], width: int, columns: int) -> str:
    """`-filter_complex` that scales each input to `width`, writes its label and tiles them `columns` wide."""
    n = len(labels)
    cols = min(columns, n)
    rows = -(-n // cols)
    parts = [f"[{i}:v]scale={width}:-2,drawtext=text='{label}':expansion=none:fontcolor=white:fontsize=22"
             f":box=1:boxcolor=black@0.6:boxborderw=6:x=8:y=8[s{i}]" for i, label in enumerate(labels)]
    joined = "".join(f"[s{i}]" for i in range(n))
    return ";".join(parts) + f";{joined}concat=n={n}:v=1:a=0,tile={cols}x{rows}"


def contact_sheet(pngs: list[Path], labels: list[str], out: Path) -> Path:
    """One PNG of `pngs`, labelled, `contact_sheet.columns` per row."""
    c = settings.get()["contact_sheet"]
    inputs = [a for p in pngs for a in ("-i", p)]
    media.run([media.which("ffmpeg"), "-y", "-v", "error", *inputs, "-filter_complex",
               sheet_filter(labels, c["width"], c["columns"]), "-frames:v", "1", out])
    return out


def stills(scene_id: str, page: Page, times: list[float], node_dir: Path, mark: Mark | None = None,
           sheet: bool = False) -> list[Path]:
    """Stills of the scene at scene times `times`; with `mark` also the marked copies, with `sheet` also the
    contact sheet (last). Returns the paths written."""
    for t in times:
        if not 0 <= t < page.duration:
            raise SceneError(f"time {t} is outside scene {scene_id} (0 to {page.duration:.2f} s)")
    html = (page.dir / "index.html").read_text(encoding="utf-8")
    scenes.copy_page_files(page.dir, html, node_dir, missing_only=True)
    shots = snapshot_checked(page.dir, [page.start + t for t in times], node_dir, uses_webgl(html))
    out_dir = page.dir / STILLS
    out_dir.mkdir(exist_ok=True)
    paths = []
    for t, shot in zip(times, shots):
        p = out_dir / still_name(scene_id, page, t)
        shutil.move(shot, p)
        paths.append(p)
    shutil.rmtree(shots[0].parent, ignore_errors=True)
    out = list(paths)
    if mark is not None:
        out += [draw_mark(p, mark) for p in paths]
    if sheet:
        name = (f"{scene_id}_" if page.world else "") + "sheet.png"
        out.append(contact_sheet(paths, [f"{scene_id} {t:.2f} s" for t in times], out_dir / name))
    return out
