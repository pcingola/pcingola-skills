"""Local images and music in process with `diffusers` (extra `ai-models[diffusers]`), and the
pipeline cache and device of every local model (video: `video`).

A model is `providers.<p>.models.<name>` of a diffusers provider in the config (`DiffusersModel`): `repo`
(a Hugging Face repo, loaded with `DiffusionPipeline.from_pretrained`, weights in the Hugging Face cache; or a local
folder, an absolute or `~` path),
`steps`, `guidance` (optional: without it no `guidance_scale` is passed), `inpaint` (a
diffusers pipeline class for mask edits, built over the loaded modules with `from_pipe`),
`args` (optional: more pipeline call arguments, after steps and guidance and before the
caller's) and `skip` (optional: pipeline components loaded as None). A music model also has
`duration_arg` and `lyrics_arg`: the names of the pipeline call arguments that take the
length in seconds and the lyrics; without one, the model does not take that option. It may also have
`min_crest_db` (`music.min_crest_db`; not read here), the crest factor below which the music skill sends the request
again. A video model also has
`pipeline` (the class to load), `fps`, `size_multiple`, `frame_step`, `width`, `height` and
`max_frames`, and optionally `text_pipeline` (see `video`); a presenter model `pipeline`, `fps`, `buckets`, `audio_rate` and `output` (see
`video`, `present`). `pipeline` may name a `ModularPipeline` class. The device is CUDA, else MPS; `to_device` moves the weights there.
Pipelines stay loaded until the process exits or calls `unload`. torch and diffusers are
imported only here.

Memory: the first load takes an exclusive file lock (`hold_lock`) that the process keeps until it exits or calls
`unload`, so one process at a time holds local models. A load of a model whose entry sets `memory` (GB at its peak)
is refused with `AIModelsError` when the free memory stays below it (`check_free`); a load whose weights exceed the
device's free memory raises `AIModelsError` before any weight moves to the device (`check_memory`); on CUDA the
allocator is capped at the memory free before the load (`cap_memory`), and an out-of-memory error becomes the same
`AIModelsError` (`out_of_memory`). `unload_model` drops one model and releases the lock once no model that took it
is loaded.
"""

from __future__ import annotations

import asyncio
import csv
import gc
import io
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import plugin_settings
from plugin_settings import DiffusersModel, DiffusersRole, DiffusersVideoModel, ProviderKind
from pydantic import BaseModel
from pydantic_ai.exceptions import UserError
from pydantic_ai.images import GeneratedImage, ImageGenerationModel, ImageGenerationResult
from pydantic_ai.messages import BinaryImage

from . import config
from .errors import AIModelsError, ConfigError, LocalMemoryError

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


def device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    raise AIModelsError(f"local models need a CUDA or Apple MPS GPU; torch {torch.__version__} sees neither")


def pipeline(repo: str, over: str | None = None, *, cls: str = "DiffusionPipeline", skip: Sequence[str] = (),
             memory: float | None = None):
    """The loaded pipeline of `repo` in bfloat16, or the pipeline class `over` built over its modules with
    `from_pipe` (an `inpaint` class, a video model's `text_pipeline`). `repo` is a
    Hugging Face repository id or a local folder (`local_folder`), which is loaded as is, with no cache lookup.
    `cls` is the diffusers class to load: a `DiffusionPipeline` class (`model_index.json`), or a `ModularPipeline`
    class (`modular_model_index.json`, loaded with `load_components`, `_modular`); the components in `skip` are
    loaded as None (a modular pipeline: not loaded). A load first takes
    the lock (`hold_lock`), checks `memory` (the entry's GB at the peak, when set) against the free memory
    (`check_free`), caps the CUDA allocator (`cap_memory`) and checks the weights against the free
    memory (`check_memory`). After waiting for the lock, a check that fails reads the free memory again for up to
    `SETTLE_SECONDS` (`wait_for_memory`), while the previous holder's memory comes back."""
    import diffusers
    import torch

    skip = tuple(skip)
    key = f"{repo}#{over or ''}#{cls}#{','.join(skip)}"
    with _load_lock:
        if key in _pipes:
            return _pipes[key]
        if over:
            # from_pipe casts the shared modules to float32 unless given the loaded dtype
            base = pipeline(repo, cls=cls, skip=skip, memory=memory)
            _pipes[key] = getattr(diffusers, over).from_pipe(base, dtype=torch.bfloat16)
            return _pipes[key]
        waited = hold_lock()
        try:
            dev = device()
            free = free_memory(dev) if memory is None else check_free(memory, repo, "its entry", dev, waited)
            cap_memory(dev, free)
            klass = getattr(diffusers, cls)
            if issubclass(klass, diffusers.ModularPipeline):
                pipe = _modular(klass, repo, skip)
            else:
                pipe = _from_pretrained(klass, repo, dev, dtype=torch.bfloat16, **dict.fromkeys(skip))
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


