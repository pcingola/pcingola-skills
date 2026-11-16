"""The fields of the remote (API) kinds."""

from __future__ import annotations

from ..fields import HttpUrl, Secret
from .timed import TimedProvider


class RemoteProvider(TimedProvider):
    """A provider of an API: its key and endpoint."""

    api_key: Secret | None = None
    base_url: HttpUrl | None = None

    def key(self) -> str | None:
        """The `api_key` value, None when the provider has none."""
        return None if self.api_key is None else self.api_key.get_secret_value()
