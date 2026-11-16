"""A provider of kind openai: the OpenAI API (`api_key` required), or any OpenAI-compatible server (`base_url`)."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from .openai_kind import OpenAIKindProvider


class OpenAIProvider(OpenAIKindProvider):
    kind: Literal["openai"]

    @model_validator(mode="after")
    def _key_or_url(self) -> OpenAIProvider:
        if self.api_key is None and self.base_url is None:
            raise ValueError("api_key: required for kind openai without base_url (the OpenAI API)")
        return self