def lock_wait() -> float | None:
    """`local_models.lock_wait` of the config: the seconds `hold_lock` waits for another holder; None, no limit."""
    try:
        return plugin_settings.load_config().local_models.lock_wait
    except plugin_settings.ConfigFileError as e:
        raise ConfigError(str(e)) from None


def hold_lock() -> bool:
    """Take the exclusive lock `LOCK_FILE` in the system temporary directory, once per process, and keep it until
    the process exits (the OS releases it then, also after a crash) or calls `unload`. The holder writes its PID to
    `PID_FILE` beside it. Another process that holds the lock makes this one wait, with a line on stderr naming
    that PID, and then wait up to `SETTLE_SECONDS` for that process to exit (not after an `unload`, which empties
    `PID_FILE`). The wait has no limit unless `local_models.lock_wait` sets one; past it, `AIModelsError` names
    the holder's PID, the lock and the setting. True when this call waited."""
    global _lock
    if _lock is not None:
        return False
    from filelock import FileLock, Timeout

    lock = FileLock(Path(tempfile.gettempdir()) / LOCK_FILE, mode=0o666, thread_local=False)
    pid_file = Path(tempfile.gettempdir()) / PID_FILE
    try:
        lock.acquire(timeout=0)
    except Timeout:
        holder = read_pid(pid_file) or "unknown"
        print(f"ai_models: waiting for process {holder}, which holds local models (lock {lock.lock_file})",
              file=sys.stderr, flush=True)
        wait = lock_wait()
        try:
            lock.acquire(timeout=-1 if wait is None else wait)
        except Timeout:
            raise AIModelsError(f"process {holder} holds local models (lock {lock.lock_file}) and did not release "
                                f"them within {wait:g} s (local_models.lock_wait)") from None
        if read_pid(pid_file) == holder:  # released at exit; `unload` empties the file first
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


def read_pid(pid_file: Path) -> str:
    """The text of `pid_file` (`PID_FILE`), stripped; empty when it is missing or unreadable."""
    try:
        return pid_file.read_text().strip()
    except OSError:
        return ""


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


def release_lock() -> None:
    """Release the lock of `hold_lock` (after a load that failed while no pipeline was loaded, and in `unload`)."""
    global _lock
    if _lock is not None:
        _lock.release()
        _lock = None


def check_free(memory: float, repo: str, where: str, dev: str, waited: bool) -> int:
    """The free memory of `dev` once it holds `memory` GB (a model's `memory`), after waiting for the previous holder
    of the lock (`waited`, `wait_for_memory`) and for local Ollama models that unload soon (`wait_for_ollama`);
    `memory_error` naming `repo` and `where` (the entry's YAML path) when it stays below."""
    need = int(memory * GB)
    free = free_memory(dev)
    if waited and need > free:
        free = wait_for_memory(dev, need)
    if need > free:
        free = wait_for_ollama(dev, need)
    if need > free:
        raise memory_error(repo, f"it takes {memory:g} GB at its peak (`memory` of {where}) and the device has "
                           f"{free / GB:.1f} GB free")
    return free


class Cache(Protocol):
    """An in-process model cache: its length is the number of entries it holds, `clear` empties it."""

    def __len__(self) -> int: ...

    def clear(self) -> None: ...


