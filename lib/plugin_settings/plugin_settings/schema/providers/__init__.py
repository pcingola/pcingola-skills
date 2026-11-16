"""The provider classes, one per kind, and `Provider`: the union picked by `kind`."""

from __future__ import annotations

from typing import Annotated, Union

from pydantic import Field

from .azure import AzureProvider
from .base import RemoteProvider, TimedProvider
from .chatterbox import ChatterboxProvider
from .diffusers import DiffusersProvider
from .google import GoogleProvider
from .kokoro import KokoroProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .openrouter import OpenRouterProvider
from .torchaudio import TorchaudioProvider
from .vllm_omni import VllmOmniProvider

Provider = Annotated[Union[OllamaProvider, OpenRouterProvider, OpenAIProvider, AzureProvider, GoogleProvider,
                           DiffusersProvider, KokoroProvider, TorchaudioProvider, ChatterboxProvider,
                           VllmOmniProvider], Field(discriminator="kind")]

__all__ = ["AzureProvider", "ChatterboxProvider", "DiffusersProvider", "GoogleProvider", "KokoroProvider",
           "OllamaProvider", "OpenAIProvider", "OpenRouterProvider", "Provider", "RemoteProvider", "TimedProvider",
           "TorchaudioProvider", "VllmOmniProvider"]
