"""`model-client` (`python -m model_client`): a command-line client of a model server at a URL
(docs/model_server.md, Command-line client).

    model-client [--url URL | --provider NAME] models [--tests] [ID]
    model-client [--url URL | --provider NAME] status VIDEO_ID
    model-client [--url URL | --provider NAME] jobs
    model-client [--url URL | --provider NAME] cancel (ID | --all)
    model-client [--url URL | --provider NAME] video --model ID [--image FILE] --prompt TEXT [--seconds S]
                                                     [--aspect A] [--size WxH] [--seed N] [-o OUT]
    model-client [--url URL | --provider NAME] image --model ID --prompt TEXT [--size WxH] [--seed N] [-o OUT]
    model-client [--url URL | --provider NAME] speech --model ID --text TEXT [--voice V] [-o OUT]

The server's `/v1` base URL is, in order: `--url`, the `base_url` of the provider `--provider`, the `base_url` of
the provider `model_client.provider`, `http://localhost:<model_server.port>/v1` (`plugin_settings`). Model
ids are the server's, as `GET /v1/models` lists them: `<runtime>:<model>`. `models` prints `server: <provider or
URL>`, then one line per model, `<role> <runtime> <id>`, grouped by role in `ROLES` order; it hides the test models
(`test: true`) unless `--tests`. `jobs` prints one line per queued or running job of the server (`GET /v1/jobs`),
`<id> <state> <role> <model> <age>`; `cancel` cancels one job (`DELETE /v1/jobs/{id}`) or every job
(`DELETE /v1/jobs`) and prints the cancelled jobs the same way. A generated file goes to `-o`, else to the current directory
as `<model id, ':' and '/' as '_'>_<YYYYmmdd-HHMMSS>.<ext>`; an existing file is never overwritten.

The calls are the `openai` SDK's on a client with `base_url` the URL, as `ai_models.video` makes them. This is a direct
call, outside `ai_models`, because `ai_models` reaches a server only through a provider of config.yaml and this tool
also calls a server at a URL no provider names (docs/architecture.md, Standard paths for model calls). Each command's
core function returns its result and raises on error; `main` prints, writes the file and sets the exit code.
"""

from __future__ import annotations

import argparse
import base64
import sys
import time
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import openai
import yaml
from openai import omit
from openai.types import Video

TIMEOUT_SECONDS = 900.0
POLL_SECONDS = 0.5
MODEL_FIELDS = ("kind", "role", "test", "entry", "voices")
# The order of the role groups of `models`; a model of another role or none comes after them.
ROLES = ("image", "video", "presenter", "speech", "music", "align", "chat", "embedding")


class ClientError(Exception):
    """An error of a command: a failed video job, an output file that exists, a URL without a server."""


def server(url: str | None = None, provider: str | None = None) -> tuple[str, str]:
    """(the server's `/v1` URL, its name for `models`: the provider, else the URL), the URL in order: `url`, the
    `base_url` of provider `provider`, the `base_url` of `model_client.provider`,
    `http://localhost:<model_server.port>/v1`; the settings from the settings file. `ClientError` when `provider`
    is not a provider of kind `openai` with a `base_url`."""
    if url:
        return url, url
    import plugin_settings

    cfg = plugin_settings.load_config()
    name = provider or cfg.model_client.provider
    if name is None:
        local = f"http://localhost:{cfg.model_server.port}/v1"
        return local, local
    if e := cfg.server_error(name):
        raise ClientError(f"--provider: {e}")
    return cfg.providers[name].base_url, name


def server_url(url: str | None = None, provider: str | None = None) -> str:
    """The server's `/v1` URL (`server`)."""
    return server(url, provider)[0]


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


@dataclass(frozen=True)
class Listed:
    """A model of `GET /v1/models`: its id, role and runtime (the object's `kind`), None when the object has none,
    and whether it is a test model."""

    id: str
    role: str | None
    runtime: str | None
    test: bool


def models(client: openai.OpenAI, tests: bool = False) -> list[Listed]:
    """The models of `GET /v1/models`, grouped by role in `ROLES` order, in the server's order within a group;
    without `tests`, no test model."""
    with answered():
        got = [m.model_dump(mode="json") for m in client.models.list()]
    listed = [Listed(m["id"], m.get("role"), m.get("kind"), bool(m.get("test"))) for m in got]
    order = {role: i for i, role in enumerate(ROLES)}
    return sorted((m for m in listed if tests or not m.test), key=lambda m: order.get(m.role, len(ROLES)))


def model_lines(name: str, listed: list[Listed]) -> list[str]:
    """`server: <name>`, then `<role> <runtime> <id>` per model in `listed`, in aligned columns (`-` for a missing
    role or runtime)."""
    rows = [(m.role or "-", m.runtime or "-", m.id) for m in listed]
    widths = [max((len(r[i]) for r in rows), default=0) for i in range(2)]
    return [f"server: {name}"] + [f"{r[0]:<{widths[0]}}  {r[1]:<{widths[1]}}  {r[2]}" for r in rows]


def model(client: openai.OpenAI, model_id: str) -> dict[str, Any]:
    """`GET /v1/models/{id}`: the model's `kind`, `role`, `test`, `entry` and a speech model's `voices`, those it
    has (an Ollama model: `kind` and `role`); the whole object when it has none of them."""
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


