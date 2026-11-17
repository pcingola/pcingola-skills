"""A provider of kind fish: Fish Audio speech models (Drama 3) through fish-speech on an NVIDIA GPU, in the caller's
process; each model needs an entry in `models`."""

from __future__ import annotations

from typing import Literal

from ..base import Strict
from ..fields import Catalogue
from ..fish_model import FishModel


class FishProvider(Strict):
    kind: Literal["fish"]
    models: Catalogue[FishModel] = {}
