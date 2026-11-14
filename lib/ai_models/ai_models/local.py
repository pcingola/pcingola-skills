"""Local images and music in process with `diffusers` (extra `ai-models[diffusers]`), and the
pipeline cache and device of every local model (video: `video`).

A model is `diffusers.<name>` in the config: `repo` (a Hugging Face repo, loaded
with `DiffusionPipeline.from_pretrained`; weights go to the Hugging Face cache),
`steps`, `guidance` (optional: without it no `guidance_scale` is passed), `inpaint` (a
diffusers pipeline class for mask edits, built over the loaded modules with `from_pipe`),
`args` (optional: more pipeline call arguments, after steps and guidance and before the
caller's) and `skip` (optional: pipeline components loaded as None). A music model also has
`duration_arg` and `lyrics_arg`: the names of the pipeline call arguments that take the
length in seconds and the lyrics; without one, the model does not take that option. A video model also has
`pipeline` (the class to load), `fps`, `size_multiple`, `frame_step`, `width`, `height` and
`max_frames` (see `video`). The device is CUDA, else MPS; `to_device` moves the weights there.
Pipelines stay loaded for the life of the process. torch and diffusers are
imported only here.

Memory: the first load takes an exclusive file lock (`hold_lock`) that the process keeps until it exits, so
one process at a time holds local models. A load whose weights exceed the device's free memory raises
`AIModelsError` before any weight moves to the device (`check_memory`); on CUDA the allocator is capped at
the memory free before the load (`cap_memory`), and an out-of-memory error becomes the same `AIModelsError`
(`out_of_memory`).
"""

from __future__ import annotations

import asyncio
import io
import itertools
import json
import os
import sys
import tempfile
import threading
import urllib.request
import wave
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai.exceptions import UserError
from pydantic_ai.images import GeneratedImage, ImageGenerationModel, ImageGenerationResult
from pydantic_ai.messages import BinaryImage

from . import config
from .errors import AIModelsError, ConfigError

_pipes: dict[str, Any] = {}
_lock = None  # the FileLock this process holds once it loads a model
_load_lock = threading.RLock()  # one thread at a time takes the FileLock and fills _pipes
LOCK_FILE = "ai-models-local.lock"
PID_FILE = "ai-models-local.pid"
GB = 1e9


def device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    raise AIModelsError(f"local models need a CUDA or Apple MPS GPU; torch {torch.__version__} sees neither")


def pipeline(repo: str, inpaint: str | None = None, *, cls: str = "DiffusionPipeline", skip: Sequence[str] = ()):
    """The loaded pipeline of `repo` in bfloat16, or the `inpaint` pipeline class over its modules.
    `cls` is the diffusers class to load; the components in `skip` are loaded as None. A load first takes
    the lock (`hold_lock`), caps the CUDA allocator (`cap_memory`) and checks the weights against the free
    memory (`check_memory`)."""
    import diffusers
    import torch

    skip = tuple(skip)
    key = f"{repo}#{inpaint or ''}#{cls}#{','.join(skip)}"
    with _load_lock:
        if key in _pipes:
            return _pipes[key]
        if inpaint:
            # from_pipe casts the shared modules to float32 unless given the loaded dtype
            _pipes[key] = getattr(diffusers, inpaint).from_pipe(pipeline(repo, cls=cls, skip=skip), dtype=torch.bfloat16)
            return _pipes[key]
        hold_lock()
        try:
            dev = device()
            free = free_memory(dev)
            cap_memory(dev, free)
            pipe = _from_pretrained(getattr(diffusers, cls), repo, dtype=torch.bfloat16, **dict.fromkeys(skip))
            check_memory(repo, weight_bytes(pipe.components.values()), free)
            with out_of_memory(repo):
                _pipes[key] = to_device(pipe, dev)
        except BaseException:
            if not _pipes:
                release_lock()
            raise
        return _pipes[key]


