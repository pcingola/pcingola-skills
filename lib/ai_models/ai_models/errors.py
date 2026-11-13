"""Errors of the layer, and short messages for the common failures of a model call."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


class AIModelsError(Exception):
    """Every error this package raises."""


class ConfigError(AIModelsError):
    """`config.yaml` is missing, malformed, or lacks a task, provider or key."""


@contextmanager
def explained(model_id: str) -> Iterator[None]:
    """Run a model call for `model_id` and replace a missing Ollama model or an
    unreachable server by an `AIModelsError` that says what to do."""
    from . import config

    try:
        yield
    except AIModelsError:
        raise
    except Exception as e:
        name, model = config.split_id(model_id)
        kind = config.provider(name).get("kind")
        status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
        text = str(e).lower()
        if kind == "ollama" and status == 404 and "not found" in text:
            raise AIModelsError(f"{model_id}: the model is not pulled; run `ollama pull {model}`") from e
        if "connect" in type(e).__name__.lower() or "connection" in text:
            raise AIModelsError(f"{model_id}: cannot reach provider {name!r} ({e})") from e
        raise
