"""The voice keys of a model entry that may be a speech model."""

from __future__ import annotations

from .base import Strict


class Voices(Strict):
    """`voice`: the default voice (None: the kind's default, `ai_models.speech.TRAITS`); `voices`: the voices
    `voiceover voices` lists (None: the model's own list, else the default voice)."""

    voice: str | None = None
    voices: list[str] | None = None
