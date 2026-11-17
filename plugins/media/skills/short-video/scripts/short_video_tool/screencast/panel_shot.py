"""A panel shot: a page (a recording interval, a screenshot or a wipe of two pictures) as a 3D panel with
its camera, highlights, clicks, typing, marks, patches, grade, inserted video and labels."""

from __future__ import annotations

import numpy as np

from . import pictures
from .camera import Camera
from .context import RenderContext
from .frame_stream import FrameStream
from .geometry import piecewise
from .model import Shot
from .page_edits import apply_grade, apply_patches, draw_marks
from .pyramid import Pyramid
from .renderer import ShotRenderer
from .typing_reveal import TypingReveal
from .video_source import VideoSource
from .wipe_source import WipeSource

# The camera may enlarge the source up to this factor past its own resolution before `screencast` warns.
ZOOM_SLACK = 1.25
# Below about this many screen px per page px, UI text is unreadable.
LEGIBLE_ZOOM = 1.4


class PanelShot(ShotRenderer):
    banded = True

    def __init__(self, shot: Shot, ctx: RenderContext):
        super().__init__(shot, ctx)
        self.video = VideoSource(shot.video) if shot.video else None
        self.still = pictures.load(shot.image, shot.upscale) if shot.image else None
        # source px per page px: `scale` of the picture as given, times what `upscale` enlarged it by, so page
        # coordinates stay the given picture's px divided by `scale`
        self.scale = shot.scale
        if shot.image:
            self.scale *= pictures.upscale_factor(shot.image, shot.upscale)
        elif shot.wipe:
            self.scale *= pictures.upscale_factor(shot.wipe.before, shot.upscale)
        if shot.wipe:
            self.wipe = WipeSource(shot.wipe, shot.upscale, self.scale, ctx.warn)
        shape = (self.video.height, self.video.width) if self.video else (self.still if self.still is not None
                                                                          else self.wipe).shape[:2]
        self.page = shot.rect or (0.0, 0.0, shape[1] / self.scale, shape[0] / self.scale)
        self.camera = Camera.resolve(shot.camera, self.page, ctx.frame)
        self.radius = ctx.style.panel.radius if shot.radius is None else shot.radius
        self.typing = [TypingReveal(apply_patches(self.still, shot.patches, self.scale), t, self.scale)
                       for t in shot.typing]
        self.stream: FrameStream | None = None
        self.inserts: list[FrameStream | np.ndarray] = []
        self.static: Pyramid | None = None
        if self.still is not None and not shot.typing and not shot.draws:
            self.static = Pyramid(self.edit(self.still, 0.0), self.scale)
        self.check_zoom()

    def check_zoom(self) -> None:
        s, warn = self.shot, self.ctx.warn
        zooms = [self.camera.at(s.length * i / 20).zoom for i in range(21)]
        if max(zooms) > self.scale * ZOOM_SLACK:
            fix = ("frame a larger rect or lower the zoom" if self.scale >= 2
                   else "capture the page at 2x (`scale: 2`) or lower the zoom")
            warn(f"shot {s.index}: the camera zooms to {max(zooms):.2f} screen px per page px, past the source's "
                 f"{self.scale:g} px per page px, so the page blurs: {fix}")
        if (s.highlights or s.clicks or s.typing) and max(zooms) < LEGIBLE_ZOOM:
            warn(f"shot {s.index}: the camera stays below {LEGIBLE_ZOOM} screen px per page px (at most "
                 f"{max(zooms):.2f}), where UI text is unreadable; frame a smaller rect around the control")

    def source_time(self, u: float) -> float:
        """The recording time shown at shot time u; held at the interval's end past the shot (a crossfade
        reads the outgoing shot past its length)."""
        s = self.shot
        u = min(max(u, 0.0), s.length)
        if s.times:
            return piecewise(s.times, u)
        end = s.end if s.end is not None else s.start + s.length
        return s.start + (end - s.start) * (u / s.length)

    def prepare(self, times: list[float]) -> None:
        if self.video:
            self.stream = self.video.stream()
        for ins in self.shot.inserts:
            self.inserts.append(VideoSource(ins.video).stream() if ins.video else pictures.load(ins.image))

    def release(self) -> None:
        if self.stream is not None:
            self.stream.close()
            if self.stream.black:
                black = sorted(self.stream.black)
                self.ctx.warn(f"shot {self.shot.index}: {self.video.path.name} is black at {black[0]:.2f} s "
                              f"({len(black)} frames); a native dropdown or a page load renders black for about "
                              "0.5 s: end the interval before it or start after it")
            self.stream = None
        for ins in self.inserts:
            if isinstance(ins, FrameStream):
                ins.close()
        self.inserts = []

    def insert_time(self, i: int, u: float) -> float:
        ins, n = self.shot.inserts[i], self.shot.length
        end = ins.end if ins.end is not None else ins.start + n
        return ins.start + (end - ins.start) * min(max(u, 0.0), n) / n

    def edit(self, img: np.ndarray, u: float) -> np.ndarray:
        """img with the shot's patches, typing, grade and marks at shot time u."""
        s = self.shot
        img = apply_patches(img, s.patches, self.scale)
        for t in self.typing:
            img = t.frame(img, u)
        return draw_marks(apply_grade(img, s.grade), s.draws, u, self.scale)

    def page_image(self, u: float) -> np.ndarray:
        if self.video:
            img = self.stream.at(self.source_time(u))
        elif self.wipe:
            img = self.wipe.frame(u)
        else:
            img = self.still
        return self.edit(img, u)

    def frame(self, u: float, t: float) -> np.ndarray:
        s, stage = self.shot, self.ctx.stage
        cam = self.camera.at(u)
        pyr = self.static or Pyramid(self.page_image(u), self.scale)
        inserts = []
        for i, (ins, src) in enumerate(zip(s.inserts, self.inserts)):
            img = src.at(self.insert_time(i, u)) if isinstance(src, FrameStream) else src
            inserts.append((img, ins.rect))
        out = stage.panel(t, cam, pyr, self.page, self.radius, inserts)
        for hl in s.highlights:
            out = stage.highlight(out, u, cam, hl)
        for c in s.clicks:
            out = stage.click(out, u, cam, c)
        if self.wipe:
            x = self.wipe.x(u)
            px, py, pw, ph = self.page
            top, bottom = stage.project([[x, py], [x, py + ph]], cam)
            out = self.divider(out, u, top, bottom)
        return self.overlays(out, u, cam)
