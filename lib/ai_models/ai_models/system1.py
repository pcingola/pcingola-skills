"""System-1 models: Pydantic-AI's `SystemOneModel` on `POST <base_url>/v1/systemone`
(Ollama: http://localhost:11434/v1/systemone). Any provider with a `base_url`
serves it; its key goes as a bearer token (`models.provider_key`).

The questions and answers are Pydantic-AI's types (`pydantic_ai.models.decision`:
`ChoiceQuestion`, `NoulQuestion`, `ScoreQuestion`, `DecisionRequest`, ...).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from plugin_settings import RemoteProvider

from . import config
from .errors import ConfigError, explained
from .models import base_url, http_client, provider_key


def system1_model(model: str | None = None, *, task: str = "system1"):
    """The `SystemOneModel` of `model` (a model id), else of `task`."""
    from pydantic_ai.models.system_one import SystemOneModel
    from pydantic_ai.providers.system_one import SystemOneProvider

    name, bare = config.split_id(config.resolve(model, task))
    spec = config.provider(name)
    url = base_url(spec)
    if not url or not isinstance(spec, RemoteProvider):
        raise ConfigError(f"provider {name!r} has no base_url for System-1 models")
    return SystemOneModel(bare, provider=SystemOneProvider(base_url=url, api_key=provider_key(spec),
                                                           http_client=http_client(spec)))


async def adecide(state: str, questions: Mapping, *, model: str | None = None, temperature: float | None = None,
                  timeout: float | None = None):
    """The `DecisionResponse` of `model` (else `tasks.system1`) for `state` and `questions`
    ({id: question}). `timeout` (seconds) replaces the provider's `timeout` for this request."""
    from pydantic_ai.models.decision import DecisionRequest

    model_id = config.resolve(model, "system1")
    m = system1_model(model_id)
    settings = {k: v for k, v in (("temperature", temperature), ("timeout", timeout)) if v is not None}
    with explained(model_id):
        return await m.decide(DecisionRequest(state=state, questions=dict(questions)), settings)


def decide(state: str, questions: Mapping, **kwargs):
    """`adecide` from synchronous code."""
    return asyncio.run(adecide(state, questions, **kwargs))
