"""Scheduling of the deployed server (docs/model_server.md, Scheduling): requests to several models, and parallel
requests to one model, sent at once through the `ai_models` async functions, all complete."""

import asyncio

import pytest

from ai_models import models, speech
from tests.server.conftest import TIMEOUT_SECONDS, model
from tests.wav import read

pytestmark = pytest.mark.timeout(TIMEOUT_SECONDS)
TEXT = "The heart pumps blood."
PARALLEL = 4


def chat(prompt: str):
    """The awaitable answer of tasks.chat to `prompt`, in at most 8 tokens."""
    return models.agent(model_settings={"max_tokens": 8}).run(prompt)


def test_models_requested_at_once_all_complete():
    """A Kokoro request, a Chatterbox request (two in-process models, which run one after the other) and an Ollama
    chat sent at once all complete: one waits in the queue for the other, and none fails."""
    async def at_once():
        return await asyncio.gather(speech.aspeak(TEXT), speech.aspeak(TEXT, model=model("chatterbox-turbo")),
                                    chat("Say hi."))

    kokoro, chatterbox, answer = asyncio.run(at_once())
    assert read(kokoro).seconds > 0.3 and read(chatterbox).seconds > 0.2 and answer.output.strip()


def test_parallel_requests_to_one_model_all_complete():
    """PARALLEL chats of one Ollama model (a model the server runs in parallel) and PARALLEL Kokoro requests (one at
    a time) sent at once all complete."""
    async def at_once():
        return await asyncio.gather(*(chat(f"Say {i}.") for i in range(PARALLEL)),
                                    *(speech.aspeak(f"{TEXT} {i}.") for i in range(PARALLEL)))

    out = asyncio.run(at_once())
    assert all(a.output.strip() for a in out[:PARALLEL])
    assert all(read(w).seconds > 0.3 for w in out[PARALLEL:])
