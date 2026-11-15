"""`config.yaml`: the providers, the model of each task and the `diffusers` models.

The file is the settings file of `plugin_settings` (`config_file`):
`$SKILLS_CONFIG`, else `<config dir>/plugins/data/config.yaml`. A provider holds
its key in `api_key`. A model id is `<provider name>:<model>`; the first colon
splits it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import plugin_settings
from plugin_settings import ConfigFileError

from .errors import ConfigError


def use(file: str | Path | None) -> None:
    """Read the config from `file` from now on (None: back to the default)."""
    plugin_settings.use(file)


def path() -> Path:
    """The config file (`plugin_settings.config_file`)."""
    return plugin_settings.config_file()


def load() -> dict[str, Any]:
    """The parsed config file; `ConfigError` when it is missing, not YAML or not a mapping."""
    p = path()
    if not p.is_file():
        raise ConfigError(f"no config at {p}; the setup:settings skill creates it")
    try:
        return plugin_settings.read_config()
    except ConfigFileError as e:
        raise ConfigError(str(e)) from e


def split_id(model_id: str) -> tuple[str, str]:
    """(provider name, model) of `<provider>:<model>`; the first colon splits."""
    name, sep, model = model_id.partition(":")
    if not sep or not name or not model:
        raise ConfigError(f"model id {model_id!r} is not <provider>:<model>")
    return name, model


def model_for(task: str) -> str:
    """The model id of `task` (`models.<task>`)."""
    model_id = (load().get("models") or {}).get(task)
    if not model_id:
        raise ConfigError(f"no model for task {task!r}: add `models.{task}: <provider>:<model>` to {path()}")
    return str(model_id)


def resolve(model: str | None, task: str) -> str:
    """`model` when given, else the model id of `task`."""
    return model or model_for(task)


def provider(name: str) -> dict[str, Any]:
    """The settings of provider `name` (`providers.<name>`), with `kind`."""
    spec = (load().get("providers") or {}).get(name)
    if not isinstance(spec, dict) or "kind" not in spec:
        raise ConfigError(f"no provider {name!r} with a `kind` in {path()}")
    return spec


def required(spec: dict[str, Any], key: str, name: str) -> Any:
    """`key` of the settings `spec` of provider `name`; `ConfigError` when it is missing or empty."""
    if spec.get(key) in (None, ""):
        raise ConfigError(f"provider {name!r} of kind {spec.get('kind')} needs `{key}` in {path()}")
    return spec[key]


def api_key(spec: dict[str, Any]) -> str | None:
    """The provider's `api_key`, None when the entry has none; `ConfigError` when it is empty."""
    if "api_key" not in spec:
        return None
    key = str(spec.get("api_key") or "").strip()
    if not key:
        raise ConfigError(f"a provider of kind {spec.get('kind')!r} has an empty `api_key` in {path()}")
    return key


def diffusers_model(name: str) -> dict[str, Any]:
    """The settings of a local model (`diffusers.<name>`): `repo` and pipeline defaults."""
    spec = (load().get("diffusers") or {}).get(name)
    if not isinstance(spec, dict) or "repo" not in spec:
        raise ConfigError(f"no diffusers model {name!r} with a `repo` in {path()}")
    return spec
