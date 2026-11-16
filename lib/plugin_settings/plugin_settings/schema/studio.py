"""`studio:`: the Studio projects directory and the default "Made by" of a new film."""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator

from .base import Strict

DEFAULT_DIR = "~/Documents/Studio"


class StudioSettings(Strict):
    """`dir`: absolute or starting with `~`; `author`: names, whitespace collapsed, empty ones dropped."""

    dir: str = DEFAULT_DIR
    author: list[str] = []

    @field_validator("dir")
    @classmethod
    def _absolute(cls, v: str) -> str:
        if not Path(v).expanduser().is_absolute():
            raise ValueError(f"{v!r} is not an absolute path or a path starting with ~")
        return v

    @field_validator("author")
    @classmethod
    def _names(cls, v: list[str]) -> list[str]:
        return [n for n in (" ".join(s.split()) for s in v) if n]

    def path(self) -> Path:
        """`dir` with `~` expanded."""
        return Path(self.dir).expanduser()
