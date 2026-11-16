"""A model id, `<provider>:<model>`: the first colon splits it, so `ollama:d3:4b` is the Ollama tag `d3:4b`."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BeforeValidator


def split_id(model_id: str) -> tuple[str, str]:
    """(provider name, model) of `model_id`; `ValueError` when either part is empty."""
    name, sep, model = model_id.partition(":")
    if not sep or not name or not model:
        raise ValueError(f"model id {model_id!r} is not <provider>:<model>")
    return name, model


def _given(value: object) -> object:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("is empty; give a model or remove the key")
    return value


def _check(model_id: str) -> str:
    split_id(model_id)
    return model_id


ModelId = Annotated[str, BeforeValidator(_given), AfterValidator(_check)]
