"""Fields of a request: sizes, multipart form fields and files, and the request fields outside an OpenAI params
type, which go to the model as more arguments."""

from __future__ import annotations

import json
from typing import Any

from pydantic import TypeAdapter, ValidationError
from starlette.datastructures import FormData, UploadFile

from .server_error import ServerError


def parse_size(size: object) -> tuple[int, int] | None:
    """(width, height) of `WxH`; None for None or `auto`; `ServerError` 400 otherwise."""
    if size is None or size == "auto":
        return None
    w, sep, h = str(size).lower().partition("x")
    if not sep or not w.isdigit() or not h.isdigit() or int(w) < 1 or int(h) < 1:
        raise ServerError(400, f"size {size!r} is not WxH (for example 512x512) or auto", param="size")
    return int(w), int(h)


def form_value(value: str) -> Any:
    """A multipart text field as JSON when it parses (a number, a boolean, a list), else as the text."""
    try:
        return json.loads(value)
    except ValueError:
        return value


def text_fields(form: FormData) -> dict[str, Any]:
    """The text fields of `form` (`form_value`); a field sent twice keeps the last value."""
    return {k: form_value(v) for k, v in form.multi_items() if isinstance(v, str)}


async def files(form: FormData, *names: str) -> list[bytes]:
    """The bytes of the files of `form` under any of `names`, in order (`image` and `image[]` for several)."""
    return [await v.read() for k, v in form.multi_items() if k in names and isinstance(v, UploadFile)]


async def one_file(form: FormData, name: str, *, required: bool) -> bytes | None:
    """The bytes of the file `name` of `form`; `ServerError` 400 when it is missing and `required`."""
    got = await files(form, name)
    if not got and required:
        raise ServerError(400, f"the request has no file `{name}`", param=name)
    return got[0] if got else None


def checked(params_type: Any, body: dict[str, Any]) -> dict[str, Any]:
    """`body` validated against the TypedDict `params_type` (an `openai.types` params type, or one of this package);
    `ServerError` 400 naming the first wrong field. The fields outside the type are kept."""
    try:
        TypeAdapter(params_type).validate_python(body)
    except ValidationError as e:
        err = e.errors()[0]
        field = ".".join(str(p) for p in err["loc"])
        raise ServerError(400, f"{field}: {err['msg']}", param=field or None) from None
    return body


def extras(params_type: Any, body: dict[str, Any], *known: str) -> dict[str, Any]:
    """The fields of `body` that are neither keys of `params_type` nor in `known`: the more arguments a client sends
    in `extra_body`."""
    keys = set(_keys(params_type)) | set(known)
    return {k: v for k, v in body.items() if k not in keys}


def _keys(params_type: Any) -> set[str]:
    """The keys of a TypedDict, or of each member of a union of TypedDicts."""
    members = getattr(params_type, "__args__", None) or (params_type,)
    return {k for m in members for k in getattr(m, "__annotations__", {})}
