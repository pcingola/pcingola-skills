"""The Pydantic-AI object built for each provider kind. No request is sent."""

import pytest
from pydantic_ai.embeddings.google import GoogleEmbeddingModel
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.images.google import GoogleImageGenerationModel
from pydantic_ai.images.openai import OpenAIImageGenerationModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.models.system_one import SystemOneModel

from ai_models import ConfigError, images, models, system1
from ai_models.local import DiffusersImageModel

# Any value serves as a key: these tests build objects and send nothing.
KEY = "test-key"
PROVIDERS = {
    "ollama": {"kind": "ollama"},
    "router": {"kind": "openrouter", "api_key": KEY},
    "oai": {"kind": "openai", "base_url": "http://127.0.0.1:9/v1", "api_key": KEY},
    "azure": {"kind": "azure", "base_url": "https://gw.example/azure-openai", "api_version": "2025-04-01-preview",
           "api_key": KEY},
    "gg": {"kind": "google", "api_key": KEY},
    "vx": {"kind": "google", "vertex": True, "base_url": "https://gw.example/vertex", "api_key": KEY},
    "local": {"kind": "diffusers"},
}


@pytest.fixture(autouse=True)
def _config(write_config):
    write_config({"providers": PROVIDERS, "models": {"chat": "ollama:gemma4:31b", "vision": "gg:gemini-3-pro"},
                  "diffusers": {"zi": {"repo": "org/zi", "steps": 9}}})


@pytest.mark.parametrize("model_id, cls", [
    ("ollama:gemma4:31b", OllamaModel), ("router:google/gemini-3-pro", OpenRouterModel),
    ("oai:gpt-5", OpenAIChatModel), ("azure:gpt-5", OpenAIChatModel), ("gg:gemini-3-pro", GoogleModel),
    ("vx:gemini-3-pro", GoogleModel),
])
def test_chat_model_per_kind(model_id, cls):
    m = models.chat_model(model_id)
    assert type(m) is cls
    assert m.model_name == model_id.split(":", 1)[1]


def test_chat_model_of_a_task_and_its_base_url():
    m = models.chat_model()
    assert m.model_name == "gemma4:31b"
    assert m.base_url.startswith(models.OLLAMA_URL)
    assert type(models.agent(task="vision").model) is GoogleModel


def test_vertex_flag_builds_a_vertex_client():
    assert models.provider("vx").client.vertexai
    assert not models.provider("gg").client.vertexai


@pytest.mark.parametrize("model_id, cls", [
    ("ollama:qwen3-embedding:8b", OpenAIEmbeddingModel), ("oai:text-embedding-3-small", OpenAIEmbeddingModel),
    ("gg:gemini-embedding-001", GoogleEmbeddingModel),
])
def test_embedder_per_kind(model_id, cls):
    assert type(models.embedder(model_id).model) is cls


@pytest.mark.parametrize("model_id, cls", [
    ("azure:gpt-image-2", OpenAIImageGenerationModel), ("ollama:flux", OpenAIImageGenerationModel),
    ("gg:gemini-3-pro-image", GoogleImageGenerationModel), ("local:zi", DiffusersImageModel),
])
def test_image_model_per_kind(model_id, cls):
    assert type(images.image_model(model_id)) is cls


def test_mask_model_per_kind():
    assert type(images.image_model("azure:gpt-image-2", mask=b"png")) is images.MaskedOpenAIImageModel
    assert images.image_model("local:zi", mask=b"png").mask == b"png"
    with pytest.raises(ConfigError, match="mask"):
        images.image_model("gg:gemini-3-pro-image", mask=b"png")


def test_diffusers_provider_has_no_chat_model():
    with pytest.raises(ConfigError, match="diffusers"):
        models.chat_model("local:zi")


def test_system1_model_on_ollama():
    m = system1.system1_model("ollama:d3:4b")
    assert type(m) is SystemOneModel
    assert m.base_url == models.OLLAMA_URL