_caches: list[Cache] = []  # every in-process model cache (`on_unload`)
_locked: list[Cache] = []  # the caches whose models take the lock (`on_unload(locked=True)`)
# One function per module that keeps loaded models: (model id, weights dir) -> the entries it dropped (`unload_model`)
_droppers: list[Callable[[str, Path | None], int]] = []


def on_unload(cache: Cache, *, locked: bool = False) -> Cache:
    """Register `cache` (a dict, or any object with `__len__` and `clear`) for `unload`; return it. Each module
    that keeps loaded models registers its cache at import; `locked` marks a cache whose models take the lock of
    `hold_lock` (diffusers, fish)."""
    _caches.append(cache)
    if locked:
        _locked.append(cache)
    return cache


def on_unload_model(drop: Callable[[str, Path | None], int]) -> Callable[[str, Path | None], int]:
    """Register `drop` for `unload_model`; return it. `drop(model_id, weights_dir)` removes the entries of model
    `model_id` from its module's cache and returns how many it removed (0 for a model of another kind)."""
    _droppers.append(drop)
    return drop


def provider_kind(model_id: str) -> str | None:
    """The provider kind of `model_id` in the config, None when its provider is missing."""
    spec = config.load().provider(config.split_id(model_id)[0])
    return None if spec is None else spec.kind


def unload_model(model_id: str, weights_dir: str | Path | None = None) -> bool:
    """Drop the loaded model `model_id` (`on_unload_model`); `weights_dir` is the weights directory a kokoro or
    chatterbox provider without `dir` loaded it from. When no model that takes the lock stays loaded, empty
    `PID_FILE` and release the lock (`unload`). True when an entry was dropped; it then collects garbage and empties
    the CUDA allocator cache when torch is imported."""
    where = None if weights_dir is None else Path(weights_dir).expanduser()
    with _load_lock:
        dropped = sum(drop(model_id, where) for drop in _droppers)
        if dropped:
            gc.collect()
            if (torch := sys.modules.get("torch")) is not None:
                torch.cuda.empty_cache()
        if not any(len(cache) for cache in _locked):
            _release_held()
    return bool(dropped)


def _release_held() -> None:
    """Empty `PID_FILE` when it names this process and release the lock of `hold_lock`; the caller holds
    `_load_lock`."""
    if _lock is not None:
        pid_file = Path(tempfile.gettempdir()) / PID_FILE
        if read_pid(pid_file) == str(os.getpid()):
            try:
                pid_file.write_text("")  # a waiter then takes the lock without waiting for this process to exit
            except OSError:
                pass
    release_lock()


def unload() -> None:
    """Drop every model this process holds: empty each cache of `on_unload`, empty `PID_FILE`, and release the lock
    of `hold_lock`, so another process loads local models at once, without waiting for this one to exit. When this
    process held the lock or a cache held an entry, it also collects garbage and empties the CUDA allocator cache
    when torch is imported (it is not imported here); otherwise there is nothing to free and it returns at once."""
    with _load_lock:
        held = _lock is not None or any(len(cache) for cache in _caches)
        for cache in _caches:
            cache.clear()
        if held:
            gc.collect()
            if (torch := sys.modules.get("torch")) is not None:
                torch.cuda.empty_cache()  # a no-op when CUDA was never initialized
        _release_held()


on_unload(_pipes, locked=True)


@on_unload_model
def _drop_pipes(model_id: str, weights_dir: Path | None) -> int:
    """Drop the pipelines of the diffusers model `model_id` (its `repo`, with any pipeline built over it);
    another model of the same `repo` shares them."""
    if provider_kind(model_id) != ProviderKind.DIFFUSERS:
        return 0
    repo = config.local_entry(model_id).repo
    keys = [k for k in _pipes if k.startswith(f"{repo}#")]
    for k in keys:
        del _pipes[k]
    return len(keys)


def weight_bytes(modules: Iterable[Any]) -> int:
    """The bytes of every parameter and buffer of the torch modules in `modules`; other objects count 0."""
    import torch

    return sum(t.numel() * t.element_size() for m in modules if isinstance(m, torch.nn.Module)
               for t in itertools.chain(m.parameters(), m.buffers()))


