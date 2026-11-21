"""Image generation with `ai_models.images` (a Pydantic-AI `ImageGenerator`).

The model is `--model` (a `provider:model` id), else the model of the task
`models.task_for` picks from `--tier` (`tasks.<task>` of config.yaml): tier `fast` (the
default) takes `image_edit` for a request with reference images, else `image`;
tier `best` takes `image_best` and tier `multi-ref` takes `image_multi_ref`,
with and without reference images. `settings` maps the CLI options to the Pydantic-AI settings of the
model's provider kind:

- OpenAI kinds (`openai`, `azure`, `openrouter`, `ollama`): one request with
  `openai_n`; `--size` gives `dimensions` within the model's image limits
  (`providers.<p>.models.<m>.image`, `OpenAIImageLimits`), else `--aspect` goes as
  `aspect_ratio`; `--quality`, `--background` and a non-PNG format go when
  given. A model with `always_sized` always gets `dimensions` (default 1:1,
  1K); a model with `default_quality` gets it unless `--quality` is given. A
  mask goes with the edit.
- `google`: `google_image_config` with `--aspect` and `--size` when given,
  else the model's default (an edit keeps the reference's aspect); one
  request per image; PNG only, no transparent background.
- `diffusers` (local): `dimensions` from `models.local_size` within the
  model's image limits (`DiffusersImageLimits`); for an edit only
  when `--aspect` or `--size` is given, else the pipeline keeps the first
  reference image's size. One request per image; PNG only.

The kind is the one the model runs as (`ai_models.served.kind`): a diffusers model of a model server, reached
through a provider of kind `openai`, takes the `diffusers` settings and its server's image limits.

`request_limits` reads the model's limits once per request (`ai_models.config.image_limits`): required when the
request needs a size, so a missing entry fails before any model call with the key to add. Every failure is an
`ImageError` with a message for the CLI.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ai_models import config as ai_config
from ai_models import images
from ai_models.errors import AIModelsError, explained
from ai_models.served import kind as provider_kind
from plugin_settings import OPENAI_KINDS, DiffusersImageLimits, OpenAIImageLimits, ProviderKind
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
# The output path extensions and their image formats.
OUTPUT_FORMATS = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}


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
    """`model`, else the model of `task` (`ai_config.resolve`); `ImageError` naming `tasks.<task>` when the config
    has none, or why `model` cannot serve the task."""
    try:
        return ai_config.resolve(model, task)
    except AIModelsError as e:
        if model:
            raise ImageError(str(e)) from None
        raise ImageError(f"--tier {tier} needs a model for the task {task}: add `tasks.{task}: "
                         f"<provider>:<model>` to the config, or pass --model ({e})") from None


def _png_only(model_id: str, background: str | None, output_format: str) -> None:
    if background == "transparent":
        raise ImageError(f"{model_id} has no transparent background; use an OpenAI-style image model that has one")
    if output_format != "png":
        raise ImageError(f"{model_id} returns PNG only; use a .png output path")


def needs_size(kind: str, *, aspect_ratio: str | None, image_size: str | None, edit: bool) -> bool:
    """Whether a request to a model of provider `kind` must carry a size, so needs the model's image limits: an
    OpenAI kind with `--size`, a diffusers model unless it is an edit without `--aspect` and `--size`."""
    if kind in OPENAI_KINDS:
        return image_size is not None
    return kind == ProviderKind.DIFFUSERS and not (edit and aspect_ratio is None and image_size is None)


def request_limits(kind: str, model_id: str, *, aspect_ratio: str | None, image_size: str | None,
                   edit: bool) -> OpenAIImageLimits | DiffusersImageLimits | None:
    """The image limits of `model_id` for one request: None for a kind without limits or a model without them
    whose request needs no size (`needs_size`); `ImageError` naming the config key to add when it needs one."""
    try:
        return ai_config.image_limits(model_id, required=needs_size(kind, aspect_ratio=aspect_ratio,
                                                                    image_size=image_size, edit=edit))
    except AIModelsError as e:
        raise ImageError(str(e)) from None


def settings(kind: str, model_id: str, *, aspect_ratio: str | None, image_size: str | None, n: int,
             quality: str | None, background: str | None, output_format: str,
             edit: bool, limits: OpenAIImageLimits | DiffusersImageLimits | None) -> tuple[dict[str, Any], int]:
    """(Pydantic-AI image settings, number of requests) for a model of provider `kind`; `ImageError` for an
    option the kind does not take. `aspect_ratio`, `image_size`, `quality` and `background` are None when
    not given. `limits` are the model's image limits from `request_limits`: present whenever the request needs a
    size."""
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
            s["dimensions"] = models.openai_size(aspect, image_size, limits)
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
        return {"dimensions": models.local_size(aspect, size, limits)}, n
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
                               limits=request_limits(kind, model_id, aspect_ratio=aspect_ratio, image_size=image_size,
                                                     edit=bool(refs)))
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


def output_format(out: Path) -> str:
    """The image format of the output path's extension; `ImageError` for an extension without one."""
    ext = out.suffix.lower()
    fmt = OUTPUT_FORMATS.get(ext)
    if fmt is None:
        raise ImageError(f"Unsupported output extension {ext!r}; use one of {', '.join(OUTPUT_FORMATS)}")
    return fmt


def read_image(path: str | Path) -> bytes:
    """The bytes of the reference or mask image at `path` (`~` expanded); `ImageError` when it is not a file."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise ImageError(f"Reference image not found: {p}")
    return p.read_bytes()


def output_path(out: str | Path, index: int, total: int) -> Path:
    """The path of image `index` of `total` for the output path `out` (`~` expanded), its parent directory created.
    With several images an index suffix goes before the extension: out.png -> out_1.png, out_2.png."""
    p = Path(out).expanduser()
    if total > 1:
        p = p.with_stem(f"{p.stem}_{index + 1}")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_images(
    prompt: str,
    out: str | Path,
    *,
    negative: str = "",
    refs: Sequence[str | Path] = (),
    mask: str | Path | None = None,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
    num_images: int = 1,
    model: str | None = None,
    tier: str = models.DEFAULT_TIER,
    quality: str | None = None,
    background: str | None = None,
    on_written: Callable[[Path], object] | None = None,
) -> list[Path]:
    """The work of `image-gen generate`: `num_images` images for `prompt` (`generate`), edited from the reference
    image files `refs` within the transparent area of the `mask` file, written to `out` (`output_path`) in the
    format of its extension; return the written paths. `on_written` is called with each path as soon as it is
    written. Every refusal before the model call (extension, `num_images`, a missing file, a mask without a
    reference) and every failure of the call is an `ImageError`."""
    fmt = output_format(Path(out))
    if num_images < 1:
        raise ImageError("--n must be at least 1")
    ref_bytes = [read_image(r) for r in refs]
    if mask and not ref_bytes:
        raise ImageError("--mask needs a --ref: the mask applies to the first reference image")
    mask_bytes = read_image(mask) if mask else None
    images = generate(prompt, negative=negative, reference_images=ref_bytes, mask=mask_bytes,
                      aspect_ratio=aspect_ratio, image_size=image_size, num_images=num_images, model=model,
                      tier=tier, quality=quality, background=background, output_format=fmt)
    written: list[Path] = []
    for i, image in enumerate(images):
        path = output_path(out, i, len(images))
        path.write_bytes(image.data)
        written.append(path)
        if on_written is not None:
            on_written(path)
    return written
