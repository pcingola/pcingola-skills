"""Forwarding to Ollama (docs/model_server.md, Routing and Ollama) with the tiny Ollama models of tests/config.yaml:
chat, streamed chat and embeddings through the `openai` SDK, `/v1/systemone`, `/api/*` and the merged model list."""

import time

from tests.prereq import OLLAMA, require_ollama
from tests.settings_env import task_model

CHAT = task_model("chat").split(":", 1)[1]
EMBED = task_model("embed").split(":", 1)[1]
SYSTEM1 = task_model("system1").split(":", 1)[1]


def test_chat_and_streamed_chat(running):
    """A chat completion of an Ollama tag (its colon included) goes to Ollama unchanged; a streamed one comes back
    chunk by chunk as Ollama sends it, ending with a finish reason, and its scheduler slot ends with the stream."""
    require_ollama("chat")
    messages = [{"role": "user", "content": "Say hi."}]
    out = running.client.chat.completions.create(model=CHAT, messages=messages, max_tokens=8)
    assert out.model == CHAT and out.choices[0].message.content
    chunks = list(running.client.chat.completions.create(model=CHAT, messages=messages, max_tokens=8, stream=True))
    assert len(chunks) > 1 and chunks[-1].choices[0].finish_reason is not None
    deadline = time.monotonic() + 2.0  # the slot ends after the last chunk is sent
    while running.server.scheduler.state().running:
        assert time.monotonic() < deadline, running.server.scheduler.state()
        time.sleep(0.05)


def test_embeddings(running):
    """`embeddings.create` of an Ollama embedding model answers one vector per input."""
    require_ollama("embed")
    out = running.client.embeddings.create(model=EMBED, input=["a cat", "a dog"])
    assert len(out.data) == 2 and len(out.data[0].embedding) == len(out.data[1].embedding) > 0


def test_systemone_and_api_paths(running):
    """`/v1/systemone` reaches Ollama unchanged: Pydantic-AI's System-1 model, pointed at the server, gets a yes/no
    probability. `/api/tags` answers the models Ollama itself lists."""
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


def test_model_list_merges_local_and_ollama(running):
    """`models.list` holds the local models, with their kind, role and entry, and Ollama's; `models.retrieve`
    answers a local model's object, and Ollama's answer for an Ollama tag."""
    require_ollama("chat")
    models = {m.id: m for m in running.client.models.list()}
    video = models[task_model("video")]
    assert video.role == "video" and video.entry["max_frames"] > 0
    assert CHAT in models and models[CHAT].owned_by != "local"
    assert running.client.models.retrieve(task_model("presenter")).entry["buckets"]
    assert running.client.models.retrieve(CHAT).id == CHAT
