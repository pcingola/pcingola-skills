"""The settings that libraries and child processes read from the process environment, and `export`.

`export(cfg)` sets each variable of `ENV_EXPORTS` from the config, or removes it when the config does not set it
(proxies in both cases), then removes every variable of `CLEARED_PREFIXES` and `CLEARED_KEYS`: the model client
libraries read keys, endpoints and headers from them, and every one of those comes from config.yaml. A shell
variable is never a setting."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from .schema import Config


@dataclass(frozen=True)
class EnvVar:
    """A variable `name` with its value from the config (`getter`; None: unset), also in lower case when `lower`."""

    name: str
    getter: Callable[[Config], str | None]
    lower: bool = False

    def names(self) -> tuple[str, ...]:
        return (self.name, self.name.lower()) if self.lower else (self.name,)


def _str(v: object) -> str | None:
    return None if v is None else str(v)


ENV_EXPORTS: tuple[EnvVar, ...] = (
    EnvVar("HTTP_PROXY", lambda c: c.network.http_proxy, lower=True),
    EnvVar("HTTPS_PROXY", lambda c: c.network.https_proxy, lower=True),
    EnvVar("ALL_PROXY", lambda c: c.network.all_proxy, lower=True),
    EnvVar("NO_PROXY", lambda c: ",".join(c.network.no_proxy), lower=True),
    EnvVar("SSL_CERT_FILE", lambda c: _str(c.network.ca_bundle)),
    EnvVar("NODE_EXTRA_CA_CERTS", lambda c: _str(c.network.extra_ca_cert)),
    EnvVar("HF_HOME", lambda c: _str(c.huggingface.home)),
    EnvVar("HF_TOKEN", lambda c: c.huggingface.token.get_secret_value() if c.huggingface.token else None),
)
# Variables that `export` removes: the OpenAI, Azure OpenAI, google-genai, google-auth and Pydantic-AI clients of
# ai_models read keys, endpoints, API versions, projects, credentials and extra headers from them; TLS libraries
# read trust stores; huggingface_hub reads a cache, an offline switch and a token that would replace
# `huggingface.home` and `huggingface.token`. setup:settings SKILL.md lists them for the user.
CLEARED_PREFIXES = ("OPENAI_", "AZURE_OPENAI_", "AZURE_VOICELIVE_", "OPENROUTER_", "OLLAMA_", "GOOGLE_GENAI_",
                    "GOOGLE_CLOUD_", "SYSTEM_ONE_")
CLEARED_KEYS = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_GEMINI_BASE_URL",
                "GOOGLE_VERTEX_BASE_URL", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "HF_HUB_CACHE",
                "HUGGINGFACE_HUB_CACHE", "HF_HUB_OFFLINE", "HUGGING_FACE_HUB_TOKEN")


def export(cfg: Config | None = None) -> None:
    """Make the process environment agree with `cfg` (default: `loader.config()`, which exits on an invalid file)."""
    if cfg is None:
        from .loader import config

        cfg = config()
    for var in ENV_EXPORTS:
        value = var.getter(cfg)
        for name in var.names():
            if value:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)
    for name in [n for n in os.environ if n.startswith(CLEARED_PREFIXES) or n in CLEARED_KEYS]:
        del os.environ[name]
