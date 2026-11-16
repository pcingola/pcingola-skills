"""`providers.<p>.models.<m>` of a diffusers provider: a local model, loaded in process."""

from __future__ import annotations

from typing import Any

from pydantic import PositiveInt

from .base import Strict
from .image_limits import ImageLimits

# The fields an image-to-video model needs (`ai_models.video`), and those of a presenter model.
VIDEO_FIELDS = ("pipeline", "fps", "size_multiple", "frame_step", "width", "height", "max_frames")
PRESENTER_FIELDS = ("pipeline", "fps", "buckets", "audio_rate", "output")


class DiffusersModel(Strict):
    """`repo` (Hugging Face repository) and the pipeline settings. Every model: `steps`, `guidance` (none: no
    `guidance_scale`), `inpaint` (pipeline class for mask edits), `args` (more call arguments), `skip` (components
    loaded as None), `image`. Music: `duration_arg`, `lyrics_arg`, `min_crest_db`. Video: VIDEO_FIELDS. Presenter:
    PRESENTER_FIELDS."""

    repo: str
    steps: PositiveInt | None = None
    guidance: float | None = None
    inpaint: str | None = None
    args: dict[str, Any] = {}
    skip: list[str] = []
    duration_arg: str | None = None
    lyrics_arg: str | None = None
    min_crest_db: float | None = None
    pipeline: str | None = None
    fps: PositiveInt | None = None
    size_multiple: PositiveInt | None = None
    frame_step: PositiveInt | None = None
    width: PositiveInt | None = None
    height: PositiveInt | None = None
    max_frames: PositiveInt | None = None
    buckets: list[tuple[PositiveInt, PositiveInt]] | None = None
    audio_rate: PositiveInt | None = None
    output: str | None = None
    image: ImageLimits | None = None

    def missing(self, fields: tuple[str, ...]) -> list[str]:
        """The names of `fields` this entry does not set."""
        return [f for f in fields if getattr(self, f) is None]

    def missing_video(self) -> list[str]:
        """The VIDEO_FIELDS this entry lacks for an image-to-video model."""
        return self.missing(VIDEO_FIELDS)

    def missing_presenter(self) -> list[str]:
        """The PRESENTER_FIELDS this entry lacks for a presenter model."""
        return self.missing(PRESENTER_FIELDS)


