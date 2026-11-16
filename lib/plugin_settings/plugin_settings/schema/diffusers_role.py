"""The role of a diffusers model entry: what its pipeline makes, and so which keys it takes."""

from __future__ import annotations

from enum import StrEnum


class DiffusersRole(StrEnum):
    IMAGE = "image"
    MUSIC = "music"
    VIDEO = "video"
    PRESENTER = "presenter"

    def noun(self) -> str:
        """"an image model", "a music model", ... for messages."""
        return f"{'an' if self.value[0] in 'aeiou' else 'a'} {self.value} model"