def free_memory(dev: str) -> int:
    """Bytes the device can still allocate. CUDA: `torch.cuda.mem_get_info`; on an integrated GPU under Linux,
    the system's available memory (`psutil`, `MemAvailable`), because the device allocates system memory,
    reclaims the page cache, and `mem_get_info` counts that cache as used. MPS: the recommended maximum minus what
    the driver holds for this process, at most the system's available memory, which other processes share. CPU
    (`"cpu"`): the system's available memory."""
    import psutil
    import torch

    if dev == "cpu":
        return psutil.virtual_memory().available
    if dev == "mps":
        return min(torch.mps.recommended_max_memory() - torch.mps.driver_allocated_memory(),
                   psutil.virtual_memory().available)
    if integrated(dev):
        return psutil.virtual_memory().available
    return torch.cuda.mem_get_info()[0]


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
    """A model Ollama holds in memory (`/api/ps`): its name, bytes and when Ollama unloads it."""

    name: str
    size: int
    expires_at: datetime | None = None


class _Ps(BaseModel):
    models: list[_Resident] = []


@dataclass
class OllamaModel:
    """A model loaded in an `ollama` provider of the config on this machine: `provider:model`, its bytes and the
    time Ollama unloads it (None when it has none)."""

    name: str
    size: int
    expires_at: datetime | None


@dataclass
class GpuProcess:
    """A process on an NVIDIA GPU: its PID, executable path and bytes of GPU memory."""

    pid: int
    name: str
    size: int

    @property
    def ollama(self) -> bool:
        """True for an Ollama runner (an executable of an `ollama` directory, or `ollama` itself)."""
        return "ollama" in Path(self.name).parts or Path(self.name).name == "ollama"


@dataclass
class Holder:
    """A holder of memory that a memory error names: what it is, its bytes, and how it frees them."""

    what: str
    size: int
    release: str = ""

    def __str__(self) -> str:
        return f"{self.what} ({self.size / GB:.1f} GB{', ' + self.release if self.release else ''})"


HOLDER_MIN_BYTES = 1 * GB  # `memory_holders` names no process below this
HOLDER_PROCESSES = 5  # `memory_holders` names at most this many processes
OLLAMA_WAIT_SECONDS = 15 * 60  # `wait_for_ollama` waits only for models Ollama unloads within this
OLLAMA_POLL_SECONDS = 5.0


def memory_error(repo: str, sizes: str, advice: str = "free memory and retry") -> LocalMemoryError:
    """The error for model `repo`: `sizes`, what holds the memory (`memory_holders`) and `advice`."""
    held = memory_holders()
    where = f"; held by {'; '.join(map(str, held))}" if held else ""
    return LocalMemoryError(f"local model {repo}: {sizes}{where}. To start it, {advice}")


def memory_holders() -> list[Holder]:
    """What holds the memory a local model needs: the models of each `ollama` provider on this machine
    (`resident_ollama_models`), then the processes that hold the most memory of this device (`gpu_processes`) and,
    on an integrated GPU, whose CPU memory comes from the same pool, the processes with the largest resident set; at
    most `HOLDER_PROCESSES` processes, none below `HOLDER_MIN_BYTES`. This process and, when an Ollama model is
    listed, Ollama's runners are left out."""
    import psutil

    try:
        dev = device()
        shared = integrated(dev)
    except (AIModelsError, RuntimeError):  # no GPU, or CUDA out of memory as this process starts
        dev, shared = None, False
    models = resident_ollama_models()
    procs = {p.pid: (p.name, p.size) for p in gpu_processes(device_uuid(dev)) if not (models and p.ollama)}
    if shared:
        for p in psutil.process_iter(["pid", "name", "exe", "memory_info"]):
            exe = p.info["exe"] or p.info["name"] or ""
            if p.info["memory_info"] and p.info["pid"] not in procs and not (models and GpuProcess(0, exe, 0).ollama):
                procs[p.info["pid"]] = (exe, p.info["memory_info"].rss)
    procs.pop(os.getpid(), None)
    top = sorted(((size, pid, Path(name).name) for pid, (name, size) in procs.items() if size >= HOLDER_MIN_BYTES),
                 reverse=True)
    return [*(Holder(f"Ollama model {m.name}", m.size, unload_text(m)) for m in models),
            *(Holder(f"process {pid} {name}", size, "until it exits") for size, pid, name in top[:HOLDER_PROCESSES])]