def hold_lock() -> None:
    """Take the exclusive lock `LOCK_FILE` in the system temporary directory, once per process, and keep it until
    the process exits (the OS releases it then, also after a crash). The holder writes its PID to `PID_FILE`
    beside it. Another process that holds the lock makes this one wait, with a line on stderr naming that PID."""
    global _lock
    if _lock is not None:
        return
    from filelock import FileLock, Timeout

    lock = FileLock(Path(tempfile.gettempdir()) / LOCK_FILE, mode=0o666, thread_local=False)
    pid_file = Path(tempfile.gettempdir()) / PID_FILE
    try:
        lock.acquire(timeout=0)
    except Timeout:
        try:
            holder = pid_file.read_text().strip()
        except OSError:
            holder = "unknown"
        print(f"ai_models: waiting for process {holder}, which holds local models (lock {lock.lock_file})",
              file=sys.stderr, flush=True)
        lock.acquire()
    _lock = lock
    try:
        pid_file.write_text(str(os.getpid()))
    except OSError:  # a file another user wrote; the PID only helps find a stuck holder
        pass


def release_lock() -> None:
    """Release the lock of `hold_lock` (after a load that failed while no pipeline was loaded)."""
    global _lock
    if _lock is not None:
        _lock.release()
        _lock = None


def weight_bytes(modules: Iterable[Any]) -> int:
    """The bytes of every parameter and buffer of the torch modules in `modules`; other objects count 0."""
    import torch

    return sum(t.numel() * t.element_size() for m in modules if isinstance(m, torch.nn.Module)
               for t in itertools.chain(m.parameters(), m.buffers()))


def free_memory(dev: str) -> int:
    """Bytes the device can still allocate. CUDA: `torch.cuda.mem_get_info`; on an integrated GPU under Linux,
    the system's available memory (`psutil`, `MemAvailable`), because the device allocates system memory,
    reclaims the page cache, and `mem_get_info` counts that cache as used. MPS: the recommended maximum minus what
    the driver holds for this process, at most the system's available memory, which other processes share."""
    import psutil
    import torch

    if dev == "mps":
        return min(torch.mps.recommended_max_memory() - torch.mps.driver_allocated_memory(),
                   psutil.virtual_memory().available)
    if sys.platform == "linux" and torch.cuda.get_device_properties(torch.cuda.current_device()).is_integrated:
        return psutil.virtual_memory().available
    return torch.cuda.mem_get_info()[0]


def cap_memory(dev: str, free: int) -> None:
    """On CUDA, cap this process's allocator at `free` bytes plus what it already reserved, so growth past the
    memory free at load time raises `torch.OutOfMemoryError` instead of exhausting a shared pool. MPS has its
    own limit (`PYTORCH_MPS_HIGH_WATERMARK_RATIO`)."""
    if dev != "cuda":
        return
    import torch

    total = torch.cuda.mem_get_info()[1]
    torch.cuda.set_per_process_memory_fraction(min(1.0, (free + torch.cuda.memory_reserved()) / total))


def check_memory(repo: str, weights: int, free: int) -> None:
    """`memory_error` when `weights` bytes exceed `free`."""
    if weights > free:
        raise memory_error(repo, f"its weights need {weights / GB:.1f} GB and the device has {free / GB:.1f} GB free")


@contextmanager
def out_of_memory(repo: str) -> Iterator[None]:
    """Turn a `torch.OutOfMemoryError` of a load or call of `repo` into `memory_error`."""
    import torch

    try:
        yield
    except torch.OutOfMemoryError as e:
        free = free_memory(device())
        raise memory_error(repo, f"it ran out of memory with {free / GB:.1f} GB free ({e})") from e


class _Resident(BaseModel):
    """A model Ollama holds in memory (`/api/ps`)."""

    name: str
    size: int


class _Ps(BaseModel):
    models: list[_Resident] = []


def memory_error(repo: str, sizes: str) -> AIModelsError:
    """The error for model `repo`, with `sizes` and the models each `ollama` provider of the config holds."""
    held = [f"{name} ({size / GB:.1f} GB)" for name, size in resident_ollama_models()]
    where = f"; Ollama holds {', '.join(held)}: unload them (`ollama stop <model>`) and retry" if held else ""
    return AIModelsError(f"local model {repo}: {sizes}{where}")


