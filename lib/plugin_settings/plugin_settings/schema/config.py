"""`Config`: the whole of config.yaml, validated at load."""

from __future__ import annotations

from typing import Any

from pydantic import model_validator

from ..old_keys import old_key_errors
from .base import Strict
from .brand import BrandSettings
from .diffusers_model import DiffusersModel
from .huggingface import HuggingFace
from .local_models import LocalModels
from .model_client import ModelClientSettings
from .model_server import ModelServerSettings
from .model_id import ModelId, split_id
from .network import Network
from .provider_kind import LOCAL_KINDS, ProviderKind
from .providers import Provider, RemoteProvider
from .second_opinion import SecondOpinionSettings
from .studio import StudioSettings
from .task import Task
from .task_kinds import SERVER_TASKS, TASK_KINDS, TASK_ROLES
from .voiceover import VoiceoverSettings


class Config(Strict):
    """The sections of config.yaml. A section that is empty or holds only comments (null) has its defaults."""

    providers: dict[str, Provider] = {}
    tasks: dict[Task, ModelId] = {}
    network: Network = Network()
    huggingface: HuggingFace = HuggingFace()
    local_models: LocalModels = LocalModels()
    brand: BrandSettings = BrandSettings()
    studio: StudioSettings = StudioSettings()
    voiceover: VoiceoverSettings = VoiceoverSettings()
    second_opinion: SecondOpinionSettings = SecondOpinionSettings()
    model_server: ModelServerSettings = ModelServerSettings()
    model_client: ModelClientSettings = ModelClientSettings()

    @model_validator(mode="before")
    @classmethod
    def _old_keys(cls, data: Any) -> Any:
        if isinstance(data, dict) and (errors := old_key_errors(data)):
            raise ValueError("\n".join(errors))
        return data

    @model_validator(mode="after")
    def _references(self) -> Config:
        errors = [f"tasks.{task}: {e}" for task, model_id in self.tasks.items()
                  if (e := self.task_error(task, model_id))]
        if (name := self.model_client.provider) is not None and (e := self.server_error(name)):
            errors.append(f"model_client.provider: {e}")
        if errors:
            raise ValueError("\n".join(errors))
        return self

    def task_error(self, task: Task, model_id: str) -> str | None:
        """Why `model_id` cannot serve `task`, None when it can: its provider is missing, is of a kind the task does
        not take (`TASK_KINDS`), is local and has no entry for the model, or the entry is a diffusers model of
        another role (`TASK_ROLES`); a System-1 model needs a provider with a `base_url`, and so does a model of
        kind `openai` for a task of `SERVER_TASKS` (a model server's local model)."""
        name, model = split_id(model_id)
        p = self.providers.get(name)
        if p is None:
            return f"provider {name!r} is not in providers"
        if p.kind not in TASK_KINDS[task]:
            return (f"provider {name!r} is of kind {p.kind}; task {task} takes kinds "
                    + ", ".join(sorted(TASK_KINDS[task])))
        entry = p.models.get(model)
        if entry is None and p.kind in LOCAL_KINDS:
            return f"model {model!r} is not in providers.{name}.models"
        if isinstance(entry, DiffusersModel) and (role := TASK_ROLES.get(task)) and entry.role != role:
            return f"providers.{name}.models.{model} is {entry.role.noun()}; task {task} takes {role.noun()}"
        if task == Task.SYSTEM1 and isinstance(p, RemoteProvider) and p.base_url is None:
            return f"provider {name!r} has no base_url for System-1 models"
        if task in SERVER_TASKS and p.kind == ProviderKind.OPENAI and p.base_url is None:
            return (f"provider {name!r} has no base_url; task {task} takes a model of kind openai only from a "
                    "model server")
        return None

    def server_error(self, name: str) -> str | None:
        """Why provider `name` is not a model server's address, None when it is: it is missing, is not of kind
        `openai`, or has no `base_url`."""
        p = self.providers.get(name)
        if p is None:
            return f"provider {name!r} is not in providers"
        if p.kind != ProviderKind.OPENAI:
            return f"provider {name!r} is of kind {p.kind}; a model server's provider is of kind openai"
        if p.base_url is None:
            return f"provider {name!r} has no base_url"
        return None

    def provider(self, name: str) -> Provider | None:
        """`providers.<name>`, None when absent."""
        return self.providers.get(name)

    def model_entry(self, model_id: str) -> Any | None:
        """`providers.<p>.models.<m>` of `model_id` (the model class of the provider's kind), None when the
        provider or the entry is absent."""
        name, model = split_id(model_id)
        p = self.providers.get(name)
        return None if p is None else p.models.get(model)

    def task_model(self, task: str) -> str | None:
        """The model id of `tasks.<task>`, None when unset."""
        return self.tasks.get(task)
