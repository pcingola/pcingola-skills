"""Creator credit: a "Created by <author>" caption drawn on the video, plus
`artist` and `copyright` metadata tags.

`assemble` draws the caption in the same encode that builds the film, over
every scene whose `storyboard.show_author` is True (the scene's own
`Show author:`, else its template's rule, else True). The caption has
no box: its colour is chosen per scene from the brightness of the corner it
sits in (dark text on a light corner, light text on a dark one). `credit_file`
adds it to any existing MP4: the video is re-encoded once, the audio is copied
unchanged. Texts, style and encoding come from `assets/settings.yaml`.

The caption text is read from a file (`textfile=`, `expansion=none`), so a
name with quotes, colons or `%` needs no filtergraph escaping. The file sits in
a fresh temporary directory whose path contains no characters that need
escaping either.

With a brand (see `brand`), the brand's PNG logo is overlaid right of the
caption text, in the same frames. Its height is a ratio of the caption's cap
height, it is centred on the cap band, and the text moves left by the logo
width plus the gap, so the logo follows whatever the caption says. The text
is then placed by its baseline, so the logo's vertical position does not
depend on which letters the caption has. A brand with `raster_on_dark` gets
that PNG, in the same box, wherever the caption is drawn in the light text
colour (a dark corner); `raster` everywhere else.

`credit.text: null` means no caption text: the logo alone, in the same box,
on every scene including those with `show_author` False (`captioned`);
without a brand, nothing is drawn. The PNG is then chosen by the brightness
of the logo's own surroundings (`measured_region`), not of the wider caption
corner. The metadata tags stay.
"""

from __future__ import annotations

import ast
import operator
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import brand, media, settings

_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")


def _c() -> dict:
    return settings.get()["credit"]


def caption_text(author: str) -> str | None:
    """The caption for `author`; None when `credit.text` is null (logo only)."""
    t = _c()["text"]
    return None if t is None else t.format(author=author)


def captioned(show_author: list[bool]) -> list[bool]:
    """Which scenes get the caption, given each scene's `storyboard.show_author`:
    all of them when there is no caption text (logo only), else those whose
    value is True."""
    return [_c()["text"] is None or s for s in show_author]


def metadata_args(author: str, year: int | None = None) -> list[str]:
    year = year or datetime.now(timezone.utc).year
    return ["-metadata", f"artist={author}", "-metadata", f"copyright={_c()['copyright'].format(year=year, author=author)}"]


def caption_color(luma: float) -> str:
    """Dark text on a light corner, light text on a dark one. No box, no shadow."""
    c = _c()
    return c["dark_text"] if luma >= c["light_background_luma"] else c["light_text"]


def corner_luma(video: Path, times: list[float], region: list[float] | None = None) -> float:
    """Mean luma of `region` (x, y, w, h as fractions of the frame; default
    `credit.corner`, see `measured_region`) over the frames at `times`."""
    x, y, w, h = region or _c()["corner"]
    values = []
    for t in times:
        raw = media.run([
            media.which("ffmpeg"), "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
            "-vf", f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale=1:1:flags=area,format=gray",
            "-f", "rawvideo", "-",
        ], text=False).stdout
        values.append(raw[0])
    return sum(values) / len(values)


def sample_times(duration: float, n: int | None = None) -> list[float]:
    """`n` times (default `samples_per_scene`) spread inside (0, duration),
    avoiding the first and last frames."""
    n = _c()["samples_per_scene"] if n is None else n
    return [duration * (i + 1) / (n + 1) for i in range(n)]


def caption_segments(durations: list[float], colors: list[str | None]) -> list[tuple[float, float, str]]:
    """(start, end, colour) for each captioned scene (colour None = no caption),
    adjacent scenes of the same colour merged."""
    out: list[tuple[float, float, str]] = []
    t = 0.0
    for d, c in zip(durations, colors):
        if c is not None:
            if out and out[-1][2] == c and abs(out[-1][1] - t) < 1e-9:
                out[-1] = (out[-1][0], t + d, c)
            else:
                out.append((t, t + d, c))
        t += d
    return out


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def pixels(expr, height: int) -> float:
    """Value of a size setting such as `h/40` (an FFmpeg expression in the
    frame height `h`) for a frame `height` pixels high."""
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name) and n.id == "h":
            return height
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        raise ValueError(f"size {expr!r}: only numbers, h, + - * / are supported")
    return float(ev(ast.parse(str(expr), mode="eval").body))


