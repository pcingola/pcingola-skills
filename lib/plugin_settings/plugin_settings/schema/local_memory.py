"""The `memory` key of a local model entry: the GB the model takes at its peak."""

from __future__ import annotations

from pydantic import PositiveFloat

from .base import Strict


class LocalMemory(Strict):
    """`memory`: the GB the model takes at its peak, checked against the free memory before the load (None: no
    check of its own; a diffusers load still checks its weights against the free memory)."""

    memory: PositiveFloat | None = None
