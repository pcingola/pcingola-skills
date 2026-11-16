"""`Config`: the whole of config.yaml, validated at load."""

from __future__ import annotations

from typing import Any

from pydantic import field_validator, model_validator

from ..old_keys import old_key_errors
from .base import Strict
from .brand import BrandSettings
from .diffusers_model import DiffusersModel
from .huggingface import HuggingFace
from .model_id import ModelId, split_id
from .network import Network
from .provider_kind import ProviderKind
from .providers import Provider
from .remote_model import RemoteModel
from .studio import StudioSettings
from .task import Task
from .voiceover import VoiceoverSettings


class Config(Strict):
    """The sections of config.yaml. A section that is empty or holds only comments (null) has its defaults."""

    providers: dict[str, Provider] = {}
    tasks: dict[Task, ModelId] = {}
    network: Network = Network()
    huggingface: HuggingFace = HuggingFace()
    brand: BrandSettings = BrandSettings()
    studio: StudioSettings = StudioSettings()
    voiceover: VoiceoverSettings = VoiceoverSettings()

    @model_validator(mode="before")
    @classmethod
    def _old_keys(cls, data: Any) -> Any:
        if isinstance(data, dict) and (errors := old_key_errors(data)):
            raise ValueError("\n".join(errors))
        return data

    @field_validator("*", mode="before")
    @classmethod
    def _null_section(cls, v: Any) -> Any:
        return {} if v is None else v

    @model_validator(mode="after")
    def _references(self) -> Config:
        errors = []
        for task, model_id in self.tasks.items():
            name, model = split_id(model_id)
            p = self.providers.get(name)
            if p is None:
                errors.append(f"tasks.{task}: provider {name!r} is not in providers")
            elif p.kind == ProviderKind.DIFFUSERS and model not in p.models:
                errors.append(f"tasks.{task}: model {model!r} is not in providers.{name}.models")
        if errors:
            raise ValueError("\n".join(errors))
        return self

    def provider(self, name: str) -> Provider | None:
        """`providers.<name>`, None when absent."""
        return self.providers.get(name)

    def model_entry(self, model_id: str) -> RemoteModel | DiffusersModel | None:
        """`providers.<p>.models.<m>` of `model_id`, None when the provider or the entry is absent."""
        name, model = split_id(model_id)
        p = self.providers.get(name)
        return None if p is None else p.models.get(model) if hasattr(p, "models") else None

    def task_model(self, task: str) -> str | None:
        """The model id of `tasks.<task>`, None when unset."""
        return self.tasks.get(task)
