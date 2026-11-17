"""Rendering a shot list: the shots back to back, each crossfaded into the next over its `fade` (the outgoing
shot holds the last frame of its recording interval), at the `video:` size and frame rate, encoded with the
`encode:` codec and pixel format at `screencast.crf`."""

from __future__ import annotations

import subprocess
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

from .. import config, media, settings
from .cards_shot import CardsShot
from .context import RenderContext
from .geometry import ease
from .model import ShotKind, ShotList
from .panel_shot import PanelShot
from .picture_shot import PictureShot
from .renderer import ShotRenderer
from .shotlist import ScreencastError, load
from .style import Style

RENDERERS = {ShotKind.PANEL: PanelShot, ShotKind.PICTURE: PictureShot, ShotKind.CARDS: CardsShot}


class Timeline:
    def __init__(self, shots: ShotList, style: Style, warn=config.warn):
        v = settings.get()["video"]
        self.frame = (int(v["width"]), int(v["height"]))
        self.fps = Fraction(str(v["fps"])).limit_denominator(1001)
        self.shots, self.style = shots, style
        ctx = RenderContext.make(style, self.frame, style.caption.band and shots.has_captions, warn)
        try:
            self.renderers: list[ShotRenderer] = [RENDERERS[s.kind](s, ctx) for s in shots.shots]
        except (ValueError, OSError) as e:
            raise ScreencastError(str(e)) from None
        self.starts = []
        t = 0.0
        for r in self.renderers:
            self.starts.append(t)
            t += r.length
        self.length = t

    @property
    def frame_count(self) -> int:
        return int(round(self.length * self.fps))

    def plan(self, times: list[float]) -> list[tuple[float, list[tuple[int, float, float]]]]:
        """Per film time, the (shot, shot time, weight) parts that make the frame."""
        out = []
        for t in times:
            i = max(j for j, s in enumerate(self.starts) if s <= t + 1e-9) if t >= 0 else 0
            u = round(t - self.starts[i], 4)
            parts = [(i, u, 1.0)]
            fade = self.renderers[i].shot.fade
            if i > 0 and fade > 0 and u < fade:
                a = ease(u / fade)
                parts = [(i - 1, round(self.renderers[i - 1].length + u, 4), 1 - a), (i, u, a)]
            out.append((t, parts))
        return out

    def frames(self, times: list[float]):
        """Yield (film time, uint8 BGR frame) for each time, loading each shot's video frames once."""
        plan = self.plan(times)
        need: dict[int, set[float]] = {}
        for _, parts in plan:
            for j, u, _ in parts:
                need.setdefault(j, set()).add(u)
        loaded: set[int] = set()
        for t, parts in plan:
            for j, _, _ in parts:
                if j not in loaded:
                    self.renderers[j].prepare(sorted(need[j]))
                    loaded.add(j)
                    for q in [q for q in loaded if q < j - 1]:
                        self.renderers[q].release()
                        loaded.discard(q)
            acc = None
            for j, u, w in parts:
                f = self.renderers[j].frame(u, t).astype(np.float32)
                acc = f * w if acc is None else acc + f * w
            yield t, self.renderers[0].ctx.stage.finish(acc)
        for q in loaded:
            self.renderers[q].release()

    def render(self, out: Path) -> Path:
        e = settings.encode()
        w, h = self.frame
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [media.which("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
               "-r", f"{self.fps.numerator}/{self.fps.denominator}", "-i", "-", "-c:v", e["video_codec"],
               "-crf", str(self.style.crf), "-pix_fmt", e["pixel_format"], "-movflags", "+faststart", str(out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            times = [i / float(self.fps) for i in range(self.frame_count)]
            for _, img in self.frames(times):
                proc.stdin.write(img.tobytes())
        except BrokenPipeError:
            pass
        finally:
            proc.stdin.close()
            err = proc.stderr.read().decode(errors="replace")
            proc.wait()
        if proc.returncode != 0:
            raise media.ToolError(f"ffmpeg failed ({proc.returncode}) writing {out}:\n{err.strip()[-2000:]}")
        return out

    def stills(self, times: list[float], stem: Path) -> list[Path]:
        stem.parent.mkdir(parents=True, exist_ok=True)
        paths = []
        for t, img in self.frames([min(max(t, 0.0), max(self.length - 1e-3, 0.0)) for t in times]):
            p = stem.parent / f"{stem.name}_{t:06.3f}.png"
            cv2.imwrite(str(p), img)
            paths.append(p)
        return paths


def render(shot_file: Path, out: Path) -> Path:
    """Render the shot list at `shot_file` to the MP4 `out`."""
    shots, style = load(shot_file)
    return Timeline(shots, style).render(out)


def stills(shot_file: Path, times: list[float], stem: Path) -> list[Path]:
    """PNG frames of the shot list at film times, written as `<stem>_<time>.png`."""
    shots, style = load(shot_file)
    return Timeline(shots, style).stills(times, stem)
