"""Real calls to Ollama on this machine with the models of tests/config.yaml; a test fails when Ollama lacks the
model."""

import pytest
from pydantic_ai.models.decision import NoulQuestion

from ai_models import AIModelsError, config, models, system1
from ai_models.errors import explained
from tests.prereq import require_ollama
from tests.settings_env import TEST_CONFIG


@pytest.fixture(autouse=True)
def _config():
    config.use(TEST_CONFIG)
    yield
    config.use(None)


def test_chat():
    """`models.agent` without a model id runs tasks.chat on Ollama and returns text."""
    require_ollama("chat")
    result = models.agent(model_settings={"max_tokens": 8}).run_sync("Reply with the word OK.")
    assert result.output.strip()


def test_embeddings():
    """`models.embedder` without a model id embeds each document with tasks.embed on Ollama."""
    require_ollama("embed")
    result = models.embedder().embed_documents_sync(["a cat", "a dog"])
    assert len(result.embeddings) == 2 and len(result.embeddings[0]) > 100


def test_system1():
    """`system1.decide` runs tasks.system1 on Ollama and returns a yes/no probability."""
    require_ollama("system1")
    r = system1.decide("The sky is blue.", {"q": NoulQuestion(instructions="Does the text name a color?")})
    assert 0 <= r.answers["q"].noul <= 1


def test_model_not_pulled_says_ollama_pull():
    """A model Ollama does not hold raises an AIModelsError that tells the user to run `ollama pull`."""
    require_ollama()
    with pytest.raises(AIModelsError, match="ollama pull no-such-model:1b"), explained("ollama:no-such-model:1b"):
        models.agent("ollama:no-such-model:1b").run_sync("hi")
