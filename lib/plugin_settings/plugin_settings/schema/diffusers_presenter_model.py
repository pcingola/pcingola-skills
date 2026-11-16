"""A diffusers presenter model: a portrait and a speech recording to a clip of the person speaking
(`ai_models.video.present`)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import PositiveInt

from .diffusers_model import DiffusersModel
from .diffusers_role import DiffusersRole


class DiffusersPresenterModel(DiffusersModel):
    """`pipeline`: a DiffusionPipeline or ModularPipeline class; `fps`; `buckets`: the frame sizes the model makes,
    [width, height]; `audio_rate`: the sample rate (Hz) it takes the speech at; `output`: the pipeline output that
    holds the videos."""

    role: ClassVar[DiffusersRole] = DiffusersRole.PRESENTER

    pipeline: str
    fps: PositiveInt
    buckets: list[tuple[PositiveInt, PositiveInt]]
    audio_rate: PositiveInt
    output: str