def resident_ollama_models() -> list[tuple[str, int]]:
    """(provider:model, bytes) of each model loaded in an `ollama` provider of the config (`GET /api/ps`); a
    missing config or a server that does not answer contributes nothing."""
    from .models import base_url
    from .tls import ssl_verify

    try:
        providers = config.load().get("providers") or {}
    except AIModelsError:
        return []
    out = []
    for name, spec in providers.items():
        if not isinstance(spec, dict) or spec.get("kind") != "ollama":
            continue
        url = base_url(spec).rstrip("/").removesuffix("/v1") + "/api/ps"
        req = urllib.request.Request(url)
        if key := spec.get("api_key"):
            req.add_header("Authorization", f"Bearer {key}")
        try:
            with urllib.request.urlopen(req, timeout=2, context=ssl_verify() if url.startswith("https") else None) as r:
                ps = _Ps.model_validate(json.load(r))
        except (OSError, ValueError):
            continue
        out.extend((f"{name}:{m.name}", m.size) for m in ps.models)
    return out


def _from_pretrained(cls, repo: str, **kwargs):
    """`cls.from_pretrained` from the cached snapshot folder of `repo`, else with a download.
    Loading the repository id fetches every weight file of each component folder, including
    alternative shardings the pipeline never reads, and `local_files_only` refuses a snapshot
    that lacks any of them; a folder load reads only the files the pipeline names."""
    from huggingface_hub import try_to_load_from_cache

    index = try_to_load_from_cache(repo, "model_index.json")
    if isinstance(index, str):
        try:
            return cls.from_pretrained(str(Path(index).parent), **kwargs)
        except (OSError, ValueError):
            pass
    return cls.from_pretrained(repo, **kwargs)


def to_device(pipe, dev: str):
    """`pipe` moved to `dev`, each CPU weight first copied to process memory. `from_pretrained` leaves the
    weights memory-mapped from the safetensors files, and a host-to-device copy from a file mapping is
    about 100 times slower than from process memory on a unified-memory GPU (docs/ai_models.md)."""
    import torch

    with torch.no_grad():
        for module in pipe.components.values():
            if isinstance(module, torch.nn.Module):
                for t in itertools.chain(module.parameters(), module.buffers()):
                    if t.device.type == "cpu":
                        t.data = t.data.clone().to(dev)
    return pipe.to(dev)