@dataclass
class Logo:
    """The brand logo beside the caption: the PNG, the PNG for dark corners
    (None: `path` everywhere) and their box in the frame. `shift` is how far
    the caption text moves left to make room."""
    path: Path
    x: int
    y: int
    w: int
    h: int
    shift: int
    on_dark: Path | None = None

    def png(self, color: str) -> Path:
        """The PNG beside a caption drawn in `color`: `on_dark` behind light
        text (a dark corner), else `path`."""
        return self.on_dark if self.on_dark is not None and color == _c()["light_text"] else self.path


def logo_box(frame: tuple[int, int], png: tuple[int, int], ratios: dict) -> tuple[int, int, int, int, int]:
    """(x, y, w, h, shift) of the logo right of a bottom-right caption whose
    baseline is `margin` above the bottom edge. Height = `ratios.height` x cap
    height, centred on the cap band; ink gap = `ratios.gap` x font size."""
    c = _c()
    fw, fh = frame
    size, margin = pixels(c["font_size"], fh), pixels(c["margin"], fh)
    cap = c["cap_height"] * size
    h = max(1, round(ratios["height"] * cap))
    w = max(1, round(h * png[0] / png[1]))
    x = round(fw - margin - w)
    y = round(fh - margin - cap / 2 - h / 2)
    return x, y, w, h, round(w + ratios["gap"] * size)


def caption_logo(b: dict | None, frame: tuple[int, int], directory: Path) -> Logo | None:
    """The brand's caption logo for a `frame` (width, height), its PNGs
    (`raster`, and `raster_on_dark` when set) copied into `directory` (a path
    safe for the filtergraph). `brand.load` has checked that both PNGs have
    the same aspect ratio, so the box of `raster` holds either. None without
    a brand."""
    if b is None:
        return None
    src = b["dir"] / b["raster"]
    path = directory / "logo.png"
    shutil.copyfile(src, path)
    on_dark = None
    if b.get("raster_on_dark"):
        on_dark = directory / "logo_on_dark.png"
        shutil.copyfile(b["dir"] / b["raster_on_dark"], on_dark)
    return Logo(path, *logo_box(frame, brand.png_size(src), b["caption"]), on_dark=on_dark)


def measured_region(logo: Logo | None, frame: tuple[int, int]) -> list[float]:
    """The region whose brightness picks the caption colour and logo PNG, as
    fractions (x, y, w, h) of a `frame` (width, height): `credit.corner`; with
    no caption text and a logo, the logo box padded by its height on every
    side, clipped to the frame."""
    if logo is None or _c()["text"] is not None:
        return list(_c()["corner"])
    fw, fh = frame
    x0, y0 = max(0, logo.x - logo.h), max(0, logo.y - logo.h)
    x1, y1 = min(fw, logo.x + logo.w + logo.h), min(fh, logo.y + logo.h + logo.h)
    return [x0 / fw, y0 / fh, (x1 - x0) / fw, (y1 - y0) / fh]


def _safe(path: Path, what: str) -> str:
    p = str(path)
    if not _SAFE_PATH.match(p):
        raise ValueError(f"{what} path {p!r} has characters that need filtergraph escaping")
    return p


def _enable(ranges: list[tuple[float, float]] | None) -> str:
    if ranges is None:
        return ""
    return ":enable='" + "+".join(f"between(t,{media.num(a)},{media.num(b)})" for a, b in ranges) + "'"


