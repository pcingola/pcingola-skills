"""`GET /v1/models` and `GET /v1/models/{id}`: the local models and Ollama's (`catalog`).

The list is `{"object": "list", "data": [...]}`: the local models first, then the `data` of Ollama's `/v1/models`
(none when Ollama does not answer), each with the id `<prefix>:<tag>` (`ModelRef`) and its role (`Ollama.role`).
One model: a local model's object, else the object of the Ollama model, a 404 `model_not_found` when Ollama has no
such model. A speech model's object also has
`voices` (`ai_models.speech.voices`: the entry's `voices`, else a Kokoro model's voices from its voices file, else the
default voice), read in a worker thread because a Kokoro voices file may be downloaded first.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .catalog import local_models, model_object, ollama_object
from .model_ref import not_found, ollama_prefix
from .model_role import ModelRole
from .requests import server_of

router = APIRouter()


@router.get("/v1/models")
async def list_models(request: Request) -> JSONResponse:
    srv = server_of(request)
    cfg = srv.config()
    local = [m.model_dump(mode="json") for m in local_models(cfg)]
    prefix = ollama_prefix(cfg)
    found = [m for m in await srv.ollama.models() if isinstance(m.get("id"), str)]
    roles = await asyncio.gather(*(srv.ollama.role(m["id"]) for m in found))
    ollama = [ollama_object(m, f"{prefix}:{m['id']}", role) for m, role in zip(found, roles)]
    return JSONResponse({"object": "list", "data": local + ollama})


@router.get("/v1/models/{model_id:path}")
async def get_model(model_id: str, request: Request) -> JSONResponse:
    srv = server_of(request)
    ref = srv.ref(model_id)
    if ref.local:
        voices = None
        if ref.role == ModelRole.SPEECH:
            from ai_models import speech

            voices = await asyncio.to_thread(speech.voices, ref.id, srv.settings.weights_dir)
        return JSONResponse(model_object(ref, voices).model_dump(mode="json"))
    data = await srv.ollama.model(ref.tag)
    if data is None:
        raise not_found(ref.id, f"Ollama has no model {ref.tag!r}")
    return JSONResponse(ollama_object(data, ref.id, await srv.ollama.role(ref.tag)))
