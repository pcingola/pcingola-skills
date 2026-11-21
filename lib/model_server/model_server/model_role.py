"""`ModelRole`: what a local model makes, and so which endpoint serves it."""

from __future__ import annotations

from enum import StrEnum

from plugin_settings import DiffusersModel, ProviderKind


class ModelRole(StrEnum):
    IMAGE = "image"
    MUSIC = "music"
    VIDEO = "video"
    PRESENTER = "presenter"
    SPEECH = "speech"
    ALIGN = "align"

    @classmethod
    def of(cls, kind: ProviderKind, entry: object) -> ModelRole:
        """The role of a model entry of a local provider of `kind`: a diffusers entry's role, speech for the speech
        kinds, align for torchaudio."""
        if isinstance(entry, DiffusersModel):
            return cls(entry.role.value)
        return cls.ALIGN if kind == ProviderKind.TORCHAUDIO else cls.SPEECH
