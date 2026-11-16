"""A diffusers image model."""

from __future__ import annotations

from typing import ClassVar

from .diffusers_image_limits import DiffusersImageLimits
from .diffusers_model import DiffusersModel
from .diffusers_role import DiffusersRole


class DiffusersImageModel(DiffusersModel):
    """`inpaint`: the pipeline class for edits with a mask; `image`: the request limits of media:image-gen."""

    role: ClassVar[DiffusersRole] = DiffusersRole.IMAGE

    inpaint: str | None = None
    image: DiffusersImageLimits | None = None
