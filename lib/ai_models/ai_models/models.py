"""Pydantic-AI providers and models from `config.yaml`: chat, vision and embeddings.

Provider kinds and the Pydantic-AI provider each builds:

    ollama      OllamaProvider (`base_url`, default http://localhost:11434/v1)
    openrouter  OpenRouterProvider (`api_key`)
    openai      OpenAIProvider (`base_url` for any OpenAI-compatible server; `api_key`
                required without `base_url`, the OpenAI API)
    azure       AzureProvider (`base_url` is the Azure endpoint, `api_version`, `api_key`)
    google      GoogleProvider (`api_key`), or GoogleCloudProvider (Vertex) with `vertex: true`:
                `api_key`, else Google Cloud credentials (`project`, `location`,
                `credentials`: a service-account JSON file, else Application Default Credentials)
    diffusers   local images and music in process (`local`), no provider
    vllm-omni, kokoro, chatterbox   local speech (`speech`), no provider
    torchaudio  forced alignment (`align`), no provider

Remote clients trust certifi's roots plus `network.extra_ca_cert` (`tls`). Every key, endpoint and API version a
client gets comes from config.yaml: the schema refuses a provider that lacks a required one at load, and a provider
that needs no key gets `NO_KEY`, so the client never falls back to its environment variables
(`plugin_settings.Plugin.load` also removes them).
"""

from __future__ import annotations

from typing import Any

from plugin_settings import GoogleProvider, Provider, ProviderKind, RemoteProvider, TimedProvider

from . import config

OPENAI_URL = "https://api.openai.com/v1"
# The key of a provider that needs none, so the client library does not read one from its environment
# variable; servers that check no key ignore it.
NO_KEY = "api-key-not-set"
CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
CONNECT_TIMEOUT_SECONDS = 10.0
# The Pydantic-AI model prefix of a kind, where it differs; `openai` uses Chat Completions,
# which every OpenAI-compatible server has.
CHAT_PREFIX = {ProviderKind.OPENAI: "openai-chat"}


def http_client(spec: TimedProvider):
    """An `httpx2.AsyncClient` with the provider's `timeout` (seconds) and the TLS context of `tls`."""
    import httpx2

    from .tls import ssl_verify

    return httpx2.AsyncClient(verify=ssl_verify(), timeout=httpx2.Timeout(spec.timeout,
                                                                         connect=CONNECT_TIMEOUT_SECONDS))


def uses_cloud_credentials(spec: Provider) -> bool:
    """A Vertex provider without `api_key` that names `project`, `location` or `credentials`."""
    return isinstance(spec, GoogleProvider) and spec.uses_cloud_credentials()


def provider_key(spec: RemoteProvider) -> str:
    """The `api_key` of a provider; `NO_KEY` for one without (the schema requires it where the service needs it)."""
    return spec.key() or NO_KEY


def vertex_provider(spec: GoogleProvider, url: str | None, http):
    """The GoogleCloudProvider of a Vertex provider with Google Cloud credentials: the service account of
    `credentials` (its project unless `project` is set), else Application Default Credentials."""
    from pydantic_ai.providers.google_cloud import GoogleCloudProvider

    creds, project = None, spec.project
    if spec.credentials is not None:
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(str(spec.credentials), scopes=[CLOUD_SCOPE])
        project = project or creds.project_id
    return GoogleCloudProvider(credentials=creds, project=project, location=spec.location, base_url=url,
                               http_client=http)


def provider(name: str):
    """The Pydantic-AI provider of provider `name` in the config, a provider of a kind in `API_KINDS`: callers
    reach it with a model id that `config.resolve` checked against its task's kinds."""
    spec = config.provider(name)
    kind = spec.kind
    url = spec.base_url
    if uses_cloud_credentials(spec):
        return vertex_provider(spec, url, http_client(spec))
    key, http = provider_key(spec), http_client(spec)
    if kind == ProviderKind.OLLAMA:
        from pydantic_ai.providers.ollama import OllamaProvider

        return OllamaProvider(base_url=url, api_key=key, http_client=http)
    if kind == ProviderKind.OPENROUTER:
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        return OpenRouterProvider(api_key=key, http_client=http)
    if kind == ProviderKind.OPENAI:
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIProvider(base_url=url or OPENAI_URL, api_key=key, http_client=http)
    if kind == ProviderKind.AZURE:
        from pydantic_ai.providers.azure import AzureProvider

        return AzureProvider(azure_endpoint=url, api_version=spec.api_version, api_key=key, http_client=http)
    if spec.vertex:
        from pydantic_ai.providers.google_cloud import GoogleCloudProvider

        return GoogleCloudProvider(api_key=key, base_url=url, http_client=http)
    from pydantic_ai.providers.google import GoogleProvider as PydanticGoogleProvider

    return PydanticGoogleProvider(api_key=key, base_url=url, http_client=http)


def kind(model_id: str) -> str:
    """The provider kind of `model_id`."""
    return config.provider(config.split_id(model_id)[0]).kind


def chat_model(model: str | None = None, *, task: str = "chat"):
    """The Pydantic-AI chat model of `model` (a model id), else of `task` (`chat`, `vision`, ...)."""
    from pydantic_ai.models import infer_model

    model_id = config.resolve(model, task)
    name, bare = config.split_id(model_id)
    k = kind(model_id)
    return infer_model(f"{CHAT_PREFIX.get(k, str(k))}:{bare}", provider_factory=lambda _: provider(name))


def agent(model: str | None = None, *, task: str = "chat", **kwargs: Any):
    """A Pydantic-AI `Agent` on `chat_model(model, task=task)`; `kwargs` go to `Agent`."""
    from pydantic_ai import Agent

    return Agent(chat_model(model, task=task), **kwargs)


def embedder(model: str | None = None, *, task: str = "embed"):
    """A Pydantic-AI `Embedder` for `model`, else for `task`."""
    from pydantic_ai.embeddings import Embedder, infer_embedding_model

    model_id = config.resolve(model, task)
    name, bare = config.split_id(model_id)
    return Embedder(infer_embedding_model(f"{kind(model_id)}:{bare}", provider_factory=lambda _: provider(name)))
