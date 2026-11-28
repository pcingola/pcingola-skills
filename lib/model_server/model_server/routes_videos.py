"""`POST /v1/videos`, `GET /v1/videos/{id}` and `GET /v1/videos/{id}/content`: asynchronous video jobs on a local
diffusers video model (`ai_models.video.aanimate`) or presenter model (`ai_models.video.apresent`).

Create (multipart): `model`, `prompt`, `input_reference` (the image; required by a presenter model, optional for a
video model: without it the clip comes from the prompt alone, which needs a model whose entry sets `text_pipeline`,
else the request is a 400 naming `input_reference`), `seconds` (video: the clip's length,
default 4), `size` (`WxH`; video: width and height, else the model's), and two fields outside
`openai.types.VideoCreateParams`: `audio` (presenter: the narration recording, required) and `aspect` (width / height;
video: reshapes the size to it at the same pixel count; presenter: the bucket nearest it, default the image's), plus
`seed`. The answer is the job as `openai.types.Video`, `status: queued`; the job runs when the scheduler admits it.
The video's id is also its job's id in the scheduler (`GET /v1/jobs`); a cancelled job ends `failed` with the error
code `cancelled`.
Retrieve answers the job; content answers the MP4 (`video/mp4`) once the job is `completed`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from openai.types import VideoCreateParams

from .forms import extras, one_file, parse_size, text_fields
from .job import Job
from .model_ref import ModelRef
from .model_role import ModelRole
from .requests import server_of
from .server import Server
from .server_error import ErrorType, ServerError
from .video_job import VideoJob, VideoStatus

router = APIRouter()
DEFAULT_SECONDS = 4.0


def number(fields: dict[str, Any], name: str, default: float | None = None) -> float | None:
    """The number field `name`; `ServerError` 400 when it is not a positive number."""
    value = fields.get(name, default)
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = 0.0
    if out <= 0:
        raise ServerError(400, f"{name} must be a positive number, not {value!r}", param=name)
    return out


def planned_video(ref: ModelRef, seconds: float, size: tuple[int, int] | None, aspect: float | None) -> tuple[str, str]:
    """The (seconds, `WxH`) of the clip a video model makes (`ai_models.video.clip_size`, `frame_count`)."""
    from ai_models.video import clip_size, frame_count

    spec = ref.entry
    w, h = clip_size(spec, *(size or (None, None)), aspect)
    frames = frame_count(seconds, spec.fps, spec.frame_step, spec.max_frames)
    return f"{frames / spec.fps:g}", f"{w}x{h}"


def planned_presenter(ref: ModelRef, image: bytes, audio: bytes, aspect: float | None) -> tuple[str, str]:
    """The (seconds, `WxH`) of the clip a presenter model makes: as long as the speech, the bucket nearest
    `aspect` (`ai_models.local.presenter_still`)."""
    from ai_models import local

    w, h = local.presenter_still(ref.entry.buckets, image, aspect).size
    track, rate = local.read_audio(audio)
    return f"{track.shape[1] / rate:g}", f"{w}x{h}"


async def run_job(srv: Server, ref: ModelRef, job: VideoJob, queued: Job, call: Any) -> None:
    """Run the job when the scheduler admits its scheduler job `queued` (of the same id); the MP4, or the error,
    goes to the job (`cancelled` for a cancelled job)."""
    from ai_models import AIModelsError

    ttl = srv.settings.video_ttl
    try:
        async with srv.running(ref, queued):
            job.start()
            content = await call()
    except ServerError as e:
        job.fail(e.error.code or e.error.type, e.error.message, ttl)
    except AIModelsError as e:
        job.fail("model_error", str(e), ttl)
    except Exception as e:  # a job has no client to answer; the error goes in the job
        job.fail("server_error", f"{type(e).__name__}: {e}", ttl)
    else:
        job.complete(content, ttl)


@router.post("/v1/videos")
async def create(request: Request) -> JSONResponse:
    from ai_models import video

    form = await request.form()
    fields = text_fields(form)
    srv = server_of(request)
    ref = srv.ref(form.get("model"), ModelRole.VIDEO, ModelRole.PRESENTER)
    prompt = form.get("prompt") if isinstance(form.get("prompt"), str) else ""
    if more := extras(VideoCreateParams, fields, "audio", "aspect", "seed"):
        raise ServerError(400, f"{ref.id} takes no request fields {', '.join(sorted(more))}", param=next(iter(more)))
    image = await one_file(form, "input_reference", required=ref.role == ModelRole.PRESENTER)
    aspect = number(fields, "aspect")
    seed = fields.get("seed")
    if seed is not None and not isinstance(seed, int):
        raise ServerError(400, f"seed must be an integer, not {seed!r}", param="seed")
    if ref.role == ModelRole.VIDEO:
        if not prompt:
            raise ServerError(400, "a video model needs a `prompt`", param="prompt")
        if image is None and not ref.entry.text_pipeline:
            raise ServerError(400, f"{ref.id} needs an image (`input_reference`): its entry has no `text_pipeline`",
                              param="input_reference")
        seconds = number(fields, "seconds", DEFAULT_SECONDS)
        size = parse_size(form.get("size"))
        planned = planned_video(ref, seconds, size, aspect)
        width, height = size or (None, None)

        def call():
            return video.aanimate(image, prompt, seconds=seconds, model=ref.id, width=width, height=height,
                                  aspect=aspect, seed=seed)
    else:
        audio = await one_file(form, "audio", required=True)
        if aspect is None and (size := parse_size(form.get("size"))):
            aspect = size[0] / size[1]
        planned = planned_presenter(ref, image, audio, aspect)

        def call():
            return video.apresent(image, audio, model=ref.id, aspect=aspect, prompt=prompt or None, seed=seed)
    job = srv.videos.add(VideoJob(ref.id, prompt, *planned))
    srv.spawn(run_job(srv, ref, job, srv.submit(ref, job.id), call))
    return JSONResponse(job.video().model_dump(mode="json"))


@router.get("/v1/videos/{video_id}")
async def retrieve(video_id: str, request: Request) -> JSONResponse:
    return JSONResponse(server_of(request).videos.get(video_id).video().model_dump(mode="json"))


@router.get("/v1/videos/{video_id}/content")
async def content(video_id: str, request: Request, variant: str = "video") -> Response:
    job = server_of(request).videos.get(video_id)
    if variant != "video":
        raise ServerError(400, f"variant {variant!r}: local video models make the video only", param="variant")
    if job.status != VideoStatus.COMPLETED:
        raise ServerError(409, f"video {video_id} is {job.status.value}; its content exists once it is completed",
                          ErrorType.INVALID_REQUEST, "video_not_ready", "video_id")
    return Response(job.content, media_type="video/mp4")
