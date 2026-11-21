"""`GET /v1/models` and `GET /v1/models/{id}` of the deployed server (docs/model_server.md, Models), read through the
client: the `AsyncOpenAI` client of `served.client` and `served.served`, which validates each answer's `entry` as
the schema class of its kind and role."""

import asyncio
from pathlib import Path

import plugin_settings
import pytest

from ai_models import served
from model_server.model_role import ModelRole
from tests.server.conftest import SERVER, TIMEOUT_SECONDS, TINY, local_models, model, task
from tests.settings_env import use_settings

pytestmark = pytest.mark.timeout(TIMEOUT_SECONDS)
# tests/config.yaml as written, `~` not expanded: the server's config holds its entries as they are written.
TINY_CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"


def tiny_entry(client_id: str):
    """The (provider kind, typed entry) in tests/config.yaml of the server's model `tiny_<provider>:<model>`."""
    name, bare = client_id.removeprefix(f"{SERVER}:").removeprefix(TINY).split(":", 1)
    with use_settings(TINY_CONFIG):
        spec = plugin_settings.load_config().providers[name]
    return spec.kind, spec.models[bare]


async def listed() -> dict:
    """The models of `GET /v1/models`, by id."""
    return {m.id: m async for m in served.client(task("chat")).models.list()}


def test_list_holds_every_tiny_model_with_kind_and_role():
    """`GET /v1/models` lists every tiny local model of tests/server/config.yaml with the `kind` and `role` of its
    provider in tests/config.yaml, and the Ollama models of the suite's tasks after them."""
    models = asyncio.run(listed())
    for client_id in local_models():
        kind, entry = tiny_entry(client_id)
        got = models.get(client_id.removeprefix(f"{SERVER}:"))
        assert got is not None, f"GET /v1/models lacks {client_id}"
        assert (got.kind, got.role) == (kind, ModelRole.of(kind, entry)), client_id
    for name in ("chat", "embed", "system1"):
        tag = task(name).removeprefix(f"{SERVER}:")
        assert tag in models or f"{tag}:latest" in models, f"GET /v1/models lacks the Ollama model {tag}"


@pytest.mark.parametrize("client_id", local_models())
def test_each_tiny_model_describes_itself(client_id):
    """`served.served` of each tiny local model reads `GET /v1/models/{id}`: its kind and role are those of its
    provider in tests/config.yaml, and its entry, validated by the client, equals that entry with every default
    except `memory`, which the server's config sets for its machine."""
    kind, entry = tiny_entry(client_id)
    m = served.served(client_id)
    assert m is not None, f"{client_id}: the server does not describe the model"
    assert (m.kind, m.role) == (kind, ModelRole.of(kind, entry))
    assert m.entry.model_dump(mode="json", exclude={"memory"}) == entry.model_dump(mode="json", exclude={"memory"})


def test_speech_models_list_their_voices():
    """The object of one speech model has `voices`: the Kokoro model's voices of its `langs` prefixes (from its
    voices file on the server), with its default voice; Chatterbox and Fish list their default voice."""
    kokoro = served.served(model("kokoro-v1.0-int8"))
    assert kokoro.entry.voice in kokoro.voices and "af_bella" in kokoro.voices
    assert all(v[:3] in kokoro.entry.langs for v in kokoro.voices)
    for name in ("chatterbox-turbo", "drama-3-tiny"):
        assert served.served(model(name)).voices == ["default"], name
