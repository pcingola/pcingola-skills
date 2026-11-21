"""`POST /v1/images/generations` (JSON) and `POST /v1/images/edits` (multipart) on a local diffusers image model
(`ai_models.local.DiffusersImageModel`).

Both answer `openai.types.ImagesResponse` with one `b64_json` PNG per image. `size` (`WxH`) sets the width and
height, else the pipeline's default; `n` images come from one pipeline call (`num_images_per_prompt`). The fields
outside the OpenAI params type (`seed`, any pipeline argument) go to the pipeline (`extra_body`). An edit takes one
or more reference images (`image`, or `image[]` for several) and an optional `mask` (PNG, transparent where the image
is repainted), which runs the model's `inpaint` pipeline on the first image.
"""

from __future__ import annotations

import base64
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from openai.types import Image, ImagesResponse
from openai.types.image_edit_params import ImageEditParamsNonStreaming
from openai.types.image_generate_params import ImageGenerateParamsNonStreaming

from .forms import checked, extras, files, form_value, one_file, parse_size, text_fields
from .model_role import ModelRole
from .requests import json_body, server_of
from .server_error import ServerError

router = APIRouter()


def check_options(body: dict[str, Any]) -> None:
    """`ServerError` 400 for an option a local image model does not serve: a URL answer, a format other than PNG,
    a stream."""
    if body.get("response_format") not in (None, "b64_json"):
        raise ServerError(400, "local image models answer b64_json only", param="response_format")
    if body.get("output_format") not in (None, "png"):
        raise ServerError(400, "local image models make PNG only", param="output_format")
    if body.get("stream"):
        raise ServerError(400, "local image models do not stream", param="stream")


def image_settings(size: tuple[int, int] | None, n: object, extra: dict[str, Any]) -> dict[str, Any]:
    """The Pydantic-AI image settings: `dimensions` and the pipeline arguments (`extra_body`)."""
    if not isinstance(n, int) or n < 1:
        raise ServerError(400, f"n must be a positive integer, not {n!r}", param="n")
    extra = dict(extra)
    if n > 1:
        extra["num_images_per_prompt"] = n
    return {**({"dimensions": size} if size else {}), "extra_body": extra}


def images_response(result: Any, size: tuple[int, int] | None) -> JSONResponse:
    """The `ImagesResponse` of a Pydantic-AI `ImageGenerationResult`."""
    data = [Image(b64_json=base64.b64encode(g.content.data).decode()) for g in result.images]
    out = ImagesResponse(created=int(time.time()), data=data, output_format="png",
                         size=f"{size[0]}x{size[1]}" if size else None)
    return JSONResponse(out.model_dump(mode="json", exclude_none=True))


@router.post("/v1/images/generations")
async def generations(request: Request) -> JSONResponse:
    from ai_models.local import DiffusersImageModel

    body = checked(ImageGenerateParamsNonStreaming, await json_body(request))
    srv = server_of(request)
    ref = srv.ref(body.get("model"), ModelRole.IMAGE)
    check_options(body)
    size = parse_size(body.get("size"))
    settings = image_settings(size, body.get("n") or 1, extras(ImageGenerateParamsNonStreaming, body))
    async with srv.running(ref):
        result = await DiffusersImageModel(ref.id).generate(body["prompt"], settings=settings)
    return images_response(result, size)


@router.post("/v1/images/edits")
async def edits(request: Request) -> JSONResponse:
    from ai_models.local import DiffusersImageModel
    from pydantic_ai.messages import BinaryImage

    form = await request.form()
    fields = text_fields(form)
    prompt = form.get("prompt")
    if not isinstance(prompt, str):
        raise ServerError(400, "the request has no `prompt`", param="prompt")
    srv = server_of(request)
    ref = srv.ref(form.get("model"), ModelRole.IMAGE)
    check_options(fields)
    refs = await files(form, "image", "image[]")
    if not refs:
        raise ServerError(400, "an edit needs a reference image (`image`, or `image[]` for several)", param="image")
    mask = await one_file(form, "mask", required=False)
    size = parse_size(form.get("size"))
    extra = extras(ImageEditParamsNonStreaming, fields, "image[]", "mask")
    settings = image_settings(size, form_value(str(form.get("n") or "1")), extra)
    images = [BinaryImage(data=r, media_type="image/png") for r in refs]
    async with srv.running(ref):
        result = await DiffusersImageModel(ref.id, mask=mask).generate(prompt, images=images, settings=settings)
    return images_response(result, size)