def drawtext_filter(textfile: Path, color: str, ranges: list[tuple[float, float]] | None = None,
                    logo: Logo | None = None) -> str:
    """One `drawtext` for the caption: bottom right, size and margin relative to
    the frame height. `ranges=None` draws it on every frame. With a `logo`, the
    text moves left to make room and is placed by its baseline."""
    path = _safe(textfile, "caption file")
    c = _c()
    if logo is None:
        pos = f"x=w-tw-{c['margin']}:y=h-th-{c['margin']}"
    else:
        pos = f"x=w-tw-{c['margin']}-{logo.shift}:y=h-{c['margin']}:y_align=baseline"
    return (f"drawtext=textfile='{path}':expansion=none:font={c['font']}:fontsize={c['font_size']}"
            f":fontcolor={color}:{pos}" + _enable(ranges))


def logo_filter(logo: Logo, ranges: list[tuple[float, float]] | None = None, png: Path | None = None,
                i: int = 0) -> str:
    """Overlay the PNG `png` (default `logo.path`) in the box of `logo` on the
    preceding stream, labelled `[cap<i>]` (anti-aliased downscale, full
    opacity), in the frames of `ranges` (None: every frame). Distinct `i`
    let several overlays follow each other in one chain."""
    path = _safe(png or logo.path, "logo")
    return (f"[cap{i}];movie='{path}',scale={logo.w}:{logo.h}:flags=lanczos,format=rgba[logo{i}];"
            f"[cap{i}][logo{i}]overlay=x={logo.x}:y={logo.y}" + _enable(ranges))


def caption_filter(textfile: Path | None, segments: list[tuple[float, float, str]],
                   logo: Logo | None = None) -> str | None:
    """The caption as a video filter chain: one `drawtext` per colour, each
    enabled over the segments of that colour, then one logo overlay per PNG
    (`Logo.png` of the segment's colour), each over its segments.
    `textfile=None`: the logo overlays only. None when there are no segments,
    or neither text nor logo."""
    by_color: dict[str, list[tuple[float, float]]] = {}
    for a, b, c in segments:
        by_color.setdefault(c, []).append((a, b))
    if not by_color or (textfile is None and logo is None):
        return None
    if textfile is None:
        f = "null"
    else:
        f = ",".join(drawtext_filter(textfile, c, r, logo) for c, r in by_color.items())
    if logo is not None:
        by_png: dict[Path, list[tuple[float, float]]] = {}
        for c, r in by_color.items():
            by_png.setdefault(logo.png(c), []).extend(r)
        f += "".join(logo_filter(logo, sorted(r), png, i) for i, (png, r) in enumerate(by_png.items()))
    return f


def write_caption(directory: Path, author: str) -> Path | None:
    """The caption text file in `directory`; None when there is no caption text."""
    text = caption_text(author)
    if text is None:
        return None
    p = directory / "caption.txt"
    p.write_text(text, encoding="utf-8")
    return p


def credit_file(src: Path, out: Path, author: str, b: dict | None = None) -> Path:
    """Write `out`: `src` with the caption (or, with `credit.text` null, the
    logo alone) on every frame and the metadata tags.
    The caption colour is chosen from the corner's brightness over the video.
    With a brand `b` (see `brand.load`), its logo goes beside the caption:
    the one for that colour (`Logo.png`)."""
    if src.resolve() == out.resolve():
        raise media.ToolError("the output must be a different file from the input")
    e = settings.encode()
    with tempfile.TemporaryDirectory() as d:
        textfile = write_caption(Path(d), author)
        frame = media.video_size(src)
        logo = caption_logo(b, frame, Path(d))
        color = caption_color(corner_luma(src, sample_times(media.video_duration(src), _c()["samples_per_video"]),
                                          measured_region(logo, frame)))
        vf = (drawtext_filter(textfile, color, logo=logo) if textfile else "null") \
            + (logo_filter(logo, png=logo.png(color)) if logo else "")
        media.run([
            media.which("ffmpeg"), "-y", "-v", "error", "-i", src,
            "-map", "0:v:0", "-map", "0:a?", "-vf", vf,
            "-c:v", e["video_codec"], "-crf", str(e["crf"]), "-pix_fmt", e["pixel_format"], "-c:a", "copy",
            *metadata_args(author), "-movflags", "+faststart", out,
        ])
    return out
