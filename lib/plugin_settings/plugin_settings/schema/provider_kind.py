"""The `kind` of a provider: which client or local runtime serves its models, and the groups of kinds the code
branches on. Every grouping of kinds is here."""

from __future__ import annotations

from enum import StrEnum


class ProviderKind(StrEnum):
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    AZURE = "azure"
    GOOGLE = "google"
    DIFFUSERS = "diffusers"
    FISH = "fish"
    KOKORO = "kokoro"
    CHATTERBOX = "chatterbox"
    TORCHAUDIO = "torchaudio"


# The kinds served by an OpenAI-style client (chat, images, speech).
OPENAI_KINDS = frozenset({ProviderKind.OLLAMA, ProviderKind.OPENROUTER, ProviderKind.OPENAI, ProviderKind.AZURE})
# The kinds of a remote API, with a Pydantic-AI provider (`ai_models.models.provider`).
API_KINDS = OPENAI_KINDS | {ProviderKind.GOOGLE}
# The kinds that run their models locally; each model of one needs its entry in `models`.
LOCAL_KINDS = frozenset({ProviderKind.DIFFUSERS, ProviderKind.FISH, ProviderKind.KOKORO,
                         ProviderKind.CHATTERBOX, ProviderKind.TORCHAUDIO})
# The kinds whose image models take image request limits (`image:` of the model entry).
IMAGE_LIMIT_KINDS = OPENAI_KINDS | {ProviderKind.DIFFUSERS}
# The kinds with speech models.
SPEECH_KINDS = API_KINDS | {ProviderKind.FISH, ProviderKind.KOKORO, ProviderKind.CHATTERBOX}
