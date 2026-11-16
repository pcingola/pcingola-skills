"""`config.yaml`: the providers, the model of each task (`tasks`) and the attributes of each model
(`providers.<p>.models`), read as the typed `Config` of `plugin_settings`.

The file is the settings file of `plugin_settings` (`config_file`): `$SKILLS_CONFIG`, else
`<config dir>/plugins/data/config.yaml`. The schema checks every key at load (required keys per provider kind, a task
naming a missing provider, a diffusers task model without an entry), so the functions here only look entries up. A
model id is `<provider name>:<model>`; the first colon splits it.
"""

from __future__ import annotations

from pathlib import Path

import plugin_settings
from plugin_settings import (Config, ConfigFileError, DiffusersModel, ImageLimits, Provider, ProviderKind,
                             RemoteModel)
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
    """`model` when given, else the model id of `task`."""
    return model or model_for(task)


def provider(name: str) -> Provider:
    """The settings of provider `name` (`providers.<name>`)."""
    spec = load().provider(name)
    if spec is None:
        raise ConfigError(f"no provider {name!r}: add `providers.{name}` with a `kind` to {path()}")
    return spec


def model_entry(model_id: str) -> RemoteModel | DiffusersModel | None:
    """The attributes of `model_id` (`providers.<p>.models.<m>`), None when the provider has no entry for it;
    `ConfigError` when the provider is missing."""
    name, _ = split_id(model_id)
    provider(name)
    return load().model_entry(model_id)


def diffusers_model(model_id: str) -> DiffusersModel:
    """The entry of the local model `model_id` (`providers.<p>.models.<m>` of a diffusers provider)."""
    name, model = split_id(model_id)
    spec = provider(name)
    if spec.kind != ProviderKind.DIFFUSERS:
        raise ConfigError(f"provider {name!r} of kind {spec.kind!r} has no diffusers models")
    entry = spec.models.get(model)
    if entry is None:
        raise ConfigError(f"no diffusers model {model!r}: add `providers.{name}.models.{model}` with a `repo` "
                          f"to {path()}")
    return entry


def image_limits(model_id: str) -> ImageLimits:
    """The image request limits of `model_id` (`providers.<p>.models.<m>.image`); `ConfigError` with the fix when
    the model has none."""
    name, model = split_id(model_id)
    entry = model_entry(model_id)
    limits = getattr(entry, "image", None)
    if limits is None:
        more = "min_edge" if provider(name).kind == ProviderKind.DIFFUSERS else "min_pixels, max_pixels"
        raise ConfigError(f"{model_id} has no image limits: add providers.{name}.models.{model}.image with max_edge "
                          f"(and {more}) to {plugin_settings.display(path())}")
    return limits
