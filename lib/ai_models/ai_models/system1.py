"""System-1 models: Pydantic-AI's `SystemOneModel` on `POST <base_url>/v1/systemone`
(Ollama: http://localhost:11434/v1/systemone). Any provider with a `base_url`
serves it; its key goes as a bearer token (`models.provider_key`).

The questions and answers are Pydantic-AI's types (`pydantic_ai.models.decision`:
`ChoiceQuestion`, `NoulQuestion`, `ScoreQuestion`, `DecisionRequest`, ...).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from . import config
from .errors import explained
from .models import http_client, provider_key


def system1_model(model: str | None = None, *, task: str = "system1"):
    """The `SystemOneModel` of `model` (a model id), else of `task`; `config.resolve` refuses a provider without
    `base_url`."""
    from pydantic_ai.models.system_one import SystemOneModel
    from pydantic_ai.providers.system_one import SystemOneProvider

    name, bare = config.split_id(config.resolve(model, task))
    spec = config.provider(name)
    return SystemOneModel(bare, provider=SystemOneProvider(base_url=spec.base_url, api_key=provider_key(spec),
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
