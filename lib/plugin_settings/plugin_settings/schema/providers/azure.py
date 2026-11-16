"""A provider of kind azure: Azure OpenAI at `base_url` (the resource or a gateway), with `api_version`."""

from __future__ import annotations

from typing import Literal

from ..fields import HttpUrl, Secret
from .base import RemoteProvider


class AzureProvider(RemoteProvider):
    kind: Literal["azure"]
    base_url: HttpUrl
    api_version: str
    api_key: Secret
