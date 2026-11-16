"""Field types shared by the schema classes: paths with `~` expanded, existing files, URLs, secrets and the
`models:` catalogue of a provider."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, TypeVar

import pydantic
from pydantic import AfterValidator, BeforeValidator, SecretStr, TypeAdapter, UrlConstraints

M = TypeVar("M")


def expand(value: object) -> object:
    """`value` with `~` expanded when it is a string or a path; other values pass to the type check."""
    return Path(value).expanduser() if isinstance(value, (str, Path)) and str(value).strip() else value


def existing(path: Path) -> Path:
    if not path.is_file():
        raise ValueError(f"file {path} does not exist")
    return path


def absolute(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError(f"'{path}' is not an absolute path or a path starting with ~")
    return path


def url_of(kind: type) -> AfterValidator:
    """A check that a string is a URL of pydantic type `kind`; the string is kept as written (pydantic's URL types
    add a trailing `/`)."""
    adapter = TypeAdapter(kind)

    def check(value: str) -> str:
        adapter.validate_python(value)
        return value

    return AfterValidator(check)


def non_empty(value: object) -> object:
    """A secret stripped of whitespace; an empty one is an error (leave the key out instead)."""
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError("is empty; set a value or remove the key")
    return value


def null_entries(value: Any) -> Any:
    """A `models:` map whose entries hold only comments: each null entry is an empty mapping."""
    return {k: {} if v is None else v for k, v in value.items()} if isinstance(value, dict) else value


# A path; `~` is expanded.
UserPath = Annotated[Path, BeforeValidator(expand)]
# An absolute path, or one starting with `~` (expanded).
AbsolutePath = Annotated[Path, BeforeValidator(expand), AfterValidator(absolute)]
# A path that must name an existing file; `~` is expanded before the check.
ExistingFile = Annotated[Path, BeforeValidator(expand), AfterValidator(existing)]
# An http:// or https:// URL.
HttpUrl = Annotated[str, url_of(pydantic.HttpUrl)]
# The schemes of a proxy URL that the HTTP clients of the model layer take.
PROXY_SCHEMES = ("http", "https", "socks4", "socks5", "socks5h")
# A proxy URL: one of PROXY_SCHEMES and a host.
ProxyUrl = Annotated[str, url_of(Annotated[pydantic.AnyUrl, UrlConstraints(allowed_schemes=list(PROXY_SCHEMES),
                                                                           host_required=True)])]
# A key or token; not shown in reprs and errors.
Secret = Annotated[SecretStr, BeforeValidator(non_empty)]
# `providers.<p>.models`: the entry of each model by its name; a null entry is an empty one.
Catalogue = Annotated[dict[str, M], BeforeValidator(null_entries)]
