"""A mark on a still: a point (red ring) or a rectangle (red outline), in stage pixels."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from .common import HAError

RED = (255, 0, 0)
RING_RADIUS = 28
LINE = 6
SPEC_RE = re.compile(r"^(point|rect):(-?\d+(?:\.\d+)?(?:,-?\d+(?:\.\d+)?)*)$")


@dataclass(frozen=True)
class Mark:
    x: float
    y: float
    w: float | None = None
    h: float | None = None

    @property
    def is_rect(self) -> bool:
        return self.w is not None

    @classmethod
    def parse(cls, spec: str) -> Mark:
        """`point:X,Y` or `rect:X,Y,W,H`."""
        m = SPEC_RE.match(spec.strip())
        nums = [float(v) for v in m.group(2).split(",")] if m else []
        if m and m.group(1) == "point" and len(nums) == 2:
            return cls(nums[0], nums[1])
        if m and m.group(1) == "rect" and len(nums) == 4 and nums[2] > 0 and nums[3] > 0:
            return cls(*nums)
        raise HAError(f"--mark {spec!r}: expected point:X,Y or rect:X,Y,W,H with W and H above 0")

    def to_dict(self) -> dict:
        if self.is_rect:
            return {"rect": {"x": self.x, "y": self.y, "w": self.w, "h": self.h}}
        return {"point": {"x": self.x, "y": self.y}}

    def draw(self, png: Path) -> None:
        img = Image.open(png).convert("RGB")
        d = ImageDraw.Draw(img)
        if self.is_rect:
            d.rectangle([self.x, self.y, self.x + self.w, self.y + self.h], outline=RED, width=LINE)
        else:
            r = RING_RADIUS
            d.ellipse([self.x - r, self.y - r, self.x + r, self.y + r], outline=RED, width=LINE)
        img.save(png)
