"""Real calls to Ollama on this machine; a test fails when Ollama lacks the model."""

import pytest
from pydantic_ai.models.decision import NoulQuestion

from ai_models import AIModelsError, models, system1
from ai_models.errors import explained

from .conftest import require_ollama

CHAT = "phi4-mini"
EMBED = "qwen3-embedding:8b"
SYSTEM1 = "d3:4b"


@pytest.fixture(autouse=True)
def _config(write_config):
    write_config({"providers": {"ollama": {"kind": "ollama"}},
                  "models": {"chat": f"ollama:{CHAT}", "embed": f"ollama:{EMBED}", "system1": f"ollama:{SYSTEM1}"}})


def test_chat():
    require_ollama(CHAT)
    result = models.agent(model_settings={"max_tokens": 8}).run_sync("Reply with the word OK.")
    assert result.output.strip()


def test_embeddings():
    require_ollama(EMBED)
    result = models.embedder().embed_documents_sync(["a cat", "a dog"])
    assert len(result.embeddings) == 2 and len(result.embeddings[0]) > 100


def test_system1():
    require_ollama(SYSTEM1)
    r = system1.decide("The sky is blue.", {"q": NoulQuestion(instructions="Does the text name a color?")})
    assert 0 <= r.answers["q"].noul <= 1


def test_model_not_pulled_says_ollama_pull():
    require_ollama()
    with pytest.raises(AIModelsError, match="ollama pull no-such-model:1b"), explained("ollama:no-such-model:1b"):
        models.agent("ollama:no-such-model:1b").run_sync("hi")
