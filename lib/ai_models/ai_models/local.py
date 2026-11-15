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
`max_frames` (see `video`); a presenter model `pipeline`, `fps`, `buckets`, `audio_rate` and `output` (see
`video`, `present`). `pipeline` may name a `ModularPipeline` class. The device is CUDA, else MPS; `to_device` moves the weights there.
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
import stat
import sys
import tempfile
import threading
import time
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
# After waiting for the lock: how long to wait for the previous holder to exit, and then for its memory to come back
# before a load is refused. The OS releases the lock file before the process exits and before the GPU driver returns
# its memory (docs/ai_models.md, Local model memory).
SETTLE_SECONDS = 10.0
SETTLE_POLL_SECONDS = 0.5
SETTLE_BYTES = 0.5 * GB  # `wait_for_settled_memory`: a rise below this between two readings counts as settled


def device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    raise AIModelsError(f"local models need a CUDA or Apple MPS GPU; torch {torch.__version__} sees neither")


def pipeline(repo: str, inpaint: str | None = None, *, cls: str = "DiffusionPipeline", skip: Sequence[str] = ()):
    """The loaded pipeline of `repo` in bfloat16, or the `inpaint` pipeline class over its modules.
    `cls` is the diffusers class to load: a `DiffusionPipeline` class (`model_index.json`), or a `ModularPipeline`
    class (`modular_model_index.json`, loaded with `load_components`, `_modular`); the components in `skip` are
    loaded as None (a modular pipeline: not loaded). A load first takes
    the lock (`hold_lock`), caps the CUDA allocator (`cap_memory`) and checks the weights against the free
    memory (`check_memory`). After waiting for the lock, a check that fails reads the free memory again for up to
    `SETTLE_SECONDS` (`wait_for_memory`), while the previous holder's memory comes back."""
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
        waited = hold_lock()
        try:
            dev = device()
            free = free_memory(dev)
            cap_memory(dev, free)
            klass = getattr(diffusers, cls)
            if issubclass(klass, diffusers.ModularPipeline):
                pipe = _modular(klass, repo, skip)
            else:
                pipe = _from_pretrained(klass, repo, dtype=torch.bfloat16, **dict.fromkeys(skip))
            weights = weight_bytes(pipe.components.values())
            if waited and weights > free:
                free = wait_for_memory(dev, weights)
                cap_memory(dev, free)
            check_memory(repo, weights, free)
            with out_of_memory(repo):
                _pipes[key] = to_device(pipe, dev)
        except BaseException:
            if not _pipes:
                release_lock()
            raise
        return _pipes[key]


def hold_lock() -> bool:
    """Take the exclusive lock `LOCK_FILE` in the system temporary directory, once per process, and keep it until
    the process exits (the OS releases it then, also after a crash). The holder writes its PID to `PID_FILE`
    beside it. Another process that holds the lock makes this one wait, with a line on stderr naming that PID, and
    then wait up to `SETTLE_SECONDS` for that process to exit. True when this call waited."""
    global _lock
    if _lock is not None:
        return False
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
        wait_for_exit(holder)
        waited = True
    else:
        waited = False
    _lock = lock
    try:
        pid_file.write_text(str(os.getpid()))
    except OSError:  # a file another user wrote; the PID only helps find a stuck holder
        pass
    return waited


def wait_for_exit(pid: str) -> None:
    """Wait up to `SETTLE_SECONDS` for process `pid` (text from `PID_FILE`) to exit (gone, or a zombie that holds
    no memory); an unreadable PID or this process returns at once."""
    import psutil

    if not pid.isdigit() or int(pid) == os.getpid():
        return
    deadline = time.monotonic() + SETTLE_SECONDS
    while time.monotonic() < deadline:
        try:
            if psutil.Process(int(pid)).status() == psutil.STATUS_ZOMBIE:
                return
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        time.sleep(SETTLE_POLL_SECONDS)


def wait_for_memory(dev: str, need: int) -> int:
    """The device's free memory, read every `SETTLE_POLL_SECONDS` until it reaches `need` bytes or
    `SETTLE_SECONDS` pass; the last reading."""
    deadline = time.monotonic() + SETTLE_SECONDS
    while (free := free_memory(dev)) < need and time.monotonic() < deadline:
        time.sleep(SETTLE_POLL_SECONDS)
    return free