def pipe_kwargs(spec: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Steps and guidance of the model (each only when set), its `args`, then `extra`; `seed` becomes a torch
    generator."""
    kwargs = {k: v for k, v in (("num_inference_steps", spec.get("steps")),
                                ("guidance_scale", spec.get("guidance"))) if v is not None}
    kwargs.update(spec.get("args") or {})
    kwargs.update(extra)
    if (seed := kwargs.pop("seed", None)) is not None:
        import torch

        dev = device()
        kwargs["generator"] = torch.Generator("cpu" if dev == "mps" else dev).manual_seed(int(seed))
    return kwargs


def repaint_mask(mask: bytes):
    """An OpenAI mask (transparent = edit) as a diffusers mask (white = repaint)."""
    from PIL import Image

    return Image.open(io.BytesIO(mask)).convert("RGBA").getchannel("A").point(lambda a: 255 if a == 0 else 0)


class DiffusersImageModel(ImageGenerationModel):
    """A Pydantic-AI image model on a local diffusers pipeline. Reference images go as
    `image`; with a `mask`, the first goes to the `inpaint` pipeline. `settings`:
    `dimensions` (width, height) and `extra_body` (more pipeline arguments, `seed`)."""

    def __init__(self, name: str, *, mask: bytes | None = None, settings=None) -> None:
        super().__init__(settings=settings)
        self._name = name
        self.spec = config.diffusers_model(name)
        self.mask = mask

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def system(self) -> str:
        return "diffusers"

    async def generate(self, prompt: str, *, images=None, settings=None) -> ImageGenerationResult:
        prompt, images, settings = self.prepare_generate(prompt, images=images, settings=settings)
        if any(not isinstance(i, BinaryImage) for i in images):
            raise UserError("local image models take reference images as BinaryImage")
        if self.mask is not None and not images:
            raise UserError("a mask needs a reference image to edit")
        if self.mask is not None and not self.spec.get("inpaint"):
            raise ConfigError(f"diffusers model {self._name!r} has no `inpaint` pipeline for a mask")
        return await asyncio.to_thread(self._run, prompt, [i.data for i in images], settings)

    def _run(self, prompt: str, refs: list[bytes], settings: dict[str, Any]) -> ImageGenerationResult:
        kwargs = pipe_kwargs(self.spec, dict(settings.get("extra_body") or {}))
        if dims := settings.get("dimensions"):
            kwargs["width"], kwargs["height"] = dims
        if refs:
            from PIL import Image
        pics = [Image.open(io.BytesIO(r)).convert("RGB") for r in refs]
        if self.mask is not None:
            kwargs.update(image=pics[0], mask_image=repaint_mask(self.mask))
            if len(pics) > 1:
                kwargs["image_reference"] = pics[1:]
        elif pics:
            kwargs["image"] = pics
        pipe = pipeline(self.spec["repo"], self.spec.get("inpaint") if self.mask is not None else None,
                        skip=self.spec.get("skip") or ())
        with out_of_memory(self.spec["repo"]):
            images = pipe(prompt=prompt, **kwargs).images
        out = []
        for img in images:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            out.append(GeneratedImage(BinaryImage(data=buf.getvalue(), media_type="image/png"), output_format="png"))
        return ImageGenerationResult(images=out, prompt=prompt, model_name=self._name, provider_name="diffusers")


class DiffusersMusicModel:
    """A local music pipeline: `prompt` and the arguments named by `duration_arg` and `lyrics_arg` in,
    `.audios` and `sample_rate` out."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.spec = config.diffusers_model(name)

    def compose(self, prompt: str, *, seconds: float | None = None, lyrics: str | None = None,
                seed: int | None = None) -> bytes:
        """A 16-bit WAV file of the track at the pipeline's sample rate; without `seconds`, the pipeline's own length."""
        import torch

        extra: dict[str, Any] = {"seed": seed}
        for key, value in (("duration_arg", None if seconds is None else float(seconds)), ("lyrics_arg", lyrics)):
            if value is None:
                continue
            if not (arg := self.spec.get(key)):
                raise ConfigError(f"diffusers model {self.name!r} has no `{key}` for {key.removesuffix('_arg')}")
            extra[arg] = value
        pipe = pipeline(self.spec["repo"], skip=self.spec.get("skip") or ())
        with out_of_memory(self.spec["repo"]):
            audio = pipe(prompt=prompt, output_type="pt", **pipe_kwargs(self.spec, extra)).audios[0]  # (channels, samples)
        pcm = (audio.float().clamp(-1, 1) * 32767).to(torch.int16).T.contiguous().cpu().numpy().tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(audio.shape[0])
            w.setsampwidth(2)
            w.setframerate(int(pipe.sample_rate))
            w.writeframes(pcm)
        return buf.getvalue()


def animate(name: str, image: bytes, prompt: str, *, seconds: float, width: int | None = None,
            height: int | None = None, aspect: float | None = None, seed: int | None = None) -> bytes:
    """An MP4 (H.264, no audio) of the image-to-video model `diffusers.<name>`, at `width` x `height`, else
    the model's size, reshaped to `aspect` when given (`video.clip_size`). The image is cropped to
    the clip's aspect ratio and scaled to its size. An audio track the pipeline generates is dropped."""
    from diffusers.utils import export_to_video
    from PIL import Image, ImageOps

    from .video import clip_size, frame_count, video_spec

    spec = video_spec(name)
    w, h = clip_size(spec, width, height, aspect)
    frames_n = frame_count(seconds, spec["fps"], spec["frame_step"], spec["max_frames"])
    extra: dict[str, Any] = {"width": w, "height": h, "num_frames": frames_n, "seed": seed}
    pipe = pipeline(spec["repo"], cls=spec["pipeline"], skip=spec.get("skip") or ())
    still = ImageOps.fit(Image.open(io.BytesIO(image)).convert("RGB"), (w, h))
    with out_of_memory(spec["repo"]):
        frames = pipe(image=still, prompt=prompt, output_type="np", **pipe_kwargs(spec, extra)).frames[0]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clip.mp4"
        export_to_video(list(frames), str(out), fps=spec["fps"])
        return out.read_bytes()
