"""Forwarding to Ollama (docs/model_server.md, Routing and Ollama) with the tiny Ollama models of tests/config.yaml:
chat, streamed chat and embeddings through the `openai` SDK, `/v1/systemone`, `/api/*` and the merged model list.
The server's Ollama ids are those of the tasks of tests/config.yaml, `ollama:<tag>`: its provider of kind `ollama` is
named `ollama`."""

import json
import time

import openai
import pytest

from tests.prereq import OLLAMA, require_ollama
from tests.settings_env import task_model

CHAT = task_model("chat")
EMBED = task_model("embed")
SYSTEM1 = task_model("system1")


def tag(model_id: str) -> str:
    """The Ollama tag of the server's Ollama id `model_id`."""
    return model_id.split(":", 1)[1]


def test_chat_and_streamed_chat(running):
    """A chat completion of `ollama:<tag>` goes to Ollama as the tag and answers with the id the client sent; a
    streamed one comes back chunk by chunk as Ollama sends it, each chunk with that id, ending with a finish reason,
    and its scheduler slot ends with the stream."""
    require_ollama("chat")
    messages = [{"role": "user", "content": "Say hi."}]
    out = running.client.chat.completions.create(model=CHAT, messages=messages, max_tokens=8)
    assert out.model == CHAT and out.choices[0].message.content
    chunks = list(running.client.chat.completions.create(model=CHAT, messages=messages, max_tokens=8, stream=True))
    assert len(chunks) > 1 and chunks[-1].choices[0].finish_reason is not None
    assert {c.model for c in chunks} == {CHAT}
    deadline = time.monotonic() + 2.0  # the slot ends after the last chunk is sent
    while running.server.scheduler.state().running:
        assert time.monotonic() < deadline, running.server.scheduler.state()
        time.sleep(0.05)


def test_embeddings(running):
    """`embeddings.create` of an Ollama embedding model answers one vector per input, with the client's id."""
    require_ollama("embed")
    out = running.client.embeddings.create(model=EMBED, input=["a cat", "a dog"])
    assert len(out.data) == 2 and len(out.data[0].embedding) == len(out.data[1].embedding) > 0
    assert out.model == EMBED


def test_systemone_and_api_paths(running):
    """`/v1/systemone` reaches Ollama with the tag: Pydantic-AI's System-1 model, pointed at the server, gets a
    yes/no probability. `/api/tags` answers the models Ollama itself lists, by their tags. `/api/chat` streams
    NDJSON lines, each with the client's id."""
    import asyncio

    import httpx
    from pydantic_ai.models.decision import DecisionRequest, NoulQuestion
    from pydantic_ai.models.system_one import SystemOneModel
    from pydantic_ai.providers.system_one import SystemOneProvider

    require_ollama("system1")
    model = SystemOneModel(SYSTEM1, provider=SystemOneProvider(base_url=f"{running.url}/v1", api_key="none"))
    request = DecisionRequest(state="The sky is blue.", questions={"q": NoulQuestion(instructions="Does the text "
                                                                                     "name a color?")})
    answer = asyncio.run(model.decide(request, {}))
    assert 0 <= answer.answers["q"].noul <= 1
    tags = running.http.get("/api/tags").json()["models"]
    assert {m["name"] for m in tags} == {m["name"] for m in httpx.get(f"{OLLAMA}/api/tags", timeout=5).json()["models"]}
    require_ollama("chat")
    body = {"model": CHAT, "messages": [{"role": "user", "content": "Say hi."}], "options": {"num_predict": 4}}
    with running.http.stream("POST", "/api/chat", json=body) as r:
        lines = [json.loads(line) for line in r.iter_lines() if line]
    assert r.status_code == 200 and len(lines) > 1 and lines[-1]["done"]
    assert {line["model"] for line in lines} == {CHAT}


def test_model_list_merges_local_and_ollama(running):
    """`models.list` holds the local models, with their kind, role, test marker and entry, and Ollama's as
    `ollama:<tag>` with kind `ollama` and role chat or embedding; `models.retrieve` answers a local model's object
    and an Ollama model's, a 404 for a tag Ollama lacks."""
    require_ollama("chat", "embed")
    models = {m.id: m for m in running.client.models.list()}
    video = models[task_model("video")]
    assert video.role == "video" and video.test is True and video.entry["max_frames"] > 0
    assert (models[CHAT].kind, models[CHAT].role) == ("ollama", "chat")
    assert (models[EMBED].kind, models[EMBED].role) == ("ollama", "embedding")
    assert all(m.startswith("ollama:") or m.split(":")[0] in ("diffusers", "kokoro", "chatterbox", "fish",
                                                               "torchaudio") for m in models)
    assert running.client.models.retrieve(task_model("presenter")).entry["buckets"]
    got = running.client.models.retrieve(CHAT)
    assert (got.id, got.kind, got.role) == (CHAT, "ollama", "chat")
    with pytest.raises(openai.NotFoundError) as e:
        running.client.models.retrieve("ollama:no-such-model:1b")
    assert e.value.code == "model_not_found"


def test_bare_tag_is_404_naming_the_prefixed_id(running):
    """A bare Ollama tag is a 404 `model_not_found` on every path, its message naming `ollama:<tag>`."""
    with pytest.raises(openai.NotFoundError) as e:
        running.client.chat.completions.create(model=tag(CHAT), messages=[{"role": "user", "content": "hi"}])
    assert e.value.code == "model_not_found" and CHAT in e.value.message
    with pytest.raises(openai.NotFoundError):
        running.client.models.retrieve(tag(CHAT))
