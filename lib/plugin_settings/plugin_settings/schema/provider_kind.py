"""The `kind` of a provider: which client or local runtime serves its models."""

from __future__ import annotations

from enum import StrEnum


class ProviderKind(StrEnum):
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    AZURE = "azure"
    GOOGLE = "google"
    DIFFUSERS = "diffusers"
    VLLM_OMNI = "vllm-omni"
    KOKORO = "kokoro"
    CHATTERBOX = "chatterbox"
    TORCHAUDIO = "torchaudio"


# The kinds served by an OpenAI-style client (chat, images, speech).
OPENAI_KINDS = (ProviderKind.OLLAMA, ProviderKind.OPENROUTER, ProviderKind.OPENAI, ProviderKind.AZURE)
