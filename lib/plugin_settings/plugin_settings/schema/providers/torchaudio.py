"""A provider of kind torchaudio: forced-alignment pipelines on the CPU, in the caller's process; each model needs
an entry in `models`."""

from __future__ import annotations

from typing import Literal

from ..fields import Catalogue
from ..torchaudio_model import TorchaudioModel
from .weights_dir import WeightsDir


class TorchaudioProvider(WeightsDir):
    kind: Literal["torchaudio"]
    models: Catalogue[TorchaudioModel] = {}
