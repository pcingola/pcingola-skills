"""Models of a model server (`lib/model_server`): a provider of kind `openai` with a `base_url` that is a model
server's `/v1` reaches the server's local models, which describe themselves at `GET <base_url>/models/{id}` with
`kind` (the server provider's kind), `role` and `entry` (the server's config entry of the model, every key with
its default), and a speech model's `voices`.

`served(model_id)` reads that answer once per process and validates `entry` as the schema class of its kind and role
(`ROLE_CLASSES` for diffusers, `ENTRY_CLASSES` for the others), so the client's config holds no copy of a model's
attributes. A model the server does not describe (an Ollama model the server forwards, a 404, an OpenAI-compatible
server that is not a model server) is None. The calls with no `openai` SDK method (music, alignments, the
presenter's second file) and the video jobs go through `client(model_id)`, the `AsyncOpenAI` client of the
Pydantic-AI provider, as speech does; `answered` turns the server's error answers into `AIModelsError`.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from plugin_settings import (ROLE_CLASSES, ChatterboxModel, DiffusersRole, FishModel, KokoroModel, ProviderKind, Task,
                             TorchaudioModel)
from pydantic import ValidationError

from . import config
from .errors import AIModelsError, ConfigError, explained
from .served_model import ServedModel

# The entry class of each local kind other than diffusers.
ENTRY_CLASSES = {ProviderKind.FISH: FishModel, ProviderKind.KOKORO: KokoroModel,
                 ProviderKind.CHATTERBOX: ChatterboxModel, ProviderKind.TORCHAUDIO: TorchaudioModel}
_cache: dict[tuple[str, str], ServedModel | None] = {}
_lock = threading.Lock()


def server_url(model_id: str) -> str | None:
    """The `base_url` of the provider of `model_id` when it is of kind `openai` and has one, else None."""
    spec = config.provider(config.split_id(model_id)[0])
    return spec.base_url if spec.kind == ProviderKind.OPENAI else None


def parse(model_id: str, bare: str, data: Any) -> ServedModel | None:
    """The `ServedModel` of a `GET /models/{id}` answer `data`; None for an answer without `kind`, `role` and
    `entry` (a model the server forwards); `AIModelsError` for an entry its class refuses."""
    if not isinstance(data, dict) or not {"kind", "role", "entry"} <= data.keys():
        return None
    try:
        kind = ProviderKind(data["kind"])
        cls = ROLE_CLASSES[DiffusersRole(data["role"])] if kind == ProviderKind.DIFFUSERS else ENTRY_CLASSES[kind]
        entry = cls.model_validate(data["entry"])
        role = Task(data["role"])
        voices = data.get("voices")
        if voices is not None and not (isinstance(voices, list) and all(isinstance(v, str) for v in voices)):
            raise ValueError(f"voices is not a list of names: {voices!r}")
    except (ValueError, KeyError, ValidationError) as e:
        raise AIModelsError(f"{model_id}: the model server describes the model in a form this client does not "
                            f"read ({type(e).__name__}: {str(e).splitlines()[0]})") from None
    return ServedModel(model_id, bare, kind, role, entry, voices)


def _fetch(model_id: str, url: str, bare: str) -> ServedModel | None:
    import httpx2

    from .models import CONNECT_TIMEOUT_SECONDS, provider_key
    from .tls import ssl_verify

    spec = config.provider(config.split_id(model_id)[0])
    address = f"{url.rstrip('/')}/models/{bare}"
    try:
        with httpx2.Client(verify=ssl_verify(), timeout=httpx2.Timeout(spec.timeout,
                                                                       connect=CONNECT_TIMEOUT_SECONDS)) as http:
            response = http.get(address, headers={"Authorization": f"Bearer {provider_key(spec)}"})
    except httpx2.HTTPError as e:
        raise AIModelsError(f"{model_id}: cannot reach provider {config.split_id(model_id)[0]!r} at {address} "
                            f"({e})") from e
    if response.status_code != 200:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    return parse(model_id, bare, data)


def served(model_id: str, *, quiet: bool = False) -> ServedModel | None:
    """The local model `model_id` of a model server (its provider of kind `openai` with a `base_url`), read once per
    process; None for a provider of another kind or a model the server does not describe. A server that does not
    answer is an `AIModelsError`, or None when `quiet` (for a caller whose model call reports the failure itself);
    that answer is not kept."""
    url = server_url(model_id)
    if url is None:
        return None
    bare = config.split_id(model_id)[1]
    key = (url, bare)
    with _lock:
        if key not in _cache:
            try:
                _cache[key] = _fetch(model_id, url, bare)
            except AIModelsError:
                if quiet:
                    return None
                raise
        return _cache[key]


def require(model_id: str, role: Task) -> ServedModel:
    """The served model `model_id` of `role`; `ConfigError` when its server describes no such model, or one of
    another role."""
    m = served(model_id)
    if m is None:
        raise ConfigError(f"{model_id}: the server at {server_url(model_id)} has no local model "
                          f"{config.split_id(model_id)[1]!r} (GET /models/{{id}}); a {role} model of an openai "
                          "provider must be a local model of a model server")
    if m.role != role:
        raise ConfigError(f"{model_id} is a {m.role} model of its server, not a {role} model")
    return m


def kind(model_id: str) -> str:
    """The kind `model_id` runs as: the server provider's kind of a served model, else its provider's kind (also
    when the server does not answer: the model call then reports it)."""
    m = served(model_id, quiet=True)
    return m.kind if m is not None else config.provider(config.split_id(model_id)[0]).kind


def client(model_id: str):
    """The `AsyncOpenAI` client of the Pydantic-AI provider of `model_id`."""
    from .models import provider

    return provider(config.split_id(model_id)[0]).client


@contextmanager
def answered(model_id: str) -> Iterator[None]:
    """Run a call to the server of `model_id`: `explained`, and an error answer of the server (an
    `openai.APIStatusError`) becomes an `AIModelsError` with its status and message."""
    import openai

    with explained(model_id):
        try:
            yield
        except openai.APIStatusError as e:
            body = e.body if isinstance(e.body, dict) else {}
            message = body.get("message") or (body.get("error") or {}).get("message") or e.message
            raise AIModelsError(f"{model_id}: the server refused the request ({e.status_code}): {message}") from e
