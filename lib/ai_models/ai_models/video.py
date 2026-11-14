"""Image to video (Pydantic-AI has no video call): `local.animate`, an MP4 without audio.

The model is `model`, else the model of task `video`. A video model is `diffusers.<name>` with these keys
besides `repo`, `steps` and `guidance`, all required:

    pipeline        the diffusers class to load (the repository's `model_index.json` names the
                    text-to-video class)
    fps             frames per second of the clip
    size_multiple   width and height are rounded to a multiple of this
    frame_step      frame counts are frame_step * k + 1
    width, height   the size when the caller gives none; with an `aspect`, reshaped to that ratio at the
                    same pixel count
    max_frames      the longest clip; a longer request is cut to it

A missing key is a `ConfigError` that names it. Any other failure of the model call (a pipeline error,
out of memory, a failed download) is an `AIModelsError` with a one-line message.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

from . import config
from .errors import AIModelsError, ConfigError

VIDEO_KEYS = ("pipeline", "fps", "size_multiple", "frame_step", "width", "height", "max_frames")


def video_spec(name: str) -> dict[str, Any]:
    """The settings of video model `diffusers.<name>`; `ConfigError` naming each missing key of VIDEO_KEYS."""
    spec = config.diffusers_model(name)
    missing = [k for k in VIDEO_KEYS if spec.get(k) is None]
    if missing:
        raise ConfigError(f"diffusers model {name!r} lacks {', '.join(missing)} in {config.path()}")
    return spec


def frame_count(seconds: float, fps: float, frame_step: int, max_frames: int) -> int:
    """The smallest frame_step * k + 1 count (k >= 1) that covers `seconds` at `fps`, cut to `max_frames`."""
    k = max(1, math.ceil((math.ceil(seconds * fps - 1e-6) - 1) / frame_step))
    k = max(1, min(k, (max_frames - 1) // frame_step))
    return frame_step * k + 1


def frame_size(width: float, height: float, multiple: int) -> tuple[int, int]:
    """(width, height) rounded to the nearest multiple of `multiple`, at least `multiple`."""
    return (max(multiple, round(width / multiple) * multiple), max(multiple, round(height / multiple) * multiple))


def clip_size(spec: dict[str, Any], width: int | None = None, height: int | None = None,
              aspect: float | None = None) -> tuple[int, int]:
    """The frame size of a clip of model `spec`: `width` and `height`, else the model's; `aspect` (width / height)
    reshapes it to that ratio at the same pixel count; then rounded by `frame_size` to `size_multiple`."""
    w, h = width or spec["width"], height or spec["height"]
    if aspect is not None:
        w, h = math.sqrt(w * h * aspect), math.sqrt(w * h / aspect)
    return frame_size(w, h, spec["size_multiple"])


def animate(image: bytes, prompt: str, *, seconds: float, model: str | None = None, width: int | None = None,
            height: int | None = None, aspect: float | None = None, seed: int | None = None) -> bytes:
    """An MP4 of `image` (PNG or JPEG bytes) animated as `prompt` describes, at least `seconds` long unless
    the model's `max_frames` is shorter. The size is `width` and `height`, else the model's; `aspect`
    (width / height) reshapes it to that ratio at the same pixel count."""
    model_id = config.resolve(model, "video")
    name, bare = config.split_id(model_id)
    if (kind := config.provider(name)["kind"]) != "diffusers":
        raise ConfigError(f"provider {name!r} of kind {kind!r} has no video models")
    from . import local

    try:
        return local.animate(bare, image, prompt, seconds=seconds, width=width, height=height, aspect=aspect,
                            seed=seed)
    except AIModelsError:
        raise
    except Exception as e:
        first = next(iter(str(e).strip().splitlines()), "")
        raise AIModelsError(f"{model_id}: {type(e).__name__}" + (f": {first}" if first else "")) from e


async def aanimate(image: bytes, prompt: str, **kwargs) -> bytes:
    """`animate` in a worker thread."""
    return await asyncio.to_thread(animate, image, prompt, **kwargs)
