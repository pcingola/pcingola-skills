"""Field types shared by the schema classes: paths with `~` expanded, existing files, URLs and secrets."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, SecretStr


def expand(value: object) -> object:
    """`value` with `~` expanded when it is a string or a path; other values pass to the type check."""
    return Path(value).expanduser() if isinstance(value, (str, Path)) and str(value).strip() else value


def existing(path: Path) -> Path:
    if not path.is_file():
        raise ValueError(f"file {path} does not exist")
    return path


def http_url(value: str) -> str:
    if not value.startswith(("http://", "https://")):
        raise ValueError(f"{value!r} is not an http:// or https:// URL")
    return value


def non_empty(value: object) -> object:
    """A secret stripped of whitespace; an empty one is an error (leave the key out instead)."""
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError("is empty; set a value or remove the key")
    return value


# A path; `~` is expanded.
UserPath = Annotated[Path, BeforeValidator(expand)]
# A path that must name an existing file; `~` is expanded before the check.
ExistingFile = Annotated[Path, BeforeValidator(expand), AfterValidator(existing)]
# An http:// or https:// URL.
HttpUrl = Annotated[str, AfterValidator(http_url)]
# A key or token; not shown in reprs and errors.
Secret = Annotated[SecretStr, BeforeValidator(non_empty)]
