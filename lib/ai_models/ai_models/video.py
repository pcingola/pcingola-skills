"""Image to video (Pydantic-AI has no video call): `animate` (`local.animate`), an MP4 with the sound track the
pipeline generates, or without audio when it generates none; and `present` (`local.present`), a portrait and a
speech recording to an MP4 of the person speaking, with the speech as its sound track.

The model is `model`, else the model of task `video`. A video model is a diffusers model
(`providers.<p>.models.<name>`) with these keys besides `repo`, `steps` and `guidance`, all required:

    pipeline        the diffusers class to load (the repository's `model_index.json` names the
                    text-to-video class)
    fps             frames per second of the clip
    size_multiple   width and height are rounded to a multiple of this
    frame_step      frame counts are frame_step * k + 1
    width, height   the size when the caller gives none; with an `aspect`, reshaped to that ratio at the
                    same pixel count
    max_frames      the longest clip; a longer request is cut to it

A presenter model (task `presenter`, `present`: a portrait and a speech recording give a clip of the person
speaking it) is a diffusers model with `repo`, optional `steps`, `guidance`, `args` and `skip`, and these, all
required:

    pipeline        the diffusers class to load: a `DiffusionPipeline` or a `ModularPipeline` class (the
                    repository's `model_index.json` or `modular_model_index.json` names it)
    fps             frames per second of the clip
    buckets         the frame sizes the model makes, a list of [width, height]; a clip takes the one nearest
                    the requested aspect ratio
    audio_rate      the sample rate (Hz) the model takes the speech at, mono
    output          the name of the pipeline output that holds the videos (a modular pipeline's `output`)

A model of a provider of kind `openai` is a video or presenter model of a model server (`served`): the job goes to
`POST <base_url>/videos` (video: `client.videos.create`; presenter: `client.post` with the narration as a second file,
which `videos.create` cannot send), is polled with `client.videos.poll` and downloaded with
`client.videos.download_content`. The model's keys come from the server's entry (`config.diffusers_model`), so a
size is computed here with `clip_size` and sent as `WxH`.

The schema checks these keys at load (a missing one, or a key of another role, names its YAML path), and that
`tasks.video` and `tasks.presenter` name a model of that role; `config.resolve` checks a model the caller names.
Any other failure of the model call
(a pipeline error, out of memory, a failed download) is an `AIModelsError` with a one-line message.
"""

from __future__ import annotations

import asyncio
import math
import warnings
from collections.abc import Sequence

from plugin_settings import DiffusersRole, DiffusersVideoModel, ProviderKind

from . import config
from .errors import AIModelsError

POLL_MS = 500


def bucket(buckets: Sequence[tuple[int, int]], aspect: float) -> tuple[int, int]:
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


def clip_size(spec: DiffusersVideoModel, width: int | None = None, height: int | None = None,
              aspect: float | None = None) -> tuple[int, int]:
    """The frame size of a clip of model `spec`: `width` and `height`, else the model's; `aspect` (width / height)
    reshapes it to that ratio at the same pixel count; then rounded by `frame_size` to `size_multiple`."""
    w, h = width or spec.width, height or spec.height
    if aspect is not None:
        w, h = math.sqrt(w * h * aspect), math.sqrt(w * h / aspect)
    return frame_size(w, h, spec.size_multiple)


def animate(image: bytes, prompt: str, *, seconds: float, model: str | None = None, width: int | None = None,
            height: int | None = None, aspect: float | None = None, seed: int | None = None) -> bytes:
    """An MP4 of `image` (PNG or JPEG bytes) animated as `prompt` describes, at least `seconds` long unless
    the model's `max_frames` is shorter. The size is `width` and `height`, else the model's; `aspect`
    (width / height) reshapes it to that ratio at the same pixel count."""
    model_id = config.resolve(model, "video")
    if _on_server(model_id):
        spec = config.diffusers_model(model_id, DiffusersRole.VIDEO)
        size = clip_size(spec, width, height, aspect) if width or height or aspect else None
        return asyncio.run(_server_animate(model_id, image, prompt, seconds, size, seed))
    from . import local

    return _call(model_id, local.animate, model_id, image, prompt, seconds=seconds, width=width, height=height,
                 aspect=aspect, seed=seed)


def present(image: bytes, speech: bytes, *, model: str | None = None, aspect: float | None = None,
            prompt: str | None = None, seed: int | None = None) -> bytes:
    """An MP4 of the person in `image` (PNG or JPEG bytes) speaking `speech` (an audio file, WAV or any format
    FFmpeg reads), as long as the speech, with the speech as its sound track. The size is the model's bucket
    nearest `aspect` (width / height), default the image's. `prompt` replaces the model's default prompt. The
    model is `model`, else the model of task `presenter`."""
    model_id = config.resolve(model, "presenter")
    if _on_server(model_id):
        config.diffusers_model(model_id, DiffusersRole.PRESENTER)
        return asyncio.run(_server_present(model_id, image, speech, aspect, prompt, seed))
    from . import local

    return _call(model_id, local.present, model_id, image, speech, aspect=aspect, prompt=prompt, seed=seed)


def _on_server(model_id: str) -> bool:
    """Whether `model_id` is a model of a model server: its provider is of kind `openai`."""
    return config.provider(config.split_id(model_id)[0]).kind == ProviderKind.OPENAI


def image_file(image: bytes) -> tuple[str, bytes, str]:
    """The multipart file of an image: (name, bytes, media type), PNG unless the bytes are JPEG."""
    return ("image.jpg", image, "image/jpeg") if image[:3] == b"\xff\xd8\xff" else ("image.png", image, "image/png")


async def _server_animate(model_id: str, image: bytes, prompt: str, seconds: float, size: tuple[int, int] | None,
                          seed: int | None) -> bytes:
    from openai import omit

    async def create(client):
        return await client.videos.create(model=config.split_id(model_id)[1], prompt=prompt,
                                          input_reference=image_file(image), seconds=f"{seconds:g}",
                                          size=f"{size[0]}x{size[1]}" if size else omit,
                                          extra_body={"seed": seed} if seed is not None else None)

    return await _server_job(model_id, create)


async def _server_present(model_id: str, image: bytes, speech: bytes, aspect: float | None, prompt: str | None,
                          seed: int | None) -> bytes:
    from openai.types import Video

    body = {k: v for k, v in (("model", config.split_id(model_id)[1]), ("prompt", prompt or ""), ("aspect", aspect),
                              ("seed", seed)) if v is not None}
    files = [("input_reference", image_file(image)), ("audio", ("speech", speech, "application/octet-stream"))]

    async def create(client):
        return await client.post("/videos", cast_to=Video, body=body, files=files,
                                 options={"headers": {"Content-Type": "multipart/form-data"}})

    return await _server_job(model_id, create)


async def _server_job(model_id: str, create) -> bytes:
    """The MP4 of the video job `create(client)` makes on the model server of `model_id`, once it completes;
    `AIModelsError` with the job's error when it fails."""
    from . import served

    client = served.client(model_id)
    with served.answered(model_id), warnings.catch_warnings():
        # The SDK flags `videos` deprecated because OpenAI's own video API is shut down; the model server serves it.
        warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*Sora API.*")
        job = await client.videos.poll((await create(client)).id, poll_interval_ms=POLL_MS)
        if job.status != "completed":
            raise AIModelsError(f"{model_id}: the video job {job.status}"
                                + (f": {job.error.message}" if job.error else ""))
        return (await client.videos.download_content(job.id)).content


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
