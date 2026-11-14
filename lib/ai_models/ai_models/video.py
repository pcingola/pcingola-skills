"""Image to video (Pydantic-AI has no video call): `local.animate`, an MP4 without audio.

The model is `model`, else the model of task `video`. A video model is `diffusers.<name>` with these keys
besides `repo`, `steps` and `guidance`, all required:

    pipeline        the diffusers class to load (the repository's `model_index.json` names the
                    text-to-video class)
    fps             frames per second of the clip
    size_multiple   width and height are rounded to a multiple of this
    frame_step      frame counts are frame_step * k + 1
    width, height   the size when the caller gives none
    max_frames      the longest clip; a longer request is cut to it

A missing key is a `ConfigError` that names it.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

from . import config
from .errors import ConfigError

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


def frame_size(width: int, height: int, multiple: int) -> tuple[int, int]:
    """(width, height) rounded to the nearest multiple of `multiple`, at least `multiple`."""
    return (max(multiple, round(width / multiple) * multiple), max(multiple, round(height / multiple) * multiple))


def animate(image: bytes, prompt: str, *, seconds: float, model: str | None = None, width: int | None = None,
            height: int | None = None, seed: int | None = None) -> bytes:
    """An MP4 of `image` (PNG or JPEG bytes) animated as `prompt` describes, at least `seconds` long unless
    the model's `max_frames` is shorter."""
    name, bare = config.split_id(config.resolve(model, "video"))
    if (kind := config.provider(name)["kind"]) != "diffusers":
        raise ConfigError(f"provider {name!r} of kind {kind!r} has no video models")
    from . import local

    return local.animate(bare, image, prompt, seconds=seconds, width=width, height=height, seed=seed)


async def aanimate(image: bytes, prompt: str, **kwargs) -> bytes:
    """`animate` in a worker thread."""
    return await asyncio.to_thread(animate, image, prompt, **kwargs)