def wait_for_settled_memory(dev: str) -> int:
    """The device's free memory, read every `SETTLE_POLL_SECONDS` until a reading rises less than `SETTLE_BYTES`
    over the one before or `SETTLE_SECONDS` pass; the last reading. For a load whose size is not known before it
    starts (a vLLM-Omni server), after waiting for the lock, while the previous holder's memory comes back."""
    deadline = time.monotonic() + SETTLE_SECONDS
    free = free_memory(dev)
    while time.monotonic() < deadline:
        time.sleep(SETTLE_POLL_SECONDS)
        last, free = free, free_memory(dev)
        if free - last < SETTLE_BYTES:
            break
    return free


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
    if integrated(dev):
        return psutil.virtual_memory().available
    return torch.cuda.mem_get_info()[0]


PAGE_CACHE_MIN_BYTES = 64 * 2**20  # `drop_page_cache` skips files smaller than this


def model_dirs() -> list[Path]:
    """The directories that hold model weights: the Hugging Face hub cache (`HF_HUB_CACHE`, under `HF_HOME` of the
    config) and every `repo` of the config's providers and `diffusers` models that is a local directory."""
    from huggingface_hub import constants

    try:
        cfg = config.load()
    except ConfigError:
        cfg = {}
    specs = [*(cfg.get("providers") or {}).values(), *(cfg.get("diffusers") or {}).values()]
    repos = [Path(str(s["repo"])).expanduser() for s in specs if isinstance(s, dict) and s.get("repo")]
    dirs = [Path(constants.HF_HUB_CACHE), *(r for r in repos if r.is_dir())]
    return [d for d in dict.fromkeys(dirs) if d.is_dir()]


def drop_page_cache(dirs: Iterable[Path], min_bytes: int = PAGE_CACHE_MIN_BYTES) -> int:
    """Ask Linux to drop the clean page cache of every regular file of at least `min_bytes` under `dirs`
    (`posix_fadvise` `POSIX_FADV_DONTNEED`; symlinks are not followed); the bytes of the files advised. It changes
    no file and needs no privilege; pages a process has mapped or dirty pages stay. A no-op (0) without
    `posix_fadvise` (macOS, Windows). On an integrated GPU `torch.cuda.mem_get_info` counts the page cache as used,
    and vLLM checks its share against that figure, so a server start calls this before it measures."""
    if not hasattr(os, "posix_fadvise"):
        return 0
    done = 0
    for top in dirs:
        for root, _subdirs, files in os.walk(top):
            for f in files:
                p = os.path.join(root, f)
                try:
                    st = os.lstat(p)
                    if not stat.S_ISREG(st.st_mode) or st.st_size < min_bytes:
                        continue
                    fd = os.open(p, os.O_RDONLY)
                except OSError:
                    continue
                try:
                    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                    done += st.st_size
                except OSError:
                    pass
                finally:
                    os.close(fd)
    return done


def integrated(dev: str) -> bool:
    """True for an integrated CUDA GPU under Linux (one that allocates system memory)."""
    import torch

    return (dev == "cuda" and sys.platform == "linux"
            and torch.cuda.get_device_properties(torch.cuda.current_device()).is_integrated)


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


def _modular(cls, repo: str, skip: Sequence[str]):
    """The `ModularPipeline` class `cls` of `repo` (`modular_model_index.json`) with its components loaded in
    bfloat16 on the CPU, except those in `skip`."""
    import torch

    pipe = cls.from_pretrained(repo)
    pipe.load_components([n for n in pipe.pretrained_component_names if n not in skip], dtype=torch.bfloat16)
    return pipe


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


def audio_rate(pipe) -> int:
    """The sample rate of the audio a pipeline returns: its vocoder's output rate (`output_sampling_rate`, else
    `sampling_rate` of the vocoder config), else the pipeline's `audio_sample_rate`, else its `sample_rate`."""
    vocoder = getattr(getattr(pipe, "vocoder", None), "config", None)
    for rate in (getattr(vocoder, "output_sampling_rate", None), getattr(vocoder, "sampling_rate", None),
                 getattr(pipe, "audio_sample_rate", None), getattr(pipe, "sample_rate", None)):
        if rate:
            return int(rate)
    raise AIModelsError(f"{type(pipe).__name__} returns audio but names no sample rate")


