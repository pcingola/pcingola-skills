"""A provider of kind chatterbox: Chatterbox Turbo in a worker process of its own environment (`python`), one per
model; each model needs an entry in `models`."""

from __future__ import annotations

from typing import Literal

from ..chatterbox_model import ChatterboxModel
from ..fields import Catalogue
from .own_environment import OwnEnvironment
from .weights_dir import WeightsDir


class ChatterboxProvider(OwnEnvironment, WeightsDir):
    kind: Literal["chatterbox"]
    models: Catalogue[ChatterboxModel] = {}
