"""Chat, streamed chat, embeddings, System-1 and audio input through the deployed server, which forwards them to its
Ollama (docs/model_server.md, Ollama), with the `ai_models` functions on the tasks of tests/server/config.yaml."""

import asyncio

import httpx2
import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.models.decision import NoulQuestion

from ai_models import models, speech, system1
from tests.server.conftest import SERVER, TIMEOUT_SECONDS, ollama_tag, server_root, task

pytestmark = pytest.mark.timeout(TIMEOUT_SECONDS)
SETTINGS = {"max_tokens": 8}


def test_chat():
    """`models.agent` on tasks.chat answers text from the server's Ollama model."""
    result = models.agent(model_settings=SETTINGS).run_sync("Reply with the word OK.")
    assert result.output.strip()


def test_streamed_chat():
    """A streamed run of `models.agent` gets the answer in more than one text delta, as the server passes Ollama's
    server-sent events through."""
    async def deltas() -> list[str]:
        async with models.agent(model_settings={"max_tokens": 16}).run_stream("Count from one to five.") as run:
            return [d async for d in run.stream_text(delta=True, debounce_by=None)]

    got = asyncio.run(deltas())
    assert len(got) > 1 and "".join(got).strip()


def test_embeddings():
    """`models.embedder` on tasks.embed embeds each document, through the server, as vectors of one length."""
    result = models.embedder().embed_documents_sync(["a cat", "a dog"])
    assert len(result.embeddings) == 2 and len(result.embeddings[0]) == len(result.embeddings[1]) > 100


def test_system1():
    """`system1.decide` on tasks.system1 posts to `<base_url>/systemone` of the server, which passes it to Ollama,
    and returns a yes/no probability."""
    r = system1.decide("The sky is blue.", {"q": NoulQuestion(instructions="Does the text name a color?")})
    assert 0 <= r.answers["q"].noul <= 1


def test_audio_input():
    """`models.agent` on tasks.audio takes a WAV recording (the server's Kokoro speech) as `input_audio` and
    answers text."""
    wav = speech.speak("The heart pumps blood.")
    result = models.agent(task="audio", model_settings={"max_tokens": 32}).run_sync(
        [BinaryContent(data=wav, media_type="audio/wav"), "Write down the words you hear."])
    assert result.output.strip()


def test_ollama_keep_alive_is_visible():
    """`GET /api/ps` goes to Ollama at once (no model in the request) and lists the chat model after a chat, with
    the `expires_at` of Ollama's keep-alive. The server's in-process models have no such listing."""
    models.agent(model_settings=SETTINGS).run_sync("Say hi.")
    running = httpx2.get(f"{server_root()}/api/ps", timeout=10).json()["models"]
    tag = ollama_tag(task("chat"))
    held = {m["name"]: m for m in running}
    assert tag in held, f"/api/ps lists {sorted(held)}, not {tag}"
    assert held[tag]["expires_at"]
