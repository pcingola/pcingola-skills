"""A provider of kind openrouter: OpenRouter, with its key."""

from __future__ import annotations

from typing import Literal

from ..fields import Secret
from .base import RemoteProvider


class OpenRouterProvider(RemoteProvider):
    kind: Literal["openrouter"]
    api_key: Secret
