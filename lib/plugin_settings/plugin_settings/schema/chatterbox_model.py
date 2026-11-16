"""`providers.<p>.models.<m>` of a chatterbox provider: one Chatterbox model."""

from __future__ import annotations

from pydantic import Field

from .fields import HttpUrl
from .voices import Voices


class ChatterboxModel(Voices):
    """`url`: the repository URL of its files; `files`: their names, downloaded to `<dir>/<model>/`."""

    url: HttpUrl
    files: list[str] = Field(min_length=1)
