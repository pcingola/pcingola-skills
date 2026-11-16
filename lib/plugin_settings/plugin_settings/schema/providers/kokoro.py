"""A provider of kind kokoro: Kokoro speech on the CPU, in the caller's process; each model needs an entry in
`models`."""

from __future__ import annotations

from typing import Literal

from ..fields import Catalogue
from ..kokoro_model import KokoroModel
from .weights_dir import WeightsDir


class KokoroProvider(WeightsDir):
    kind: Literal["kokoro"]
    models: Catalogue[KokoroModel] = {}
