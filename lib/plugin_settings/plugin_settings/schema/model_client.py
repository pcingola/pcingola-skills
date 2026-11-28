"""`model_client:`: the settings of the command-line client of a model server (`lib/model_client`)."""

from __future__ import annotations

from .base import Strict


class ModelClientSettings(Strict):
    """`provider`: the provider whose `base_url` is the client's default server, a provider of kind `openai` with a
    `base_url` (`Config` checks it); None: the server at `http://localhost:<model_server.port>/v1`."""

    provider: str | None = None
