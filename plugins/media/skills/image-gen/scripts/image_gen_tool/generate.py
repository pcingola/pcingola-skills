"""Image generation with `ai_models.images` (a Pydantic-AI `ImageGenerator`).

The model is `--model` (a `provider:model` id), else the model of the task
`models.task_for` picks from `--tier` (`tasks.<task>` of config.yaml): tier `fast` (the
default) takes `image_edit` for a request with reference images, else `image`;
tier `best` takes `image_best` and tier `multi-ref` takes `image_multi_ref`,
with and without reference images. `settings` maps the CLI options to the Pydantic-AI settings of the
model's provider kind:

- OpenAI kinds (`openai`, `azure`, `openrouter`, `ollama`): one request with
  `openai_n`; `--size` gives `dimensions` within the model's image limits
  (`providers.<p>.models.<m>.image`, `ImageLimits`), else `--aspect` goes as
  `aspect_ratio`; `--quality`, `--background` and a non-PNG format go when
  given. A model with `always_sized` always gets `dimensions` (default 1:1,
  1K); a model with `default_quality` gets it unless `--quality` is given. A
  mask goes with the edit.
- `google`: `google_image_config` with `--aspect` and `--size` when given,
  else the model's default (an edit keeps the reference's aspect); one
  request per image; PNG only, no transparent background.
- `diffusers` (local): `dimensions` from `models.local_size` within the
  model's image limits; for an edit only
  when `--aspect` or `--size` is given, else the pipeline keeps the first
  reference image's size. One request per image; PNG only.

Every failure is an `ImageError` with a message for the CLI.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from ai_models import config as ai_config
from ai_models import images
from ai_models.errors import AIModelsError, explained
from ai_models.models import kind as provider_kind
from plugin_settings import OPENAI_KINDS, ImageLimits, ProviderKind
from pydantic_ai.exceptions import AgentRunError, ContentFilterError, ModelRateLimitError, UserError
from pydantic_ai.messages import BinaryImage

from . import models

logger = logging.getLogger(__name__)

RATE_LIMIT_MESSAGE = (
    "Image generation is temporarily unavailable due to high demand. "
    "Do NOT retry — ask the user to try again in a few minutes."
)
HTTP_TOO_MANY_REQUESTS = 429
# Leading bytes of the reference image formats.
_MAGIC = ((b"\x89PNG", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF8", "image/gif"))


class ImageError(Exception):
    """Raised when the provider fails to return a usable image."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def media_type(data: bytes) -> str:
    """The media type of a reference image's bytes; `ImageError` when it is not PNG, JPEG, WebP or GIF."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    raise ImageError("A reference image is not a PNG, JPEG, WebP or GIF file")


def _model_id(model: str | None, tier: str, task: str) -> str:
    """`model`, else the model of `task`; `ImageError` naming `tasks.<task>` when the config has none."""
    if model:
        return model
    try:
        return ai_config.model_for(task)
    except AIModelsError as e:
        raise ImageError(f"--tier {tier} needs a model for the task {task}: add `tasks.{task}: "
                         f"<provider>:<model>` to the config, or pass --model ({e})") from None


def _png_only(model_id: str, background: str | None, output_format: str) -> None:
    if background == "transparent":
        raise ImageError(f"{model_id} has no transparent background; use an OpenAI-style image model that has one")
    if output_format != "png":
        raise ImageError(f"{model_id} returns PNG only; use a .png output path")


def needs_limits(kind: str) -> bool:
    """Whether `settings` reads the image limits for a model of provider `kind`."""
    return kind in OPENAI_KINDS or kind == ProviderKind.DIFFUSERS


def model_limits(model_id: str) -> ImageLimits | None:
    """The image limits of `model_id` (`providers.<p>.models.<m>.image`), None when it has none."""
    return getattr(ai_config.model_entry(model_id), "image", None)


def _sized(model_id: str, limits: ImageLimits | None) -> ImageLimits:
    """`limits`, needed for a size; `ImageError` naming the missing config entry when None."""
    if limits is not None:
        return limits
    try:
        return ai_config.image_limits(model_id)
    except AIModelsError as e:
        raise ImageError(str(e)) from None


def settings(kind: str, model_id: str, *, aspect_ratio: str | None, image_size: str | None, n: int,
             quality: str | None, background: str | None, output_format: str,
             edit: bool, limits: ImageLimits | None) -> tuple[dict[str, Any], int]:
    """(Pydantic-AI image settings, number of requests) for a model of provider `kind`; `ImageError` for an
    option the kind does not take. `aspect_ratio`, `image_size`, `quality` and `background` are None when
    not given. `limits` are the model's image limits (`model_limits`), None when it has none; a request that
    needs a size without limits is an `ImageError` naming the config entry to add."""
    aspect = aspect_ratio or models.DEFAULT_ASPECT
    size = image_size or models.DEFAULT_SIZE
    if kind in OPENAI_KINDS:
        s: dict[str, Any] = {"openai_n": n}
        if limits is not None:
            if limits.always_sized:
                image_size = size
            if quality is None and limits.default_quality is not None:
                quality = limits.default_quality.value
        if image_size:
            s["dimensions"] = models.openai_size(aspect, image_size, _sized(model_id, limits))
        elif aspect_ratio:
            s["aspect_ratio"] = aspect_ratio
        if quality:
            s["openai_quality"] = quality
        if background:
            s["openai_background"] = background
        if output_format != "png":
            s["openai_output_format"] = output_format
        return s, 1
    _png_only(model_id, background, output_format)
    if kind == ProviderKind.GOOGLE:
        config = {k: v for k, v in (("aspect_ratio", aspect_ratio), ("image_size", image_size)) if v}
        return ({"google_image_config": config} if config else {}), n
    if kind == ProviderKind.DIFFUSERS:
        if edit and aspect_ratio is None and image_size is None:
            return {}, n
        return {"dimensions": models.local_size(aspect, size, _sized(model_id, limits))}, n
    return {}, n


def generate(
    prompt: str,
    *,
    negative: str = "",
    reference_images: Sequence[bytes] = (),
    mask: bytes | None = None,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    num_images: int = 1,
    model: str | None = None,
    tier: str = models.DEFAULT_TIER,
    quality: str | None = None,
    background: str | None = None,
    output_format: str = "png",
) -> list[BinaryImage]:
    """`num_images` images for `prompt`, edited from `reference_images` (file bytes) when given, within the
    transparent area of `mask` (PNG bytes) when given. `model` is a `provider:model` id; None takes the
    model of the config task of `tier` (`models.task_for`)."""
    if not prompt.strip():
        raise ImageError("Prompt cannot be empty")
    refs = [BinaryImage(data=r, media_type=media_type(r)) for r in reference_images]
    task = models.task_for(tier, bool(refs))
    model_id = _model_id(model, tier, task)
    try:
        kind = provider_kind(model_id)
        opts, calls = settings(kind, model_id, aspect_ratio=aspect_ratio, image_size=image_size, n=num_images,
                               quality=quality, background=background, output_format=output_format,
                               edit=bool(refs),
                               limits=model_limits(model_id) if needs_limits(kind) else None)
        generator = images.image_generator(model_id, task=task, mask=mask)
    except AIModelsError as e:
        raise ImageError(str(e)) from None
    full_prompt = f"{prompt}. Do not include: {negative}" if negative else prompt

    logger.info("Image generation started (model=%s, images=%d)", model_id, num_images)
    out: list[BinaryImage] = []
    try:
        with explained(model_id):
            for _ in range(calls):
                result = generator.generate_sync(full_prompt, images=refs or None, settings=opts)
                out += [g.content for g in result.images]
    except ContentFilterError as e:
        raise ImageError(f"Image generation blocked: {e}") from e
    except (AIModelsError, UserError, AgentRunError) as e:
        if isinstance(e, ModelRateLimitError) or getattr(e, "status_code", None) == HTTP_TOO_MANY_REQUESTS:
            raise ImageError(RATE_LIMIT_MESSAGE) from None
        raise ImageError(f"Image generation failed: {e}") from e
    logger.info("Image generation completed (%d images)", len(out))
    return out