def unload_text(m: OllamaModel) -> str:
    """When Ollama unloads `m` and the command that unloads it now."""
    when = f"Ollama unloads it at {m.expires_at.astimezone():%H:%M}, " if m.expires_at else ""
    return f"{when}`ollama stop {m.name.split(':', 1)[1]}` unloads it now"


def device_uuid(dev: str | None) -> str | None:
    """The UUID of the current CUDA device as `nvidia-smi` prints it (`GPU-...`); None for another device."""
    if dev != "cuda":
        return None
    import torch

    return f"GPU-{torch.cuda.get_device_properties(torch.cuda.current_device()).uuid}"


def gpu_processes(uuid: str | None = None) -> list[GpuProcess]:
    """Each process on an NVIDIA GPU (`nvidia-smi --query-compute-apps`), only those of the GPU `uuid` when given;
    none without `nvidia-smi` or when it fails. A process without a reading (`[N/A]`) is left out."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10,
                             check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [GpuProcess(int(pid), name, int(mib) * 2**20)
            for gpu, pid, name, mib in csv.reader(io.StringIO(out), skipinitialspace=True)
            if pid.isdigit() and mib.isdigit() and (uuid is None or gpu == uuid)]


def loopback(url: str) -> bool:
    """True when `url`'s host is this machine (`localhost` or a loopback address)."""
    import ipaddress
    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def resident_ollama_models() -> list[OllamaModel]:
    """Each model loaded in an `ollama` provider of the config whose server runs on this machine (`loopback`;
    `GET /api/ps`); a missing config or a server that does not answer contributes nothing."""
    from .tls import ssl_verify

    try:
        providers = config.load().providers
    except AIModelsError:
        return []
    out = []
    for name, spec in providers.items():
        if spec.kind != ProviderKind.OLLAMA:
            continue
        url = spec.base_url.rstrip("/").removesuffix("/v1") + "/api/ps"
        if not loopback(url):
            continue
        req = urllib.request.Request(url)
        if key := spec.key():
            req.add_header("Authorization", f"Bearer {key}")
        try:
            with urllib.request.urlopen(req, timeout=2, context=ssl_verify() if url.startswith("https") else None) as r:
                ps = _Ps.model_validate(json.load(r))
        except (OSError, ValueError):
            continue
        out.extend(OllamaModel(f"{name}:{m.name}", m.size, m.expires_at) for m in ps.models)
    return out


def ollama_release(dev: str, need: int, free: int, cap: datetime) -> datetime | None:
    """The time by which local Ollama models free `need - free` bytes of `dev` when Ollama unloads them, None when
    the models it unloads by `cap` hold less: their sizes, or the memory of Ollama's runners on `dev` when every
    loaded model unloads by then."""
    models = resident_ollama_models()
    soon = [m for m in models if m.expires_at and m.expires_at <= cap]
    if not soon:
        return None
    release = sum(m.size for m in soon)
    if len(soon) == len(models):
        release = max(release, sum(p.size for p in gpu_processes(device_uuid(dev)) if p.ollama))
    return max(m.expires_at for m in soon) if free + release >= need else None


