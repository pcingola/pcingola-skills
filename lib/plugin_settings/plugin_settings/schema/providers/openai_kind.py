"""The fields of the kinds served by an OpenAI-style client (ollama, openrouter, openai, azure)."""

from __future__ import annotations

from ..fields import Catalogue
from ..openai_model import OpenAIModel
from .base import RemoteProvider


class OpenAIKindProvider(RemoteProvider):
    """`models`: per-model attributes (image limits, voices)."""

    models: Catalogue[OpenAIModel] = {}
