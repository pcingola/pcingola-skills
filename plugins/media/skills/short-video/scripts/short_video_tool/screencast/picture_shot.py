"""A picture shot: a picture (or a wipe of two) filling the frame, with an eased camera (no tilt),
highlights, clicks, marks, patches, grade and labels."""

from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np

from . import pictures
from .camera import Camera
from .context import RenderContext
from .model import Shot
from .page_edits import apply_grade, apply_patches, draw_marks
from .renderer import ShotRenderer
from .wipe_source import WipeSource


class PictureShot(ShotRenderer):
    def __init__(self, shot: Shot, ctx: RenderContext):
        super().__init__(shot, ctx)
        self.still = pictures.load(shot.image, shot.upscale) if shot.image else None
        # source px per page px, `upscale` included (page coordinates are the given picture's px / `scale`)
        self.scale = shot.scale * pictures.upscale_factor(shot.image or shot.wipe.before, shot.upscale)
        if shot.wipe:
            self.wipe = WipeSource(shot.wipe, shot.upscale, self.scale, ctx.warn)
        h, w = (self.still if self.still is not None else self.wipe).shape[:2]
        self.page = (0.0, 0.0, w / self.scale, h / self.scale)
        self.camera = Camera.resolve(shot.camera, self.page, ctx.frame, fill=True)

    def frame(self, u: float, t: float) -> np.ndarray:
        s = self.shot
        cam = replace(self.camera.at(u), yaw=0.0, pitch=0.0)
        img = self.wipe.frame(u) if self.wipe else self.still
        img = draw_marks(apply_grade(apply_patches(img, s.patches, self.scale), s.grade), s.draws, u, self.scale)
        fw, fh = self.ctx.frame
        z = cam.zoom / self.scale
        cx, cy = cam.center[0] * self.scale, cam.center[1] * self.scale
        m = np.float32([[z, 0, fw / 2 - cx * z], [0, z, fh / 2 - cy * z]])
        out = cv2.warpAffine(img, m, (fw, fh), flags=cv2.INTER_CUBIC if z > 1 else cv2.INTER_AREA,
                             borderMode=cv2.BORDER_REFLECT).astype(np.float32)
        stage = self.ctx.stage
        for hl in s.highlights:
            out = stage.highlight(out, u, cam, hl)
        for c in s.clicks:
            out = stage.click(out, u, cam, c)
        if self.wipe:
            x = self.wipe.x(u)
            top, bottom = stage.project([[x, self.page[1]], [x, self.page[1] + self.page[3]]], cam)
            top[1], bottom[1] = max(top[1], 0), min(bottom[1], fh)
            out = self.divider(out, u, top, bottom)
        return self.overlays(out, u, cam)
