"""A provider of kind chatterbox: Chatterbox Turbo on the CPU, in the caller's process; each model needs an entry in
`models`."""

from __future__ import annotations

from typing import Literal

from ..chatterbox_model import ChatterboxModel
from ..fields import Catalogue
from .weights_dir import WeightsDir


class ChatterboxProvider(WeightsDir):
    kind: Literal["chatterbox"]
    models: Catalogue[ChatterboxModel] = {}
