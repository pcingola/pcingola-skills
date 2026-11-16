"""A provider of kind torchaudio: a forced-alignment pipeline; `url` is its weights file, downloaded to
`<dir>/<model>/`."""

from __future__ import annotations

from typing import Literal

from ..fields import HttpUrl, UserPath
from .base import TimedProvider


class TorchaudioProvider(TimedProvider):
    kind: Literal["torchaudio"]
    url: HttpUrl
    dir: UserPath | None = None
