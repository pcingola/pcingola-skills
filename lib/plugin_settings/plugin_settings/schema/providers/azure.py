"""A provider of kind azure: Azure OpenAI at `base_url` (the resource or a gateway), with `api_version`."""

from __future__ import annotations

from typing import Literal

from ..fields import HttpUrl, Secret
from .openai_kind import OpenAIKindProvider


class AzureProvider(OpenAIKindProvider):
    kind: Literal["azure"]
    base_url: HttpUrl
    api_version: str
    api_key: Secret
