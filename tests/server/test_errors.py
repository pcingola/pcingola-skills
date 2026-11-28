"""Error answers of the deployed server (docs/model_server.md, Errors and Routing) and how the client turns them into
`ai_models` errors (`served.require`, `served.answered`)."""

import asyncio

import openai
import pytest

from ai_models import AIModelsError, ConfigError, align, served, video
from tests.media import png
from tests.server.conftest import SERVER, TEST, TIMEOUT_SECONDS, ollama_tag, task

pytestmark = pytest.mark.timeout(TIMEOUT_SECONDS)
# A model of a tiny local provider of the server that its config lacks.
UNKNOWN = f"{SERVER}:{TEST}diffusers:no-such-model"


def bare(client_id: str) -> str:
    """The server's model id of the client's model id."""
    return client_id.removeprefix(f"{SERVER}:")


def test_unknown_local_model_is_404():
    """`GET /v1/models/{id}` of a model a local provider lacks is a 404 `model_not_found`; the client reads it as a
    model the server does not describe, and a video job on it is a `ConfigError` before any job."""
    async def retrieve():
        return await served.client(task("chat")).models.retrieve(bare(UNKNOWN))

    with pytest.raises(openai.NotFoundError) as e:
        asyncio.run(retrieve())
    assert e.value.code == "model_not_found"
    assert served.served(UNKNOWN) is None
    with pytest.raises(ConfigError, match="has no local model"):
        video.animate(png(64, 64), "waves", seconds=0.3, model=UNKNOWN)


def test_model_of_another_role():
    """A speech request to the server's image model is a 400 `model_not_supported`, which `served.answered` turns
    into an `AIModelsError` with the status; the client refuses the speech model as an aligner before any
    request."""
    image = task("image")

    async def speak():
        with served.answered(image):
            await served.client(image).audio.speech.create(model=bare(image), input="Hi.", voice="default",
                                                           response_format="wav")

    with pytest.raises(AIModelsError, match=r"refused the request \(400\)") as e:
        asyncio.run(speak())
    assert isinstance(e.value.__cause__, openai.BadRequestError) and e.value.__cause__.code == "model_not_supported"
    with pytest.raises(ConfigError, match="speech model of its server"):
        align.aligner(task("speech"))


def test_local_model_on_an_ollama_path_is_404():
    """A chat completion that names a local model is a 404 `model_not_supported`: local models have their own
    endpoints."""
    speech = task("speech")

    async def chat():
        return await served.client(speech).chat.completions.create(
            model=bare(speech), messages=[{"role": "user", "content": "Hi."}], max_tokens=4)

    with pytest.raises(openai.NotFoundError) as e:
        asyncio.run(chat())
    assert e.value.code == "model_not_supported"


def test_bare_ollama_tag_is_404():
    """A chat completion that names a bare Ollama tag is a 404 `model_not_found` whose message names the server's
    id of it, `ollama:<tag>`."""
    chat_id = task("chat")

    async def chat():
        return await served.client(chat_id).chat.completions.create(
            model=ollama_tag(chat_id), messages=[{"role": "user", "content": "Hi."}], max_tokens=4)

    with pytest.raises(openai.NotFoundError) as e:
        asyncio.run(chat())
    assert e.value.code == "model_not_found" and bare(chat_id) in e.value.message
