"""`providers.<p>.models.<m>` of a torchaudio provider: one forced-alignment pipeline, by its name in
`torchaudio.pipelines` (`MMS_FA`)."""

from __future__ import annotations

from .fields import HttpUrl
from .local_memory import LocalMemory


class TorchaudioModel(LocalMemory):
    """`url`: the pipeline's weights file, downloaded to `<dir>/<model lowercased>/`; `memory` (`LocalMemory`)."""

    url: HttpUrl
