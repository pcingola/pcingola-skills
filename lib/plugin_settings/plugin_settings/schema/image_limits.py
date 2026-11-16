"""`providers.<p>.models.<m>.image`: the request limits of an image model, read by media:image-gen."""

from __future__ import annotations

from pydantic import NonNegativeInt, PositiveInt, model_validator

from .base import Strict
from .quality import Quality


class ImageLimits(Strict):
    """The longest edge (px), the shortest edge, the pixel count range (`max_pixels` None: no cap), whether every
    request gets a size (`always_sized`; default 1:1, 1K) and the quality when the caller gives none."""

    max_edge: PositiveInt
    min_edge: NonNegativeInt = 0
    min_pixels: NonNegativeInt = 0
    max_pixels: PositiveInt | None = None
    always_sized: bool = False
    default_quality: Quality | None = None

    @model_validator(mode="after")
    def _ranges(self) -> ImageLimits:
        if self.min_edge > self.max_edge:
            raise ValueError(f"min_edge {self.min_edge} is above max_edge {self.max_edge}")
        if self.max_pixels is not None and self.min_pixels > self.max_pixels:
            raise ValueError(f"min_pixels {self.min_pixels} is above max_pixels {self.max_pixels}")
        return self
