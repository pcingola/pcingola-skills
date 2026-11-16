"""The schema of config.yaml: one class per section and per provider kind (`Config` is the root)."""

from .base import Strict
from .brand import BrandSettings
from .config import Config
from .diffusers_model import PRESENTER_FIELDS, VIDEO_FIELDS, DiffusersModel
from .huggingface import HuggingFace
from .image_limits import ImageLimits
from .model_id import ModelId, split_id
from .network import Network
from .provider_kind import OPENAI_KINDS, ProviderKind
from .providers import (AzureProvider, ChatterboxProvider, DiffusersProvider, GoogleProvider, KokoroProvider,
                        OllamaProvider, OpenAIProvider, OpenRouterProvider, Provider, RemoteProvider, TimedProvider,
                        TorchaudioProvider, VllmOmniProvider)
from .quality import Quality
from .remote_model import GoogleModel, RemoteModel
from .studio import StudioSettings
from .task import Task
from .voiceover import VoiceoverSettings

__all__ = [
    "OPENAI_KINDS", "PRESENTER_FIELDS", "VIDEO_FIELDS", "AzureProvider", "BrandSettings", "ChatterboxProvider",
    "Config", "DiffusersModel", "DiffusersProvider", "GoogleModel", "GoogleProvider", "HuggingFace", "ImageLimits",
    "KokoroProvider", "ModelId", "Network", "OllamaProvider", "OpenAIProvider", "OpenRouterProvider", "Provider",
    "ProviderKind", "Quality", "RemoteModel", "RemoteProvider", "Strict", "StudioSettings", "Task", "TimedProvider",
    "TorchaudioProvider", "VllmOmniProvider", "VoiceoverSettings", "split_id",
]
