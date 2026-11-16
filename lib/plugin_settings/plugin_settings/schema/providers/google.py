"""A provider of kind google: Gemini API, or Vertex AI with `vertex: true`. Vertex takes `api_key`, or Google Cloud
credentials: `credentials` (a service-account JSON file), else Application Default Credentials with `project` and
`location`."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from ..fields import Catalogue, ExistingFile
from ..google_model import GoogleModel
from .base import RemoteProvider


class GoogleProvider(RemoteProvider):
    kind: Literal["google"]
    vertex: bool = False
    credentials: ExistingFile | None = None
    project: str | None = None
    location: str | None = None
    models: Catalogue[GoogleModel] = {}

    def uses_cloud_credentials(self) -> bool:
        """A Vertex provider without `api_key` that names `project`, `location` or `credentials`."""
        return self.vertex and self.api_key is None and any((self.project, self.location, self.credentials))

    @model_validator(mode="after")
    def _key_or_credentials(self) -> GoogleProvider:
        if self.api_key is None and not self.uses_cloud_credentials():
            raise ValueError("api_key: required for kind google" + (
                " (or credentials, project or location for Google Cloud credentials)" if self.vertex else ""))
        if not self.vertex and any((self.credentials, self.project, self.location)):
            raise ValueError("credentials, project and location need vertex: true")
        return self
