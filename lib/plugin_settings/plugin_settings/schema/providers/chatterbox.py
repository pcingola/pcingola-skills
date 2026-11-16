"""A provider of kind chatterbox: Chatterbox Turbo in a worker of its own environment (`python`). `url` and
`files`: the model files, downloaded to `<dir>/<model>/`; `start_timeout`: seconds the load may take."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, PositiveFloat

from ..fields import HttpUrl, UserPath
from .base import DEFAULT_TIMEOUT, TimedProvider


class ChatterboxProvider(TimedProvider):
    kind: Literal["chatterbox"]
    python: UserPath
    url: HttpUrl
    files: list[str] = Field(min_length=1)
    dir: UserPath | None = None
    voice: str | None = None
    voices: list[str] | None = None
    start_timeout: PositiveFloat = DEFAULT_TIMEOUT
