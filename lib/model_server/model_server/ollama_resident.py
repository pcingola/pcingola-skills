"""`OllamaResident`: a model Ollama holds in memory (`GET /api/ps`)."""

from __future__ import annotations

from pydantic import BaseModel


class OllamaResident(BaseModel):
    """Its name (the Ollama tag) and bytes."""

    name: str
    size: int = 0
