"""Image to video (Pydantic-AI has no video call): `animate` (`local.animate`), an MP4 with the sound track the
pipeline generates, or without audio when it generates none; and `present` (`local.present`), a portrait and a
speech recording to an MP4 of the person speaking, with the speech as its sound track.

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

A presenter model (task `presenter`, `present`: a portrait and a speech recording give a clip of the person
speaking it) is `diffusers.<name>` with `repo`, optional `steps`, `guidance`, `args` and `skip`, and these, all
required:

    pipeline        the diffusers class to load: a `DiffusionPipeline` or a `ModularPipeline` class (the
                    repository's `model_index.json` or `modular_model_index.json` names it)
    fps             frames per second of the clip
    buckets         the frame sizes the model makes, a list of [width, height]; a clip takes the one nearest
                    the requested aspect ratio
    audio_rate      the sample rate (Hz) the model takes the speech at, mono
    output          the name of the pipeline output that holds the videos (a modular pipeline's `output`)

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
PRESENTER_KEYS = ("pipeline", "fps", "buckets", "audio_rate", "output")


def _spec(name: str, keys: tuple[str, ...]) -> dict[str, Any]:
    spec = config.diffusers_model(name)
    missing = [k for k in keys if spec.get(k) is None]
    if missing:
        raise ConfigError(f"diffusers model {name!r} lacks {', '.join(missing)} in {config.path()}")
    return spec


def video_spec(name: str) -> dict[str, Any]:
    """The settings of video model `diffusers.<name>`; `ConfigError` naming each missing key of VIDEO_KEYS."""
    return _spec(name, VIDEO_KEYS)


def presenter_spec(name: str) -> dict[str, Any]:
    """The settings of presenter model `diffusers.<name>`; `ConfigError` naming each missing key of
    PRESENTER_KEYS, or for `buckets` that is not a list of [width, height]."""
    spec = _spec(name, PRESENTER_KEYS)
    b = spec["buckets"]
    if not isinstance(b, list) or not b or not all(
            isinstance(x, list) and len(x) == 2 and all(isinstance(n, int) and n > 0 for n in x) for x in b):
        raise ConfigError(f"diffusers model {name!r}: `buckets` must be a list of [width, height] in {config.path()}")
    return spec


def bucket(buckets: list[list[int]], aspect: float) -> tuple[int, int]:
    """The (width, height) of `buckets` whose aspect ratio is nearest `aspect` (width / height), on a log scale so
    that 2:1 and 1:2 are equally far from 1:1; the first of a tie."""
    w, h = min(buckets, key=lambda b: abs(math.log(b[0] / b[1] / aspect)))
    return w, h


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

    return _call(model_id, local.animate, bare, image, prompt, seconds=seconds, width=width, height=height,
                 aspect=aspect, seed=seed)


def present(image: bytes, speech: bytes, *, model: str | None = None, aspect: float | None = None,
            prompt: str | None = None, seed: int | None = None) -> bytes:
    """An MP4 of the person in `image` (PNG or JPEG bytes) speaking `speech` (an audio file, WAV or any format
    FFmpeg reads), as long as the speech, with the speech as its sound track. The size is the model's bucket
    nearest `aspect` (width / height), default the image's. `prompt` replaces the model's default prompt. The
    model is `model`, else the model of task `presenter`."""
    model_id = config.resolve(model, "presenter")
    name, bare = config.split_id(model_id)
    if (kind := config.provider(name)["kind"]) != "diffusers":
        raise ConfigError(f"provider {name!r} of kind {kind!r} has no presenter models")
    from . import local

    return _call(model_id, local.present, bare, image, speech, aspect=aspect, prompt=prompt, seed=seed)


def _call(model_id: str, fn, *args, **kwargs) -> bytes:
    """`fn(*args, **kwargs)`; an error other than `AIModelsError` becomes a one-line `AIModelsError`."""
    try:
        return fn(*args, **kwargs)
    except AIModelsError:
        raise
    except Exception as e:
        first = next(iter(str(e).strip().splitlines()), "")
        raise AIModelsError(f"{model_id}: {type(e).__name__}" + (f": {first}" if first else "")) from e


async def aanimate(image: bytes, prompt: str, **kwargs) -> bytes:
    """`animate` in a worker thread."""
    return await asyncio.to_thread(animate, image, prompt, **kwargs)


async def apresent(image: bytes, speech: bytes, **kwargs) -> bytes:
    """`present` in a worker thread."""
    return await asyncio.to_thread(present, image, speech, **kwargs)
