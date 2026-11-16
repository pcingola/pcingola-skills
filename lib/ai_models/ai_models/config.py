"""`config.yaml`: the providers, the model of each task (`tasks`) and the attributes of each model
(`providers.<p>.models`), read as the typed `Config` of `plugin_settings`.

The file is the settings file of `plugin_settings` (`config_file`): `$SKILLS_CONFIG`, else
`<config dir>/plugins/data/config.yaml`. The schema checks every key at load, and every `tasks.<task>` against the
provider kinds and diffusers role the task takes (`Config.task_error`); `resolve` applies the same check to a model
a caller names for a task. A model id is `<provider name>:<model>`; the first colon splits it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import plugin_settings
from plugin_settings import (IMAGE_LIMIT_KINDS, Config, ConfigFileError, DiffusersImageLimits, DiffusersImageModel,
                             DiffusersModel, DiffusersRole, OpenAIImageLimits, OpenAIModel, Provider, ProviderKind,
                             Task)
from plugin_settings import split_id as _split_id

from .errors import ConfigError


def use(file: str | Path | None) -> None:
    """Read the config from `file` from now on (None: back to the default)."""
    plugin_settings.use(file)


def path() -> Path:
    """The config file (`plugin_settings.config_file`)."""
    return plugin_settings.config_file()


def load() -> Config:
    """The validated config file; `ConfigError` when it is missing or not valid (the message of
    `ConfigFileError`, a line per problem)."""
    p = path()
    if not p.is_file():
        raise ConfigError(f"no config at {p}; the setup:settings skill creates it")
    try:
        return plugin_settings.load_config()
    except ConfigFileError as e:
        raise ConfigError(str(e)) from None


def split_id(model_id: str) -> tuple[str, str]:
    """(provider name, model) of `<provider>:<model>`; the first colon splits."""
    try:
        return _split_id(model_id)
    except ValueError as e:
        raise ConfigError(str(e)) from None


def model_for(task: str) -> str:
    """The model id of `task` (`tasks.<task>`)."""
    model_id = load().task_model(task)
    if not model_id:
        raise ConfigError(f"no model for task {task!r}: add `tasks.{task}: <provider>:<model>` to {path()}")
    return model_id


def resolve(model: str | None, task: str) -> str:
    """`model` when given, else the model id of `task`; `ConfigError` when the model cannot serve the task
    (`Config.task_error`: its provider is missing or of a kind the task does not take, or a local model has no
    entry or one of another role)."""
    if not model:
        return model_for(task)
    split_id(model)
    if error := load().task_error(Task(task), model):
        raise ConfigError(f"{model} for task {task}: {error}")
    return model


def provider(name: str) -> Provider:
    """The settings of provider `name` (`providers.<name>`)."""
    spec = load().provider(name)
    if spec is None:
        raise ConfigError(f"no provider {name!r}: add `providers.{name}` with a `kind` to {path()}")
    return spec


def model_entry(model_id: str) -> Any | None:
    """The attributes of `model_id` (`providers.<p>.models.<m>`, the model class of the provider's kind), None
    when the provider has no entry for it; `ConfigError` when the provider is missing."""
    name, model = split_id(model_id)
    return provider(name).models.get(model)


def local_entry(model_id: str) -> Any:
    """The entry of the local model `model_id` (a provider of a kind in `LOCAL_KINDS`); `ConfigError` naming the
    key to add when it has none."""
    entry = model_entry(model_id)
    if entry is None:
        name, model = split_id(model_id)
        raise ConfigError(f"no model {model!r}: add `providers.{name}.models.{model}` to {path()}")
    return entry


def diffusers_model(model_id: str, role: DiffusersRole) -> DiffusersModel:
    """The entry of the local model `model_id` (`providers.<p>.models.<m>` of a diffusers provider), an instance of
    the class of `role` (`ROLE_CLASSES`); `ConfigError` for another kind or role."""
    name, model = split_id(model_id)
    if (kind := provider(name).kind) != ProviderKind.DIFFUSERS:
        raise ConfigError(f"provider {name!r} of kind {kind!r} has no diffusers models")
    entry = local_entry(model_id)
    if entry.role != role:
        raise ConfigError(f"providers.{name}.models.{model} is {entry.role.noun()}, not {role.noun()}")
    return entry


def _limits_class(kind: str) -> type[OpenAIImageLimits | DiffusersImageLimits]:
    """The limits class of a kind of `IMAGE_LIMIT_KINDS`: diffusers, else the OpenAI kinds."""
    return DiffusersImageLimits if kind == ProviderKind.DIFFUSERS else OpenAIImageLimits


def image_limits(model_id: str, *, required: bool) -> OpenAIImageLimits | DiffusersImageLimits | None:
    """The image request limits of `model_id` (`providers.<p>.models.<m>.image`), None for a model of a kind that
    takes none (`IMAGE_LIMIT_KINDS`) or that has none. When `required`, a model of such a kind without limits is a
    `ConfigError` naming the key and its required fields."""
    name, model = split_id(model_id)
    spec = provider(name)
    if spec.kind not in IMAGE_LIMIT_KINDS:
        return None
    entry = spec.models.get(model)
    limits = entry.image if isinstance(entry, (OpenAIModel, DiffusersImageModel)) else None
    if limits is None and required:
        fields = [f for f, info in _limits_class(spec.kind).model_fields.items() if info.is_required()]
        raise ConfigError(f"{model_id} has no image limits: add providers.{name}.models.{model}.image with "
                          f"{', '.join(fields)} to {plugin_settings.display(path())}")
    return limits
