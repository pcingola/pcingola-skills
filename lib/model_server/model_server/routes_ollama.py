"""Every other path under `/v1/` and `/api/`: forwarded to Ollama (`Ollama.forward`), the answer streamed back as
Ollama sends it. The `model` of a JSON body is an Ollama model id, `<prefix>:<tag>` (`ModelRef`); Ollama gets the
body with `model` set to the tag, and the answer's JSON objects carry the id the client sent.

A request whose JSON body names a `model` runs as one request to that model: it waits for its turn in the scheduler,
idle in-process models make room for it (`Residency.begin`), and its slot ends when the answer ends, a streamed chat
included. Such a request is a job of the scheduler, of role chat or embedding (`Ollama.role`); its cancel closes
the request to Ollama (`Ollama.forward`). A request without a model (`GET /api/tags`, `GET /api/ps`) goes to Ollama at once, unchanged. A model id
of a local provider on one of these paths is an error (404): the local models have their own endpoints.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import Response

from .ollama import with_model
from .requests import server_of
from .server_error import ErrorType, ServerError

router = APIRouter()
METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"]


def body_model(body: bytes) -> object:
    """The `model` of a JSON object body, None for another body."""
    try:
        data = json.loads(body) if body else None
    except ValueError:
        return None
    return data.get("model") if isinstance(data, dict) else None


async def forward(request: Request) -> Response:
    srv = server_of(request)
    body = await request.body()
    model = body_model(body)
    if model is None:
        return await srv.ollama.forward(request, body)
    ref = srv.ref(model)
    if ref.local:
        raise ServerError(404, f"{request.url.path} does not serve the local model {ref.id}; it has its own "
                          "endpoint (docs: model_server)", ErrorType.NOT_FOUND, "model_not_supported", "model")
    body = with_model(body, ref.tag)
    job = srv.submit(ref, role=await srv.ollama.role(ref.tag))
    lease = await srv.admit(ref, job)
    try:
        return await srv.ollama.forward(request, body, lease.release, ref.id, job)
    except BaseException:
        lease.release()
        raise


router.add_api_route("/v1/{path:path}", forward, methods=METHODS, include_in_schema=False)
router.add_api_route("/api/{path:path}", forward, methods=METHODS, include_in_schema=False)
