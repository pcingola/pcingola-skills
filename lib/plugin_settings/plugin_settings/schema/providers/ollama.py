"""A provider of kind ollama: an Ollama server at `base_url`."""

from __future__ import annotations

from typing import Literal

from ..fields import HttpUrl
from .openai_kind import OpenAIKindProvider

OLLAMA_URL = "http://localhost:11434/v1"


class OllamaProvider(OpenAIKindProvider):
    kind: Literal["ollama"]
    base_url: HttpUrl = OLLAMA_URL
