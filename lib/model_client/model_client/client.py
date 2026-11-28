"""`model-client` (`python -m model_client`): a command-line client of a model server at a URL
(docs/model_server.md, Command-line client).

    model-client [--url URL] models [ID]
    model-client [--url URL] status VIDEO_ID
    model-client [--url URL] video --model ID --image FILE --prompt TEXT [--seconds S] [--aspect A] [--size WxH]
                                   [--seed N] [-o OUT]
    model-client [--url URL] image --model ID --prompt TEXT [--size WxH] [--seed N] [-o OUT]
    model-client [--url URL] speech --model ID --text TEXT [--voice V] [-o OUT]

`--url` is the server's `/v1` base URL, default `http://localhost:<model_server.port>/v1` (`plugin_settings`). Model
ids are the server's, as `GET /v1/models` lists them. A generated file goes to `-o`, else to the current directory
as `<model id, ':' and '/' as '_'>_<YYYYmmdd-HHMMSS>.<ext>`; an existing file is never overwritten.

The calls are the `openai` SDK's on a client with `base_url` the URL, as `ai_models.video` makes them. This is a direct
call, outside `ai_models`, because `ai_models` reaches a server only through a provider of config.yaml and this tool
calls a server at a URL no provider names (docs/architecture.md, Standard paths for model calls). Each command's core
function returns its result and raises on error; `main` prints, writes the file and sets the exit code.
"""

from __future__ import annotations

import argparse
import base64
import sys
import time
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import openai
import yaml
from openai import omit
from openai.types import Video

TIMEOUT_SECONDS = 900.0
POLL_SECONDS = 0.5
MODEL_FIELDS = ("kind", "role", "entry", "voices")


class ClientError(Exception):
    """An error of a command: a failed video job, an output file that exists, a URL without a server."""


def default_url() -> str:
    """`http://localhost:<model_server.port>/v1`, the port from the settings file."""
    import plugin_settings

    return f"http://localhost:{plugin_settings.load_config().model_server.port}/v1"


def connect(url: str, timeout: float = TIMEOUT_SECONDS) -> openai.OpenAI:
    """An `openai` client of the server at `url` (its `/v1`), without retries."""
    return openai.OpenAI(base_url=url, api_key="none", timeout=timeout, max_retries=0)


@contextmanager
def answered() -> Iterator[None]:
    """An SDK error becomes a one-line `ClientError`: the status, code and message of an error answer, or the URL
    the client could not reach."""
    try:
        yield
    except openai.APIStatusError as e:
        code = f" {e.code}" if e.code else ""
        message = e.body.get("message", e.message) if isinstance(e.body, dict) else e.message
        raise ClientError(f"HTTP {e.status_code}{code}: {message}") from e
    except openai.APIConnectionError as e:
        raise ClientError(f"no answer from {e.request.url}: {e}") from e


@contextmanager
def video_calls() -> Iterator[None]:
    """`answered`, and no Sora deprecation warning: the SDK flags `videos` deprecated because OpenAI's own video API
    is shut down; the model server serves it."""
    with answered(), warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*Sora API.*")
        yield


def models(client: openai.OpenAI) -> list[str]:
    """The ids of `GET /v1/models`, in the server's order."""
    with answered():
        return [m.id for m in client.models.list()]


def model(client: openai.OpenAI, model_id: str) -> dict[str, Any]:
    """`GET /v1/models/{id}`: a local model's `kind`, `role`, `entry` (and a speech model's `voices`); the whole
    object for another model (Ollama's)."""
    with answered():
        got = client.models.retrieve(model_id).model_dump(mode="json")
    picked = {k: got[k] for k in MODEL_FIELDS if got.get(k) is not None}
    return picked or got


def status(client: openai.OpenAI, video_id: str) -> Video:
    """The video job `video_id` (`GET /v1/videos/{id}`)."""
    with video_calls():
        return client.videos.retrieve(video_id)


def status_line(job: Video) -> str:
    """`<id> <status> <progress>%`, with the error of a failed job."""
    line = f"{job.id} {job.status} {job.progress}%"
    return line + (f": {job.error.code}: {job.error.message}" if job.error else "")


def image_file(image: bytes) -> tuple[str, bytes, str]:
    """The multipart file of an image: (name, bytes, media type), PNG unless the bytes are JPEG."""
    return ("image.jpg", image, "image/jpeg") if image[:3] == b"\xff\xd8\xff" else ("image.png", image, "image/png")


def video(client: openai.OpenAI, model_id: str, image: bytes, prompt: str, *, seconds: float | None = None,
          aspect: float | None = None, size: str | None = None, seed: int | None = None,
          on_status: Callable[[Video], None] | None = None) -> bytes:
    """The MP4 of a video job (`POST /v1/videos`) of `image` (PNG or JPEG bytes) animated as `prompt` describes,
    polled until it completes; `on_status` gets the job at creation and at each change of status. `ClientError`
    with the job's error when it fails."""
    extra = {k: v for k, v in (("aspect", aspect), ("seed", seed)) if v is not None}
    with video_calls():
        job = client.videos.create(model=model_id, prompt=prompt, input_reference=image_file(image),
                                   seconds=f"{seconds:g}" if seconds is not None else omit, size=size or omit,
                                   extra_body=extra or None)
        if on_status:
            on_status(job)
        while job.status in ("queued", "in_progress"):
            time.sleep(POLL_SECONDS)
            now = client.videos.retrieve(job.id)
            if on_status and now.status != job.status:
                on_status(now)
            job = now
        if job.status != "completed":
            raise ClientError(f"video job {status_line(job)}")
        return client.videos.download_content(job.id).content


