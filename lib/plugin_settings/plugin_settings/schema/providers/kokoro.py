"""A provider of kind kokoro: Kokoro speech on the CPU. `model_url`, `voices_url`: its files, downloaded to
`<dir>/<model>/`; `langs`: espeak-ng language of each voice-name prefix; `voice`: the default voice."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..fields import HttpUrl, UserPath
from .base import TimedProvider


class KokoroProvider(TimedProvider):
    kind: Literal["kokoro"]
    model_url: HttpUrl
    voices_url: HttpUrl
    langs: dict[str, str] = Field(min_length=1)
    voice: str | None = None
    voices: list[str] | None = None
    dir: UserPath | None = None
