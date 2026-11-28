"""`Route`: where a request runs."""

from __future__ import annotations

from enum import StrEnum


class Route(StrEnum):
    LOCAL = "local"  # in process, with the ai_models code
    OLLAMA = "ollama"  # forwarded to Ollama, the model named by its Ollama tag
