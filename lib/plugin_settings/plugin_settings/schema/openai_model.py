"""`providers.<p>.models.<m>` of a provider of an OpenAI kind (ollama, openrouter, openai, azure); any model id is
served, an entry only gives attributes."""

from __future__ import annotations

from .openai_image_limits import OpenAIImageLimits
from .voices import Voices


class OpenAIModel(Voices):
    """`image`: the request limits of an image model; `voice`, `voices`: those of a speech model."""

    image: OpenAIImageLimits | None = None
