"""The base class of every schema class: unknown keys are errors, and a loaded config is read-only."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    """A section or entry of config.yaml: a key the class does not define fails validation with its path."""

    model_config = ConfigDict(extra="forbid", frozen=True)