def wait_for_ollama(dev: str, need: int) -> int:
    """The device's free memory, after waiting for local Ollama models to unload when that frees enough
    (`ollama_release`): it prints a line on stderr and reads the free memory every `OLLAMA_POLL_SECONDS`, and the
    models again, while they still free enough by `OLLAMA_WAIT_SECONDS` from the call (a model another program uses
    moves its unload time), until the free memory reaches `need` bytes or `SETTLE_SECONDS` after the last unload
    time. Otherwise it returns at once. It unloads nothing."""
    free = free_memory(dev)
    cap = datetime.now(timezone.utc) + timedelta(seconds=OLLAMA_WAIT_SECONDS)
    until = ollama_release(dev, need, free, cap) if free < need else None
    if until is None:
        return free
    print(f"ai_models: {need / GB:.1f} GB needed, {free / GB:.1f} GB free; waiting until Ollama unloads models "
          f"(at {until.astimezone():%H:%M:%S}, at most until {cap.astimezone():%H:%M:%S})", file=sys.stderr, flush=True)
    while until is not None and datetime.now(timezone.utc) < until + timedelta(seconds=SETTLE_SECONDS):
        time.sleep(OLLAMA_POLL_SECONDS)
        if (free := free_memory(dev)) >= need:
            break
        until = ollama_release(dev, need, free, cap) or until
    return free


def _modular(cls, repo: str, skip: Sequence[str]):
    """The `ModularPipeline` class `cls` of `repo` (`modular_model_index.json`) with its components loaded in
    bfloat16 on the CPU, except those in `skip`."""
    import torch

    pipe = cls.from_pretrained(str(local_folder(repo) or repo))
    pipe.load_components([n for n in pipe.pretrained_component_names if n not in skip], dtype=torch.bfloat16)
    return pipe


def local_folder(repo: str) -> Path | None:
    """The folder `repo` names when it is a path (absolute, or starting with `~`), else None (a Hugging Face
    repository id). A path that is not a folder raises `ConfigError`."""
    if not repo.startswith(("/", "~")):
        return None
    folder = Path(repo).expanduser()
    if not folder.is_dir():
        raise ConfigError(f"model repo {repo!r} is a path but not a folder")
    return folder


def _from_pretrained(cls, repo: str, dev: str, **kwargs):
    """`cls.from_pretrained` from the folder `repo` names (`local_folder`), else from the cached snapshot folder of
    the repository `repo`, else with a download, with the components `device_components` loads for `dev`.
    Loading the repository id fetches every weight file of each component folder, including
    alternative shardings the pipeline never reads, and `local_files_only` refuses a snapshot
    that lacks any of them; a folder load reads only the files the pipeline names."""
    from huggingface_hub import try_to_load_from_cache

    def load(source: str):
        return cls.from_pretrained(source, **device_components(source, dev, kwargs), **kwargs)

    if (folder := local_folder(repo)) is not None:
        return load(str(folder))
    index = try_to_load_from_cache(repo, "model_index.json")
    if isinstance(index, str):
        try:
            return load(str(Path(index).parent))
        except (OSError, ValueError):
            pass
    return load(repo)


# The component config values a device needs, each where the component's config sets another value. MPS has no
# float64 tensors, and the LTX-2 transformer and text connectors build their rotary frequencies in float64 when
# `rope_double_precision` is true (the published configs); with false they build them in float32. Both cast the
# frequencies to float32 before any use, so the change is the rounding of `theta ** linspace(0, 1)` (docs/ai_models.md,
# Video).
DEVICE_CONFIG: dict[str, dict[str, Any]] = {"mps": {"rope_double_precision": False}}


def device_components(source: str, dev: str, given: dict[str, Any]) -> dict[str, Any]:
    """The components of the pipeline at `source` (a folder or a repository id) whose config differs from
    `DEVICE_CONFIG[dev]`, each loaded with `from_pretrained` (in the `dtype` of `given`) with those values as config
    overrides, the diffusers way to change a config value at load. A component named in `given` (a skipped one) and
    one that is not a diffusers `ConfigMixin` class keep the pipeline's own load."""
    import diffusers

    want = DEVICE_CONFIG.get(dev)
    if not want:
        return {}
    out = {}
    for name, spec in diffusers.DiffusionPipeline.load_config(source).items():
        if name.startswith("_") or name in given or not isinstance(spec, list) or len(spec) != 2:
            continue
        klass = getattr(diffusers, spec[1] or "", None)
        if not (isinstance(klass, type) and issubclass(klass, diffusers.ModelMixin)):
            continue
        conf = klass.load_config(source, subfolder=name)
        changes = {k: v for k, v in want.items() if k in conf and conf[k] != v}
        if changes:
            out[name] = klass.from_pretrained(source, subfolder=name, dtype=given.get("dtype"), **changes)
    return out


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


