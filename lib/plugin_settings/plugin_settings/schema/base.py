"""The base class of every schema class: unknown keys are errors, a loaded config is read-only, and a key whose
value is null takes its default when the default is a section, mapping or list."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class Strict(BaseModel):
    """A section or entry of config.yaml: a key the class does not define fails validation with its path. A key
    that holds only comments parses as null; when its field defaults to a section, mapping or list, it takes that
    default (an emptied section or `models:` map), else null is validated as given (an optional key is None, a
    required one fails)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _null_as_default(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        empty = [k for k, v in data.items() if v is None and k in cls.model_fields
                 and isinstance(cls.model_fields[k].get_default(call_default_factory=True), (dict, list, BaseModel))]
        return {**data, **{k: cls.model_fields[k].get_default(call_default_factory=True) for k in empty}}
