"""A diffusers image-to-video model (`ai_models.video.animate`)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import PositiveInt

from .diffusers_model import DiffusersModel
from .diffusers_role import DiffusersRole


class DiffusersVideoModel(DiffusersModel):
    """`pipeline`: the class to load; `fps`; `size_multiple`: width and height are rounded to it; `frame_step`:
    frame counts are frame_step * k + 1; `width`, `height`: the default size; `max_frames`: the longest clip."""

    role: ClassVar[DiffusersRole] = DiffusersRole.VIDEO

    pipeline: str
    fps: PositiveInt
    size_multiple: PositiveInt
    frame_step: PositiveInt
    width: PositiveInt
    height: PositiveInt
    max_frames: PositiveInt
