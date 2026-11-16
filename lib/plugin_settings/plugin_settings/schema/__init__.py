"""The schema of config.yaml: one class per section, provider kind and model entry (`Config` is the root)."""

from .base import Strict
from .brand import BrandSettings
from .chatterbox_model import ChatterboxModel
from .config import Config
from .diffusers_entry import ROLE_CLASSES, DiffusersEntry
from .diffusers_image_limits import DiffusersImageLimits
from .diffusers_image_model import DiffusersImageModel
from .diffusers_model import DiffusersModel
from .diffusers_music_model import DiffusersMusicModel
from .diffusers_presenter_model import DiffusersPresenterModel
from .diffusers_role import DiffusersRole
from .diffusers_video_model import DiffusersVideoModel
from .google_model import GoogleModel
from .huggingface import HuggingFace
from .image_limits import ImageLimits
from .kokoro_model import KokoroModel
from .model_id import ModelId, split_id
from .network import Network
from .openai_image_limits import OpenAIImageLimits
from .openai_model import OpenAIModel
from .provider_kind import API_KINDS, IMAGE_LIMIT_KINDS, LOCAL_KINDS, OPENAI_KINDS, SPEECH_KINDS, ProviderKind
from .providers import (OLLAMA_URL, AzureProvider, ChatterboxProvider, DiffusersProvider, GoogleProvider,
                        KokoroProvider, OllamaProvider, OpenAIKindProvider, OpenAIProvider, OpenRouterProvider,
                        OwnEnvironment, Provider, RemoteProvider, TimedProvider, TorchaudioProvider, VllmOmniProvider,
                        WeightsDir)
from .quality import Quality
from .studio import StudioSettings
from .task import Task
from .task_kinds import TASK_KINDS, TASK_ROLES
from .torchaudio_model import TorchaudioModel
from .voiceover import VoiceoverSettings
from .voices import Voices
from .vllm_omni_model import VllmOmniModel

__all__ = [
    "API_KINDS", "IMAGE_LIMIT_KINDS", "LOCAL_KINDS", "OLLAMA_URL", "OPENAI_KINDS", "ROLE_CLASSES", "SPEECH_KINDS",
    "TASK_KINDS", "TASK_ROLES", "AzureProvider", "BrandSettings", "ChatterboxModel", "ChatterboxProvider", "Config",
    "DiffusersEntry", "DiffusersImageLimits", "DiffusersImageModel", "DiffusersModel", "DiffusersMusicModel",
    "DiffusersPresenterModel", "DiffusersProvider", "DiffusersRole", "DiffusersVideoModel", "GoogleModel",
    "GoogleProvider", "HuggingFace", "ImageLimits", "KokoroModel", "KokoroProvider", "ModelId", "Network",
    "OllamaProvider", "OpenAIImageLimits", "OpenAIKindProvider", "OpenAIModel", "OpenAIProvider",
    "OpenRouterProvider", "OwnEnvironment", "Provider", "ProviderKind", "Quality", "RemoteProvider", "Strict",
    "StudioSettings", "Task", "TimedProvider", "TorchaudioModel", "TorchaudioProvider", "VllmOmniModel",
    "VllmOmniProvider", "VoiceoverSettings", "Voices", "WeightsDir", "split_id",
]