def animate(name: str, image: bytes, prompt: str, *, seconds: float, width: int | None = None,
            height: int | None = None, aspect: float | None = None, seed: int | None = None) -> bytes:
    """An MP4 (H.264) of the image-to-video model `diffusers.<name>`, at `width` x `height`, else
    the model's size, reshaped to `aspect` when given (`video.clip_size`). The image is cropped to
    the clip's aspect ratio and scaled to its size. When the pipeline output has `audio` (a sound track generated
    with the frames, (channels, samples) or (samples,) per video, a tensor or an array), the clip carries it as an AAC
    stream at the pipeline's rate (`audio_rate`); else it has no audio stream. Encoded with diffusers' `encode_video`."""
    from diffusers.utils import encode_video
    from PIL import Image, ImageOps

    from .video import clip_size, frame_count, video_spec

    spec = video_spec(name)
    w, h = clip_size(spec, width, height, aspect)
    frames_n = frame_count(seconds, spec["fps"], spec["frame_step"], spec["max_frames"])
    extra: dict[str, Any] = {"width": w, "height": h, "num_frames": frames_n, "seed": seed}
    pipe = pipeline(spec["repo"], cls=spec["pipeline"], skip=spec.get("skip") or ())
    still = ImageOps.fit(Image.open(io.BytesIO(image)).convert("RGB"), (w, h))
    with out_of_memory(spec["repo"]):
        result = pipe(image=still, prompt=prompt, output_type="np", **pipe_kwargs(spec, extra))
    audio = getattr(result, "audio", None)
    track = {} if audio is None else {"audio": waveform(audio[0]), "audio_sample_rate": audio_rate(pipe)}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clip.mp4"
        encode_video(result.frames[0], fps=spec["fps"], output_path=str(out), **track)
        return out.read_bytes()


def waveform(audio):
    """A float32 CPU tensor (channels, samples) of `audio`: a tensor or array, (channels, samples) or (samples,)."""
    import torch

    t = torch.as_tensor(audio).float().cpu()
    return t[None] if t.ndim == 1 else t


def read_audio(data: bytes, rate: int | None = None, layout: str | None = None):
    """(waveform, rate) of the audio file `data` (any format FFmpeg reads, decoded with PyAV): a float32 tensor
    (channels, samples), resampled to `rate` and mixed to `layout` (`"mono"`, `"stereo"`) when given, else at the
    file's own rate and channels."""
    import av
    import numpy as np
    import torch

    with av.open(io.BytesIO(data)) as f:
        stream = f.streams.audio[0]
        rate = rate or stream.rate
        layout = layout or stream.layout.name
        resampler = av.AudioResampler(format="fltp", layout=layout, rate=rate)
        chunks = [r.to_ndarray() for frame in f.decode(stream) for r in resampler.resample(frame)]
        chunks += [r.to_ndarray() for r in resampler.resample(None)]
    if not chunks:
        raise AIModelsError("the audio file has no samples")
    return torch.from_numpy(np.concatenate(chunks, axis=1)), rate


PRESENTER_CENTERING = (0.5, 0.3)  # `ImageOps.fit` centring of the bucket crop: biased upward, to keep the head


def presenter_still(buckets: list[list[int]], image: bytes, aspect: float | None = None):
    """`image` as an RGB PIL image cropped to the bucket of `buckets` nearest `aspect` (default the image's,
    `video.bucket`) and scaled to it; the crop keeps more of the top (`PRESENTER_CENTERING`)."""
    from PIL import Image, ImageOps

    from .video import bucket

    still = Image.open(io.BytesIO(image)).convert("RGB")
    return ImageOps.fit(still, bucket(buckets, aspect or still.width / still.height), centering=PRESENTER_CENTERING)


def present(name: str, image: bytes, speech: bytes, *, aspect: float | None = None, prompt: str | None = None,
            seed: int | None = None) -> bytes:
    """An MP4 (H.264, AAC) of the presenter model `diffusers.<name>`: the person in `image` speaks `speech` (an audio
    file), as long as the speech, with the speech as its sound track (AAC, at the file's sample rate). The size is
    the model's bucket nearest `aspect` (width / height; default the image's, `video.bucket`); the image is cropped
    to it, biased upward, and scaled (`presenter_still`). The model takes the speech mono at its `audio_rate`;
    `prompt` replaces the model's default prompt when given. Encoded with diffusers' `encode_video`."""
    from diffusers.utils import encode_video

    from .video import presenter_spec

    spec = presenter_spec(name)
    still = presenter_still(spec["buckets"], image, aspect)
    w, h = still.size
    drive, _ = read_audio(speech, int(spec["audio_rate"]), "mono")
    track, rate = read_audio(speech)
    extra: dict[str, Any] = {"width": w, "height": h, "fps": spec["fps"], "seed": seed}
    if prompt:
        extra["prompt"] = prompt
    pipe = pipeline(spec["repo"], cls=spec["pipeline"], skip=spec.get("skip") or ())
    with out_of_memory(spec["repo"]):
        frames = pipe(image=still, audio=drive[0].numpy(), output=spec["output"], output_type="np",
                      **pipe_kwargs(spec, extra))[0]
    seconds = len(frames) / spec["fps"]
    track = track[:, : round(seconds * rate)]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "presenter.mp4"
        encode_video(frames, fps=spec["fps"], output_path=str(out), audio=track, audio_sample_rate=rate)
        return out.read_bytes()
