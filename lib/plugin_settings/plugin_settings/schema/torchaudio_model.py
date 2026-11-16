"""`providers.<p>.models.<m>` of a torchaudio provider: one forced-alignment pipeline, by its name in
`torchaudio.pipelines` (`MMS_FA`)."""

from __future__ import annotations

from .base import Strict
from .fields import HttpUrl


class TorchaudioModel(Strict):
    """`url`: the pipeline's weights file, downloaded to `<dir>/<model lowercased>/`."""

    url: HttpUrl
