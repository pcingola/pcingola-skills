"""`GET /v1/models` and `GET /v1/models/{id}`: the local models (`catalog`) and Ollama's.

The list is `{"object": "list", "data": [...]}`: the local models first, then the `data` of Ollama's `/v1/models`
(none when Ollama does not answer). One model: a local model's object, else Ollama's answer for the id, forwarded. A speech model's object also has
`voices` (`ai_models.speech.voices`: the entry's `voices`, else a Kokoro model's voices from its voices file, else the
default voice), read in a worker thread because a Kokoro voices file may be downloaded first.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from .catalog import local_models, model_object
from .model_role import ModelRole
from .requests import server_of

router = APIRouter()


@router.get("/v1/models")
async def list_models(request: Request) -> JSONResponse:
    srv = server_of(request)
    local = [m.model_dump(mode="json") for m in local_models(srv.config())]
    return JSONResponse({"object": "list", "data": local + await srv.ollama.models()})


@router.get("/v1/models/{model_id:path}")
async def get_model(model_id: str, request: Request) -> Response:
    srv = server_of(request)
    ref = srv.ref(model_id)
    if ref.local:
        voices = None
        if ref.role == ModelRole.SPEECH:
            from ai_models import speech

            voices = await asyncio.to_thread(speech.voices, ref.id, srv.settings.weights_dir)
        return JSONResponse(model_object(ref, voices).model_dump(mode="json"))
    return await srv.ollama.forward(request, b"")
