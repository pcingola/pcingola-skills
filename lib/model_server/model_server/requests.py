"""Reading a request: the `Server` of the app and a JSON object body."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request

from .server import Server
from .server_error import ServerError


def server_of(request: Request) -> Server:
    return request.app.state.server


async def json_body(request: Request) -> dict[str, Any]:
    """The request's body as a JSON object; `ServerError` 400 otherwise."""
    try:
        body = json.loads(await request.body() or b"null")
    except ValueError as e:
        raise ServerError(400, f"the body is not JSON: {e}") from None
    if not isinstance(body, dict):
        raise ServerError(400, "the body is not a JSON object")
    return body
