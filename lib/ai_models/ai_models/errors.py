"""Errors of the layer, and short messages for the common failures of a model call."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from plugin_settings import ProviderKind, RemoteProvider


class AIModelsError(Exception):
    """Every error this package raises."""


class ConfigError(AIModelsError):
    """`config.yaml` is missing, malformed, or lacks a task, provider or key."""


class LocalMemoryError(AIModelsError):
    """A local model does not fit in the free memory (`local.memory_error`)."""


class Cancelled(AIModelsError):
    """An in-process model call stopped because its cancel signal was set (`cancel`)."""


# HTTP statuses of a request the server refuses for its credentials.
REFUSED = (401, 403)


@contextmanager
def explained(model_id: str) -> Iterator[None]:
    """Run a model call for `model_id` and replace a missing Ollama model, an
    unreachable server, or a refusal (401, 403) by a provider without `api_key`
    by an `AIModelsError` that says what to do."""
    from . import config
    from .models import uses_cloud_credentials

    try:
        yield
    except AIModelsError:
        raise
    except Exception as e:
        name, model = config.split_id(model_id)
        spec = config.provider(name)
        kind = spec.kind
        status = (getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
                  or getattr(e, "code", None))
        text = str(e).lower()
        if (status in REFUSED and isinstance(spec, RemoteProvider) and spec.api_key is None
                and not uses_cloud_credentials(spec)):
            raise AIModelsError(f"{model_id}: provider {name!r} refused the request ({status}) and has no key; "
                                f"set providers.{name}.api_key in {config.path()}") from e
        if kind == ProviderKind.OLLAMA and status == 404 and "not found" in text:
            raise AIModelsError(f"{model_id}: the model is not pulled; run `ollama pull {model}`") from e
        if "connect" in type(e).__name__.lower() or "connection" in text:
            raise AIModelsError(f"{model_id}: cannot reach provider {name!r} ({e})") from e
        raise
