"""The image limits of a diffusers image model."""

from __future__ import annotations

from pydantic import PositiveInt, model_validator

from .image_limits import ImageLimits


class DiffusersImageLimits(ImageLimits):
    """`min_edge`: the shortest edge (px)."""

    min_edge: PositiveInt

    @model_validator(mode="after")
    def _range(self) -> DiffusersImageLimits:
        if self.min_edge > self.max_edge:
            raise ValueError(f"min_edge {self.min_edge} is above max_edge {self.max_edge}")
        return self
