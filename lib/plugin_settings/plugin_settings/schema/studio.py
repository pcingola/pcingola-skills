"""`studio:`: the Studio projects directory and the default "Made by" of a new film."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator

from .base import Strict
from .fields import AbsolutePath

DEFAULT_DIR = Path("~/Documents/Studio")


class StudioSettings(Strict):
    """`dir`: absolute or starting with `~` (expanded); `author`: names, whitespace collapsed, empty ones dropped."""

    dir: AbsolutePath = Field(default_factory=DEFAULT_DIR.expanduser)
    author: list[str] = []

    @field_validator("author")
    @classmethod
    def _names(cls, v: list[str]) -> list[str]:
        return [n for n in (" ".join(s.split()) for s in v) if n]