def pipe_kwargs(spec: DiffusersModel, extra: dict[str, Any]) -> dict[str, Any]:
    """Steps and guidance of the model (each only when set), its `args`, then `extra`; `seed` becomes a torch
    generator on the pipeline's device. diffusers' `randn_tensor` takes a generator of any device, but some pipelines
    draw with `torch.randn(..., generator=generator, device=device)`, which needs one on `device` (the LTX-Video
    decode noise), so a CPU generator fails them on a GPU."""
    kwargs = {k: v for k, v in (("num_inference_steps", spec.steps),
                                ("guidance_scale", spec.guidance)) if v is not None}
    kwargs.update(spec.args)
    kwargs.update(extra)
    if (seed := kwargs.pop("seed", None)) is not None:
        import torch

        kwargs["generator"] = torch.Generator(device()).manual_seed(int(seed))
    return kwargs


def repaint_mask(mask: bytes):
    """An OpenAI mask (transparent = edit) as a diffusers mask (white = repaint)."""
    from PIL import Image

    return Image.open(io.BytesIO(mask)).convert("RGBA").getchannel("A").point(lambda a: 255 if a == 0 else 0)


class DiffusersImageModel(ImageGenerationModel):
    """A Pydantic-AI image model on a local diffusers pipeline. Reference images go as
    `image`; with a `mask`, the first goes to the `inpaint` pipeline. `settings`:
    `dimensions` (width, height) and `extra_body` (more pipeline arguments, `seed`)."""

    def __init__(self, model_id: str, *, mask: bytes | None = None, settings=None) -> None:
        super().__init__(settings=settings)
        self.model_id = model_id
        self._name = config.split_id(model_id)[1]
        self.spec = config.diffusers_model(model_id, DiffusersRole.IMAGE)
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
        if self.mask is not None and not self.spec.inpaint:
            raise ConfigError(f"diffusers model {self.model_id!r} has no `inpaint` pipeline for a mask")
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
        pipe = pipeline(self.spec.repo, self.spec.inpaint if self.mask is not None else None, skip=self.spec.skip,
                        memory=self.spec.memory)
        with out_of_memory(self.spec.repo):
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

    def __init__(self, model_id: str) -> None:
        self.name = model_id
        self.spec = config.diffusers_model(model_id, DiffusersRole.MUSIC)

    def compose(self, prompt: str, *, seconds: float | None = None, lyrics: str | None = None,
                seed: int | None = None) -> bytes:
        """A 16-bit WAV file of the track at the pipeline's sample rate; without `seconds`, the pipeline's own length."""
        import torch

        extra: dict[str, Any] = {"seed": seed}
        if seconds is not None:
            extra[self.spec.duration_arg] = float(seconds)
        if lyrics is not None:
            if not self.spec.lyrics_arg:
                raise ConfigError(f"diffusers model {self.name!r} has no `lyrics_arg` for lyrics")
            extra[self.spec.lyrics_arg] = lyrics
        pipe = pipeline(self.spec.repo, skip=self.spec.skip, memory=self.spec.memory)
        with out_of_memory(self.spec.repo):
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


