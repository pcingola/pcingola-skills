"""A provider of kind ollama: an Ollama server (`base_url`, default http://localhost:11434/v1)."""

from __future__ import annotations

from typing import Literal

from .base import RemoteProvider


class OllamaProvider(RemoteProvider):
    kind: Literal["ollama"]
