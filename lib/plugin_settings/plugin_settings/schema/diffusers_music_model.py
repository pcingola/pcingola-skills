"""A diffusers music model."""

from __future__ import annotations

from typing import ClassVar

from .diffusers_model import DiffusersModel
from .diffusers_role import DiffusersRole


class DiffusersMusicModel(DiffusersModel):
    """`duration_arg`: the pipeline call argument of the length in seconds; `lyrics_arg`: that of the lyrics (None:
    the model takes no lyrics); `min_crest_db`: a track whose crest factor is below it is loud and compressed (None:
    no check)."""

    role: ClassVar[DiffusersRole] = DiffusersRole.MUSIC

    duration_arg: str
    lyrics_arg: str | None = None
    min_crest_db: float | None = None