def image(client: openai.OpenAI, model_id: str, prompt: str, *, size: str | None = None,
          seed: int | None = None) -> bytes:
    """The PNG of `POST /v1/images/generations`."""
    with answered():
        got = client.images.generate(model=model_id, prompt=prompt, size=size or omit,
                                     extra_body={"seed": seed} if seed is not None else None)
    return base64.b64decode(got.data[0].b64_json)


def speech(client: openai.OpenAI, model_id: str, text: str, *, voice: str | None = None) -> bytes:
    """The WAV file of `POST /v1/audio/speech`. Without `voice`, the model's default voice: its entry's `voice`, else
    the first of its `voices` (`GET /v1/models/{id}`); the server's request type requires a voice."""
    with answered():
        if not voice:
            got = client.models.retrieve(model_id).model_dump(mode="json")
            voice = (got.get("entry") or {}).get("voice") or next(iter(got.get("voices") or []), None)
        if not voice:
            raise ClientError(f"{model_id} has no default voice; give one with --voice")
        return client.audio.speech.create(model=model_id, input=text, voice=voice, response_format="wav").content


def default_name(model_id: str, ext: str, when: datetime) -> str:
    """`<model id, ':' and '/' as '_'>_<YYYYmmdd-HHMMSS>.<ext>`."""
    return f"{model_id.replace(':', '_').replace('/', '_')}_{when:%Y%m%d-%H%M%S}.{ext}"


def output_path(out: Path | None, model_id: str, ext: str, directory: Path, when: datetime) -> Path:
    """`out`, else `default_name` in `directory`; `ClientError` when the file exists."""
    path = out if out is not None else directory / default_name(model_id, ext, when)
    if path.exists():
        raise ClientError(f"{path} exists; the client does not overwrite a file")
    return path


def save(data: bytes, path: Path) -> Path:
    """`data` written to the new file `path`; `ClientError` when it exists."""
    try:
        with path.open("xb") as f:
            f.write(data)
    except FileExistsError as e:
        raise ClientError(f"{path} exists; the client does not overwrite a file") from e
    return path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="model-client", description="A client of a model server at a URL.")
    p.add_argument("--url", help="the server's /v1 base URL (default http://localhost:<model_server.port>/v1)")
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("models", help="the model ids, or one model's kind, role and entry")
    m.add_argument("id", nargs="?")
    s = sub.add_parser("status", help="the status of a video job")
    s.add_argument("id")
    v = sub.add_parser("video", help="an MP4 of an image animated as a prompt describes")
    v.add_argument("--model", required=True)
    v.add_argument("--image", required=True, type=Path)
    v.add_argument("--prompt", required=True)
    v.add_argument("--seconds", type=float)
    v.add_argument("--aspect", type=float)
    v.add_argument("--size", help="WxH")
    v.add_argument("--seed", type=int)
    v.add_argument("-o", "--output", type=Path)
    i = sub.add_parser("image", help="a PNG of a prompt")
    i.add_argument("--model", required=True)
    i.add_argument("--prompt", required=True)
    i.add_argument("--size", help="WxH")
    i.add_argument("--seed", type=int)
    i.add_argument("-o", "--output", type=Path)
    t = sub.add_parser("speech", help="a WAV file of a text spoken")
    t.add_argument("--model", required=True)
    t.add_argument("--text", required=True)
    t.add_argument("--voice")
    t.add_argument("-o", "--output", type=Path)
    return p


def run(args: argparse.Namespace) -> None:
    """The command of `args`, its results printed."""
    client = connect(args.url or default_url())
    if args.command == "models":
        if args.id:
            print(yaml.safe_dump(model(client, args.id), sort_keys=False), end="")
        else:
            print("\n".join(models(client)))
        return
    if args.command == "status":
        print(status_line(status(client, args.id)))
        return
    ext = {"video": "mp4", "image": "png", "speech": "wav"}[args.command]
    path = output_path(args.output, args.model, ext, Path.cwd(), datetime.now())
    start = time.monotonic()
    if args.command == "video":
        data = video(client, args.model, args.image.read_bytes(), args.prompt, seconds=args.seconds,
                     aspect=args.aspect, size=args.size, seed=args.seed,
                     on_status=lambda job: print(status_line(job), flush=True))
    elif args.command == "image":
        data = image(client, args.model, args.prompt, size=args.size, seed=args.seed)
    else:
        data = speech(client, args.model, args.text, voice=args.voice)
    print(f"{save(data, path)} ({time.monotonic() - start:.1f} s)")


def main(argv: list[str] | None = None) -> int:
    import plugin_settings

    args = parser().parse_args(argv)
    try:
        run(args)
    except (ClientError, openai.OpenAIError, plugin_settings.ConfigFileError, OSError) as e:
        print(f"model-client: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
