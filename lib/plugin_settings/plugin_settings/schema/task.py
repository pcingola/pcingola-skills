"""The tasks of `tasks:`: what a skill asks a model for."""

from __future__ import annotations

from enum import StrEnum


class Task(StrEnum):
    CHAT = "chat"
    VISION = "vision"
    SYSTEM1 = "system1"
    EMBED = "embed"
    IMAGE = "image"
    IMAGE_EDIT = "image_edit"
    IMAGE_BEST = "image_best"
    IMAGE_MULTI_REF = "image_multi_ref"
    SPEECH = "speech"
    ALIGN = "align"
    MUSIC = "music"
    AUDIO = "audio"
    VIDEO = "video"
    PRESENTER = "presenter"
    FILM_CRITIC = "film_critic"
