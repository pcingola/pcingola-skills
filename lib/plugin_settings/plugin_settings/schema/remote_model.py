"""`providers.<p>.models.<m>` of a remote provider: attributes of one model id; any model id is served."""

from __future__ import annotations

from .base import Strict
from .image_limits import ImageLimits


class RemoteModel(Strict):
    """A model of an ollama, openrouter, openai or azure provider."""

    image: ImageLimits | None = None


class GoogleModel(RemoteModel):
    """A model of a google provider; `predict`: served by the Vertex predict endpoint (Lyria 2), else streamed."""

    predict: bool = False
