"""`model_server:`: the settings of the OpenAI-compatible model server (`lib/model_server`)."""

from __future__ import annotations

from pydantic import Field, NonNegativeFloat, PositiveFloat

from .base import Strict
from .fields import AbsolutePath, HttpUrl

OLLAMA_LOCAL_URL = "http://127.0.0.1:11434"


class ModelServerSettings(Strict):
    """`host`, `port`: the address the server listens on; `keep_alive`: the seconds an in-process model stays
    loaded after its last request (0: unloaded after each request); `ollama_url`: the Ollama server the requests
    for other models go to, without `/v1`; `timeout`: the seconds a forwarded request may take; `video_ttl`: the
    seconds a finished video job and its file are kept; `weights_dir`: the weights directory of a kokoro,
    chatterbox or torchaudio provider without `dir` (None: such a provider needs `dir`)."""

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    keep_alive: NonNegativeFloat = 300.0
    ollama_url: HttpUrl = OLLAMA_LOCAL_URL
    timeout: PositiveFloat = 600.0
    video_ttl: PositiveFloat = 3600.0
    weights_dir: AbsolutePath | None = None