@dataclass(frozen=True)
class Job:
    """A job of `GET /v1/jobs`: its id, state (queued, running), role (None when the server names none), model,
    creation time (Unix seconds) and whether a cancel was asked."""

    id: str
    state: str
    role: str | None
    model: str
    created_at: float
    cancelled: bool

    @classmethod
    def of(cls, data: dict[str, Any]) -> Job:
        return cls(data["id"], data["state"], data.get("role"), data["model"], float(data["created_at"]),
                   bool(data.get("cancelled")))


def _jobs(got: dict[str, Any]) -> list[Job]:
    return [Job.of(j) for j in got.get("data") or []]


def jobs(client: openai.OpenAI) -> list[Job]:
    """The queued and running jobs of the server (`GET /v1/jobs`), oldest first."""
    with answered():
        return _jobs(client.get("/jobs", cast_to=object))


def cancel(client: openai.OpenAI, job_id: str) -> Job:
    """Cancel the job `job_id` (`DELETE /v1/jobs/{id}`); the job as the server answers it. `ClientError` (HTTP
    404 `job_not_found`) when no such job is queued or running."""
    with answered():
        return Job.of(client.delete(f"/jobs/{job_id}", cast_to=object))


def cancel_all(client: openai.OpenAI) -> list[Job]:
    """Cancel every job of the server (`DELETE /v1/jobs`); the cancelled jobs."""
    with answered():
        return _jobs(client.delete("/jobs", cast_to=object))


def job_lines(listed: list[Job], now: float) -> list[str]:
    """`<id> <state> <role> <model> <age>` per job, in aligned columns: `-` for a missing role, the age since the
    job was created at `now` (Unix seconds) as `<s>s`, and `(cancelling)` after a running job with a cancel asked."""
    rows = [(j.id, j.state, j.role or "-", j.model, f"{max(0.0, now - j.created_at):.0f}s"
             + (" (cancelling)" if j.cancelled and j.state == "running" else "")) for j in listed]
    widths = [max((len(r[i]) for r in rows), default=0) for i in range(4)]
    return [" ".join(f"{r[i]:<{widths[i]}}" for i in range(4)) + f" {r[4]}" for r in rows]


def image_file(image: bytes) -> tuple[str, bytes, str]:
    """The multipart file of an image: (name, bytes, media type), PNG unless the bytes are JPEG."""
    return ("image.jpg", image, "image/jpeg") if image[:3] == b"\xff\xd8\xff" else ("image.png", image, "image/png")


def video(client: openai.OpenAI, model_id: str, image: bytes | None, prompt: str, *, seconds: float | None = None,
          aspect: float | None = None, size: str | None = None, seed: int | None = None,
          on_status: Callable[[Video], None] | None = None) -> bytes:
    """The MP4 of a video job (`POST /v1/videos`) of `image` (PNG or JPEG bytes) animated as `prompt` describes,
    or with no image of `prompt` alone (no `input_reference`), polled until it completes; `on_status` gets the job at creation and at each change of status. `ClientError`
    with the job's error when it fails."""
    extra = {k: v for k, v in (("aspect", aspect), ("seed", seed)) if v is not None}
    with video_calls():
        job = client.videos.create(model=model_id, prompt=prompt, input_reference=image_file(image) if image is not None else omit,
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
    p.add_argument("--url", help="the server's /v1 base URL")
    p.add_argument("--provider", help="a provider of config.yaml of kind openai whose base_url is the server's /v1 "
                                      "(default model_client.provider, else http://localhost:<model_server.port>/v1)")
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("models", help="the models with their role and runtime, or one model's kind, role and entry")
    m.add_argument("--tests", action="store_true", help="also list the test models")
    m.add_argument("id", nargs="?")
    s = sub.add_parser("status", help="the status of a video job")
    s.add_argument("id")
    sub.add_parser("jobs", help="the queued and running jobs of the server")
    c = sub.add_parser("cancel", help="cancel a job of the server, or every job")
    which = c.add_mutually_exclusive_group(required=True)
    which.add_argument("id", nargs="?", help="the job's id, as `jobs` lists it (a video job's is the video's id)")
    which.add_argument("--all", action="store_true", help="cancel every queued and running job")
    v = sub.add_parser("video", help="an MP4 of a prompt, or of an image animated as the prompt describes")
    v.add_argument("--model", required=True)
    v.add_argument("--image", type=Path, help="the first frame, PNG or JPEG (optional: without it the video comes "
                   "from the prompt alone, on a model whose server entry sets `text_pipeline`)")
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
    url, name = server(args.url, args.provider)
    client = connect(url)
    if args.command == "models":
        if args.id:
            print(yaml.safe_dump(model(client, args.id), sort_keys=False), end="")
        else:
            print("\n".join(model_lines(name, models(client, args.tests))))
        return
    if args.command == "status":
        print(status_line(status(client, args.id)))
        return
    if args.command in ("jobs", "cancel"):
        if args.command == "jobs":
            listed = jobs(client)
        else:
            listed = cancel_all(client) if args.all else [cancel(client, args.id)]
        lines = job_lines(listed, time.time())
        if lines:
            print("\n".join(lines))
        return
    ext = {"video": "mp4", "image": "png", "speech": "wav"}[args.command]
    path = output_path(args.output, args.model, ext, Path.cwd(), datetime.now())
    start = time.monotonic()
    if args.command == "video":
        data = video(client, args.model, args.image.read_bytes() if args.image else None, args.prompt, seconds=args.seconds,
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
