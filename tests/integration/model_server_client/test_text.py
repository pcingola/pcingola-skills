"""Chat, embeddings and System-1 of `ai_models` through a provider of kind `openai` at the model server, which
forwards them to Ollama (docs/model_server.md, Ollama); a test fails when Ollama lacks the model."""

from pydantic_ai.models.decision import NoulQuestion

from ai_models import models, system1
from tests.prereq import require_ollama


def test_chat(client):
    """`models.agent` on tasks.chat, a model of the server's provider, answers text from Ollama's model."""
    require_ollama("chat")
    result = models.agent(model_settings={"max_tokens": 8}).run_sync("Reply with the word OK.")
    assert result.output.strip()


def test_embeddings(client):
    """`models.embedder` on tasks.embed, through the server, embeds each document."""
    require_ollama("embed")
    result = models.embedder().embed_documents_sync(["a cat", "a dog"])
    assert len(result.embeddings) == 2 and len(result.embeddings[0]) > 100


def test_system1(client):
    """`system1.decide` on tasks.system1 posts to `<base_url>/systemone` of the server, which passes it to Ollama,
    and returns a yes/no probability."""
    require_ollama("system1")
    r = system1.decide("The sky is blue.", {"q": NoulQuestion(instructions="Does the text name a color?")})
    assert 0 <= r.answers["q"].noul <= 1
