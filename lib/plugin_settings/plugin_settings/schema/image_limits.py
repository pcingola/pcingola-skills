"""`providers.<p>.models.<m>.image`: the request limits of an image model, read by media:image-gen. The fields
every kind's limits share; `OpenAIImageLimits` and `DiffusersImageLimits` add the rest."""

from __future__ import annotations

from pydantic import PositiveInt

from .base import Strict


class ImageLimits(Strict):
    """`max_edge`: the longest edge (px)."""

    max_edge: PositiveInt