def animate(model_id: str, image: bytes | None, prompt: str, *, seconds: float, width: int | None = None,
            height: int | None = None, aspect: float | None = None, seed: int | None = None) -> bytes:
    """An MP4 (H.264) of the video model `model_id` (a diffusers model), at `width` x `height`, else
    the model's size, reshaped to `aspect` when given (`video.clip_size`). The image is cropped to
    the clip's aspect ratio and scaled to its size. Without an image the clip comes from the prompt alone, with the
    model's `text_pipeline` (`text_pipe`). When the pipeline output has `audio` (a sound track generated
    with the frames, (channels, samples) or (samples,) per video, a tensor or an array), the clip carries it as an AAC
    stream at the pipeline's rate (`audio_rate`); else it has no audio stream. Encoded with diffusers' `encode_video`."""
    from diffusers.utils import encode_video
    from PIL import Image, ImageOps

    from .video import clip_size, frame_count

    spec = config.diffusers_model(model_id, DiffusersRole.VIDEO)
    w, h = clip_size(spec, width, height, aspect)
    frames_n = frame_count(seconds, spec.fps, spec.frame_step, spec.max_frames)
    extra: dict[str, Any] = {"width": w, "height": h, "num_frames": frames_n, "seed": seed}
    if image is None:
        pipe = text_pipe(model_id, spec)
    else:
        pipe = pipeline(spec.repo, cls=spec.pipeline, skip=spec.skip, memory=spec.memory)
        extra["image"] = ImageOps.fit(Image.open(io.BytesIO(image)).convert("RGB"), (w, h))
    with out_of_memory(spec.repo):
        result = pipe(prompt=prompt, output_type="np", **pipe_kwargs(spec, extra))
    audio = getattr(result, "audio", None)
    track = {} if audio is None else {"audio": waveform(audio[0]), "audio_sample_rate": audio_rate(pipe)}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clip.mp4"
        encode_video(result.frames[0], fps=spec.fps, output_path=str(out), **track)
        return out.read_bytes()


def text_pipe(model_id: str, spec: DiffusersVideoModel):
    """The prompt-to-video pipeline of the video model `spec`: its `pipeline` when `text_pipeline` names the same
    class (one that takes no image), else the `text_pipeline` class over the modules of `pipeline`; `AIModelsError`
    when the entry has no `text_pipeline`."""
    if not spec.text_pipeline:
        raise AIModelsError(f"{model_id}: the model needs an image (its entry has no `text_pipeline`)")
    over = None if spec.text_pipeline == spec.pipeline else spec.text_pipeline
    return pipeline(spec.repo, over, cls=spec.pipeline, skip=spec.skip, memory=spec.memory)


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


def presenter_still(buckets: list[tuple[int, int]], image: bytes, aspect: float | None = None):
    """`image` as an RGB PIL image cropped to the bucket of `buckets` nearest `aspect` (default the image's,
    `video.bucket`) and scaled to it; the crop keeps more of the top (`PRESENTER_CENTERING`)."""
    from PIL import Image, ImageOps

    from .video import bucket

    still = Image.open(io.BytesIO(image)).convert("RGB")
    return ImageOps.fit(still, bucket(buckets, aspect or still.width / still.height), centering=PRESENTER_CENTERING)


def present(model_id: str, image: bytes, speech: bytes, *, aspect: float | None = None, prompt: str | None = None,
            seed: int | None = None) -> bytes:
    """An MP4 (H.264, AAC) of the presenter model `model_id` (a diffusers model): the person in `image` speaks `speech` (an audio
    file), as long as the speech, with the speech as its sound track (AAC, at the file's sample rate). The size is
    the model's bucket nearest `aspect` (width / height; default the image's, `video.bucket`); the image is cropped
    to it, biased upward, and scaled (`presenter_still`). The model takes the speech mono at its `audio_rate`;
    `prompt` replaces the model's default prompt when given. Encoded with diffusers' `encode_video`."""
    from diffusers.utils import encode_video

    spec = config.diffusers_model(model_id, DiffusersRole.PRESENTER)
    still = presenter_still(spec.buckets, image, aspect)
    w, h = still.size
    drive, _ = read_audio(speech, spec.audio_rate, "mono")
    track, rate = read_audio(speech)
    extra: dict[str, Any] = {"width": w, "height": h, "fps": spec.fps, "seed": seed}
    if prompt:
        extra["prompt"] = prompt
    pipe = pipeline(spec.repo, cls=spec.pipeline, skip=spec.skip, memory=spec.memory)
    with out_of_memory(spec.repo):
        frames = pipe(image=still, audio=drive[0].numpy(), output=spec.output, output_type="np",
                      **pipe_kwargs(spec, extra))[0]
    seconds = len(frames) / spec.fps
    track = track[:, : round(seconds * rate)]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "presenter.mp4"
        encode_video(frames, fps=spec.fps, output_path=str(out), audio=track, audio_sample_rate=rate)
        return out.read_bytes()
