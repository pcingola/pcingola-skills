"""The image limits of a model of an OpenAI kind (ollama, openrouter, openai, azure)."""

from __future__ import annotations

from pydantic import NonNegativeInt, PositiveInt, model_validator

from .image_limits import ImageLimits
from .quality import Quality


class OpenAIImageLimits(ImageLimits):
    """The pixel count range of a request (`min_pixels`, `max_pixels`), whether every request gets a size
    (`always_sized`; default 1:1, 1K) and the quality when the caller gives none (`default_quality`)."""

    min_pixels: NonNegativeInt
    max_pixels: PositiveInt
    always_sized: bool = False
    default_quality: Quality | None = None

    @model_validator(mode="after")
    def _range(self) -> OpenAIImageLimits:
        if self.min_pixels > self.max_pixels:
            raise ValueError(f"min_pixels {self.min_pixels} is above max_pixels {self.max_pixels}")
        return self
