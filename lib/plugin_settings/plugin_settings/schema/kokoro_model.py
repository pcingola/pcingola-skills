"""`providers.<p>.models.<m>` of a kokoro provider: one Kokoro model."""

from __future__ import annotations

from pydantic import Field

from .fields import HttpUrl
from .local_memory import LocalMemory
from .voices import Voices


class KokoroModel(Voices, LocalMemory):
    """`model_url`, `voices_url`: its files, downloaded to `<dir>/<model>/`; `langs`: the espeak-ng language of each
    voice-name prefix (voices of other prefixes are refused); `memory` (`LocalMemory`)."""

    model_url: HttpUrl
    voices_url: HttpUrl
    langs: dict[str, str] = Field(min_length=1)
