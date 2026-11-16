"""Fields every provider kind except diffusers shares, and those of the remote (API) kinds."""

from __future__ import annotations

from pydantic import PositiveFloat

from ..base import Strict
from ..fields import HttpUrl, Secret
from ..remote_model import RemoteModel

DEFAULT_TIMEOUT = 600.0


class TimedProvider(Strict):
    """A provider that takes `timeout`: seconds per request."""

    timeout: PositiveFloat = DEFAULT_TIMEOUT


class RemoteProvider(TimedProvider):
    """A provider of an API: its key, endpoint, speech voices and per-model attributes (`models`)."""

    api_key: Secret | None = None
    base_url: HttpUrl | None = None
    voice: str | None = None
    voices: list[str] | None = None
    models: dict[str, RemoteModel] = {}

    def key(self) -> str | None:
        """The `api_key` value, None when the provider has none."""
        return None if self.api_key is None else self.api_key.get_secret_value()
