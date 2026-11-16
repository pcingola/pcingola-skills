"""The provider classes, one per kind, and `Provider`: the union picked by `kind`."""

from __future__ import annotations

from typing import Annotated, Union

from pydantic import Field

from .azure import AzureProvider
from .base import RemoteProvider
from .chatterbox import ChatterboxProvider
from .diffusers import DiffusersProvider
from .google import GoogleProvider
from .kokoro import KokoroProvider
from .ollama import OLLAMA_URL, OllamaProvider
from .openai import OpenAIProvider
from .openai_kind import OpenAIKindProvider
from .openrouter import OpenRouterProvider
from .own_environment import OwnEnvironment
from .timed import TimedProvider
from .torchaudio import TorchaudioProvider
from .vllm_omni import VllmOmniProvider
from .weights_dir import WeightsDir

Provider = Annotated[Union[OllamaProvider, OpenRouterProvider, OpenAIProvider, AzureProvider, GoogleProvider,
                           DiffusersProvider, KokoroProvider, TorchaudioProvider, ChatterboxProvider,
                           VllmOmniProvider], Field(discriminator="kind")]

__all__ = ["OLLAMA_URL", "AzureProvider", "ChatterboxProvider", "DiffusersProvider", "GoogleProvider",
           "KokoroProvider", "OllamaProvider", "OpenAIKindProvider", "OpenAIProvider", "OpenRouterProvider",
           "OwnEnvironment", "Provider", "RemoteProvider", "TimedProvider", "TorchaudioProvider", "VllmOmniProvider",
           "WeightsDir"]
