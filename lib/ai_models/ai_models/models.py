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

Remote clients trust certifi's roots plus EXTRA_CA_CERT (`tls`). Every key, endpoint and
API version a client gets comes from config.yaml: a missing required one is a
`ConfigError`, and a provider that needs no key gets `NO_KEY`, so the client never
falls back to its environment variables (`plugin_settings.Plugin.load` also removes them).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import config
from .errors import ConfigError

OLLAMA_URL = "http://localhost:11434/v1"
OPENAI_URL = "https://api.openai.com/v1"
# The key of a provider that needs none, so the client library does not read one from its environment
# variable; servers that check no key ignore it.
NO_KEY = "api-key-not-set"
# Kinds whose service always needs a key; `openai` needs one without `base_url` (the OpenAI API).
KEY_KINDS = ("openrouter", "azure", "google")
# The settings of a Vertex provider that select Google Cloud credentials in place of `api_key`.
VERTEX_CREDENTIALS = ("project", "location", "credentials")
CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DEFAULT_TIMEOUT_SECONDS = 600.0
CONNECT_TIMEOUT_SECONDS = 10.0
# The Pydantic-AI model prefix of a kind, where it differs; `openai` uses Chat Completions,
# which every OpenAI-compatible server has.
CHAT_PREFIX = {"openai": "openai-chat"}


def http_client(spec: dict[str, Any]):
    """An `httpx2.AsyncClient` with the provider's `timeout` (seconds) and the TLS context of `tls`."""
    import httpx2

    from .tls import ssl_verify

    timeout = float(spec.get("timeout", DEFAULT_TIMEOUT_SECONDS))
    return httpx2.AsyncClient(verify=ssl_verify(), timeout=httpx2.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS))


def base_url(spec: dict[str, Any]) -> str | None:
    """The provider's `base_url`; Ollama's default for an `ollama` provider without one."""
    return spec.get("base_url") or (OLLAMA_URL if spec["kind"] == "ollama" else None)


def uses_cloud_credentials(spec: dict[str, Any]) -> bool:
    """A Vertex provider without `api_key` that names `project`, `location` or `credentials`."""
    return (spec["kind"] == "google" and bool(spec.get("vertex")) and config.api_key(spec) is None
            and any(spec.get(k) for k in VERTEX_CREDENTIALS))


def provider_key(spec: dict[str, Any], name: str) -> str:
    """The `api_key` of provider `name`; `NO_KEY` for a provider that needs none, `ConfigError` when one that
    needs a key has none."""
    k = config.api_key(spec)
    if k is not None:
        return k
    if spec["kind"] in KEY_KINDS or (spec["kind"] == "openai" and not spec.get("base_url")):
        alt = " (or `project`, `location`, `credentials` for Google Cloud credentials)" if spec.get("vertex") else ""
        raise ConfigError(f"provider {name!r} of kind {spec['kind']} needs `api_key`{alt} in {config.path()}")
    return NO_KEY


def vertex_provider(spec: dict[str, Any], url: str | None, http):
    """The GoogleCloudProvider of a Vertex provider with Google Cloud credentials: the service account of
    `credentials` (its project unless `project` is set), else Application Default Credentials."""
    from pydantic_ai.providers.google_cloud import GoogleCloudProvider

    creds, project = None, spec.get("project")
    if path := spec.get("credentials"):
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(str(Path(path).expanduser()),
                                                                      scopes=[CLOUD_SCOPE])
        project = project or creds.project_id
    return GoogleCloudProvider(credentials=creds, project=project, location=spec.get("location"), base_url=url,
                               http_client=http)


def provider(name: str):
    """The Pydantic-AI provider of provider `name` in the config."""
    spec = config.provider(name)
    kind, url = spec["kind"], base_url(spec)
    if kind == "azure":
        url = config.required(spec, "base_url", name)
        config.required(spec, "api_version", name)
    if uses_cloud_credentials(spec):
        return vertex_provider(spec, url, http_client(spec))
    key, http = provider_key(spec, name), http_client(spec)
    if kind == "ollama":
        from pydantic_ai.providers.ollama import OllamaProvider

        return OllamaProvider(base_url=url, api_key=key, http_client=http)
    if kind == "openrouter":
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        return OpenRouterProvider(api_key=key, http_client=http)
    if kind == "openai":
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIProvider(base_url=url or OPENAI_URL, api_key=key, http_client=http)
    if kind == "azure":
        from pydantic_ai.providers.azure import AzureProvider

        return AzureProvider(azure_endpoint=url, api_version=spec.get("api_version"), api_key=key, http_client=http)
    if kind == "google":
        if spec.get("vertex"):
            from pydantic_ai.providers.google_cloud import GoogleCloudProvider

            return GoogleCloudProvider(api_key=key, base_url=url, http_client=http)
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleProvider(api_key=key, base_url=url, http_client=http)
    raise ConfigError(f"provider {name!r} of kind {kind!r} has no API models; kinds: ollama, openrouter, "
                      "openai, azure, google")


def kind(model_id: str) -> str:
    """The provider kind of `model_id`."""
    return config.provider(config.split_id(model_id)[0])["kind"]


def chat_model(model: str | None = None, *, task: str = "chat"):
    """The Pydantic-AI chat model of `model` (a model id), else of `task` (`chat`, `vision`, ...)."""
    from pydantic_ai.models import infer_model

    model_id = config.resolve(model, task)
    name, bare = config.split_id(model_id)
    k = kind(model_id)
    return infer_model(f"{CHAT_PREFIX.get(k, k)}:{bare}", provider_factory=lambda _: provider(name))


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
