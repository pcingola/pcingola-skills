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
from .fish_model import FishModel
from .google_model import GoogleModel
from .huggingface import HuggingFace
from .image_limits import ImageLimits
from .kokoro_model import KokoroModel
from .local_memory import LocalMemory
from .local_models import LocalModels
from .model_client import ModelClientSettings
from .model_server import OLLAMA_LOCAL_URL, ModelServerSettings
from .model_id import ModelId, split_id
from .network import Network
from .openai_image_limits import OpenAIImageLimits
from .openai_model import OpenAIModel
from .provider_kind import API_KINDS, IMAGE_LIMIT_KINDS, LOCAL_KINDS, OPENAI_KINDS, SPEECH_KINDS, ProviderKind
from .providers import (OLLAMA_URL, AzureProvider, ChatterboxProvider, DiffusersProvider, FishProvider,
                        GoogleProvider, KokoroProvider, OllamaProvider, OpenAIKindProvider, OpenAIProvider,
                        OpenRouterProvider, Provider, RemoteProvider, TimedProvider, TorchaudioProvider, WeightsDir)
from .quality import Quality
from .second_opinion import SecondOpinionSettings
from .studio import StudioSettings
from .task import Task
from .task_kinds import SERVER_TASKS, TASK_KINDS, TASK_ROLES
from .torchaudio_model import TorchaudioModel
from .voiceover import VoiceoverSettings
from .voices import Voices

__all__ = [
    "API_KINDS", "IMAGE_LIMIT_KINDS", "LOCAL_KINDS", "OLLAMA_LOCAL_URL", "OLLAMA_URL", "OPENAI_KINDS", "ROLE_CLASSES", "SPEECH_KINDS",
    "SERVER_TASKS", "TASK_KINDS", "TASK_ROLES", "AzureProvider", "BrandSettings", "ChatterboxModel", "ChatterboxProvider", "Config",
    "DiffusersEntry", "DiffusersImageLimits", "DiffusersImageModel", "DiffusersModel", "DiffusersMusicModel",
    "DiffusersPresenterModel", "DiffusersProvider", "DiffusersRole", "DiffusersVideoModel", "FishModel",
    "FishProvider", "GoogleModel",
    "GoogleProvider", "HuggingFace", "ImageLimits", "KokoroModel", "KokoroProvider", "LocalMemory", "LocalModels", "ModelClientSettings", "ModelId", "ModelServerSettings", "Network",
    "OllamaProvider", "OpenAIImageLimits", "OpenAIKindProvider", "OpenAIModel", "OpenAIProvider",
    "OpenRouterProvider", "Provider", "ProviderKind", "Quality", "RemoteProvider", "SecondOpinionSettings", "Strict",
    "StudioSettings", "Task", "TimedProvider", "TorchaudioModel", "TorchaudioProvider",
    "VoiceoverSettings", "Voices", "WeightsDir", "split_id",
]
