"""Speech models of vLLM-Omni (provider kind `vllm-omni`), served by a vLLM-Omni server in its own environment.

vLLM-Omni pins its own torch and transformers, so it runs in a separate Python environment (`python` of the
provider) and the skill process talks to it over HTTP. The server serves one model (`repo`) for the life of the
calling process: the first `aspeak` takes the local-model lock (`local.hold_lock`), reads the free memory
(`local.free_memory`, the figure vLLM checks its budget against; after waiting for the lock, once it settles,
`local.wait_for_settled_memory`), refuses the start with `local.memory_error` when the provider's `memory` (GB) exceeds
it, writes a deploy overlay and starts `vllm serve <repo> --omni` on a free loopback port. `atexit` stops the
server's process group, also after a SIGTERM (`exit_on_sigterm`), and the kernel stops its main process when the
caller dies (`PR_SET_PDEATHSIG`). `args` (optional) lists more server arguments, `env` (optional) environment
variables of the server. So no memory stays held after the command.

The overlay (`overlay`) inherits the model's deploy config (`deploy`: a file of vLLM-Omni's `deploy/` directory or
a path), turns the CUDA MPS daemon off and scales every stage's `gpu_memory_utilization` so that together they
take `memory` GB, in the stages' original proportions. A fixed budget gives each stage the same memory on every
start, whatever else is loaded; vLLM sizes the KV cache as the stage's budget minus its weights, activations and
other allocations, and fails when that is not positive. Without MPS the stages share the GPU by time-slicing.

A request is `POST /v1/audio/speech`. The voice is `default` (the model's own voice) or a reference recording
(`reference`): an audio file with its transcript in a `.txt` file of the same stem, sent as `ref_audio` (a
`data:` URI) and `ref_text`. Drama 3 picks a new speaker for each request without a reference, and a fixed `seed`
does not keep it (the speaker still changes with the text), so with `default` the first answer of the process
(`first_take`) is the reference of every later request: one process, one speaker. `style` (optional) is a format string with `{instructions}` and `{text}` that puts
the caller's instructions into the text, for a model whose direction is inline tags.
"""

from __future__ import annotations

import atexit
import base64
import mimetypes
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from plugin_settings import ProviderKind, VllmOmniProvider

from . import local
from .errors import AIModelsError, ConfigError

KIND = ProviderKind.VLLM_OMNI
DEFAULT_VOICE = "default"
POLL_SECONDS = 2.0
STOP_SECONDS = 30.0  # seconds `stop` waits for the main process, then again for the rest of its group
STOP_POLL_SECONDS = 0.2
LOG_TAIL = 4000  # characters of the server log an error quotes

_servers: dict[str, "Server"] = {}
# (provider, speaker) -> (WAV, text) of the first `DEFAULT_VOICE` answer for that speaker (None: the narrator)
_takes: dict[tuple[str, str | None], tuple[bytes, str]] = {}


@dataclass
class Server:
    """A running vLLM-Omni server: its process, URL, log file, the model name it serves and its start time."""

    proc: subprocess.Popen
    url: str
    log: Path
    model: str
    load_seconds: float = 0.0

    def stop(self, seconds: float = STOP_SECONDS) -> None:
        """SIGTERM to the server's process group; SIGKILL to the group when the main process, or after it the rest
        of the group (the stage workers), is still there after `seconds`."""
        pgid = self.proc.pid
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.proc.wait(seconds)
        except subprocess.TimeoutExpired:
            pass
        deadline = time.monotonic() + seconds
        while group_alive(pgid) and time.monotonic() < deadline:
            time.sleep(STOP_POLL_SECONDS)
        if group_alive(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.proc.wait()
        deadline = time.monotonic() + seconds  # killed members stay in the group until their parent reaps them
        while group_alive(pgid) and time.monotonic() < deadline:
            time.sleep(STOP_POLL_SECONDS)


def group_alive(pgid: int) -> bool:
    """True while a process of group `pgid` exists (`killpg` with signal 0)."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def exit_on_sigterm() -> None:
    """In the main thread, make SIGTERM raise `SystemExit` when it has its default action, so that `atexit` stops
    the servers' process groups; `PR_SET_PDEATHSIG` reaches only each server's main process."""
    if threading.current_thread() is threading.main_thread() and signal.getsignal(signal.SIGTERM) == signal.SIG_DFL:
        signal.signal(signal.SIGTERM, _raise_exit)


def _raise_exit(signum: int, _frame) -> None:
    raise SystemExit(128 + signum)


def deploy_path(python: str, deploy: str) -> Path:
    """`deploy` as a path: itself when it names a file, else a file of vLLM-Omni's `deploy/` directory, found with
    the server environment's `python` (`find_spec` does not import the package)."""
    p = Path(deploy).expanduser()
    if p.is_file():
        return p
    try:
        out = subprocess.run([python, "-I", "-c", "import importlib.util as u; "
                              "print(u.find_spec('vllm_omni').submodule_search_locations[0])"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        raise ConfigError(f"{python} cannot find vllm_omni: {getattr(e, 'stderr', '') or e}") from e
    p = Path(out) / "deploy" / deploy
    if not p.is_file():
        raise ConfigError(f"no deploy config {deploy!r}: {p} does not exist")
    return p


def overlay(base: Path, share: float) -> dict[str, Any]:
    """A deploy overlay of `base`: no CUDA MPS daemon, and each stage's `gpu_memory_utilization` scaled so the
    stages together take `share` of the device memory."""
    stages = (yaml.safe_load(base.read_text()) or {}).get("stages") or []
    fractions = {s["stage_id"]: float(s["gpu_memory_utilization"]) for s in stages if "gpu_memory_utilization" in s}
    if not fractions:
        raise ConfigError(f"deploy config {base} has no stage with gpu_memory_utilization")
    total = sum(fractions.values())
    return {"base_config": str(base),
            "stages": [{"stage_id": sid, "gpu_memory_utilization": round(share * f / total, 4)}
                       for sid, f in fractions.items()],
            "platforms": {"cuda": {"cuda_mps": False}}}


# The default `overhead` of a provider (`VllmOmniProvider.overhead`, 22 GB): the GB the server takes outside
# `memory`, the host memory of the API server and the stage processes, and device memory past the stages' budgets
# (CUDA contexts and, with the estimate off, `INTEGRATED_ENV`, the CUDA graph pool). On the GB10, Drama 3 with
# `memory: 70` took 18.7 to 19.9 GB more than `memory` at its peak over a start and two requests
# (docs/ai_models.md); the default adds 2 GB to the largest.


def memory_bytes(spec: VllmOmniProvider) -> int:
    """The bytes the server's stages take together: the provider's `memory` in GB."""
    return int(spec.memory * local.GB)


def overhead_bytes(spec: VllmOmniProvider) -> int:
    """The bytes the server takes outside `memory`: the provider's `overhead` in GB."""
    return int(spec.overhead * local.GB)


def device_share(need: int, total: int, name: str) -> float:
    """`need` bytes as a share of the device's `total`; a `ConfigError` above the whole device."""
    if need > total:
        raise ConfigError(f"provider {name!r}: memory {need / local.GB:.1f} GB exceeds the device's "
                          f"{total / local.GB:.1f} GB")
    return need / total


def command(python: str, repo: str, deploy: Path, port: int, model: str, args: list[str] = ()) -> list[str]:
    """`vllm serve <repo> --omni` on loopback, then the provider's `args` (more server arguments)."""
    return [python, "-m", "vllm.entrypoints.cli.main", "serve", repo, "--omni", "--deploy-config", str(deploy),
            "--host", "127.0.0.1", "--port", str(port), "--served-model-name", model, *map(str, args)]


# Set in the server's environment on an integrated GPU unless the provider's `env` sets it. vLLM estimates the CUDA
# graph pool from `mem_get_info` deltas, which there also move with the page cache and other processes: on the GB10,
# Drama 3 starts measured 0.2 to 3.3 GiB, and one 17.7 GiB, which left no KV cache (docs/ai_models.md).
INTEGRATED_ENV = {"VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS": "0"}


def server_env(spec: VllmOmniProvider, shared: bool = False) -> dict[str, str]:
    """This process's environment, `INTEGRATED_ENV` when `shared` (an integrated GPU), then the provider's `env`
    mapping (variables vLLM reads)."""
    return {**os.environ, **(INTEGRATED_ENV if shared else {}),
            **{k: str(v) for k, v in spec.env.items()}}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def die_with_parent() -> None:
    """In the child before exec: SIGTERM when the parent dies (Linux `PR_SET_PDEATHSIG`)."""
    if sys.platform == "linux":
        import ctypes

        ctypes.CDLL(None).prctl(1, signal.SIGTERM)


def tail(log: Path) -> str:
    """The last `LOG_TAIL` characters of the server log, for an error to quote."""
    return read_log(log)[-LOG_TAIL:]


class StartFailure(Enum):
    """How a server start ran out of memory, read from its log (`start_failure`)."""

    KV_CACHE = "kv-cache"  # the stage's budget left no KV cache
    OUT_OF_MEMORY = "out-of-memory"  # a CUDA or torch out-of-memory error, or vLLM's free memory check


# Log lines of each `StartFailure`, checked in this order.
FAILURE_LINES = {
    StartFailure.KV_CACHE: ("No available memory for the cache blocks",),
    StartFailure.OUT_OF_MEMORY: ("CUDA error: out of memory", "torch.OutOfMemoryError",
                                 "Decrease GPU memory utilization or reduce GPU memory used by other processes"),
}


def start_failure(text: str) -> StartFailure | None:
    """The `StartFailure` the whole server log `text` shows, None when it shows none."""
    return next((f for f, lines in FAILURE_LINES.items() if any(line in text for line in lines)), None)


def failure_advice(failure: StartFailure, name: str) -> str:
    """What to do after `failure` of provider `name`'s server."""
    if failure is StartFailure.KV_CACHE:
        return f"raise `memory` of provider {name!r} (the budget left no KV cache) and retry"
    return f"free memory, or lower `memory` of provider {name!r}, and retry"


def read_log(log: Path) -> str:
    """The whole server log; empty when it cannot be read."""
    try:
        return log.read_text(errors="replace")
    except OSError:
        return ""


@contextmanager
def context_out_of_memory(repo: str) -> Iterator[None]:
    """Turn a CUDA out-of-memory error of this process's first CUDA calls into `local.memory_error`. On the GB10
    one start failed so, with 59 GB `MemAvailable` and 4 GB `MemFree`, while an Ollama model had just loaded."""
    try:
        yield
    except RuntimeError as e:
        if "out of memory" not in str(e):
            raise
        raise local.memory_error(repo, f"CUDA ran out of memory as this process started ({e})") from e


def server(name: str, spec: VllmOmniProvider, model: str) -> Server:
    """The server of provider `name`, started on the first call of the process."""
    if name in _servers and _servers[name].proc.poll() is None:
        return _servers[name]
    import httpx
    import torch

    python, repo = str(spec.python), spec.repo
    base = deploy_path(python, spec.deploy)
    exit_on_sigterm()
    need = memory_bytes(spec)
    overhead = overhead_bytes(spec)
    waited = local.hold_lock() or name in _servers
    started = time.monotonic()
    with context_out_of_memory(repo):
        dev = local.device()
        free = local.wait_for_settled_memory(dev) if waited else local.free_memory(dev)
        share = device_share(need, torch.cuda.mem_get_info()[1] if dev == "cuda" else free, name)
        if need + overhead > free and waited:
            free = local.wait_for_memory(dev, need + overhead)
        if need + overhead > free:
            free = local.wait_for_ollama(dev, need + overhead)
    if need + overhead > free:
        raise local.memory_error(repo, f"the vLLM-Omni server needs {need / local.GB:.1f} GB (`memory` of provider "
                                 f"{name!r}) plus {overhead / local.GB:.1f} GB outside it (`overhead`) and the "
                                 f"device has {free / local.GB:.1f} GB free",
                                 f"free memory, or lower `memory` of provider {name!r} (vLLM sizes the KV cache from "
                                 "it), and retry")
    shared = local.integrated(dev)
    work = Path(tempfile.mkdtemp(prefix="ai-models-omni-"))
    deploy = work / "deploy.yaml"
    deploy.write_text(yaml.safe_dump(overlay(base, share)))
    log = work / "server.log"
    port = free_port()
    print(f"ai_models: starting {repo} with vLLM-Omni ({need / local.GB:.1f} GB plus {overhead / local.GB:.1f} GB "
          f"outside it, of {free / local.GB:.1f} GB free, "
          f"log {log})", file=sys.stderr, flush=True)
    with log.open("wb") as out:
        proc = subprocess.Popen(command(python, repo, deploy, port, model, spec.args), stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True, preexec_fn=die_with_parent,
                                env=server_env(spec, shared))
    srv = Server(proc, f"http://127.0.0.1:{port}", log, model)
    atexit.register(srv.stop)
    deadline = started + spec.start_timeout
    while True:
        if proc.poll() is not None:
            srv.stop()
            if failure := start_failure(read_log(log)):
                raise local.memory_error(repo, f"a stage of the vLLM-Omni server ran out of memory during the start "
                                         f"({failure.value}), with a budget of {need / local.GB:.1f} GB (`memory` "
                                         f"of provider {name!r}); log {log}", failure_advice(failure, name))
            raise AIModelsError(f"vLLM-Omni server of {repo} exited with code {proc.returncode}:\n{tail(log)}")
        try:
            if httpx.get(f"{srv.url}/health", timeout=5, trust_env=False).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            srv.stop()
            raise AIModelsError(f"vLLM-Omni server of {repo} did not start in {deadline - started:.0f} s:\n{tail(log)}")
        time.sleep(POLL_SECONDS)
    srv.load_seconds = time.monotonic() - started
    print(f"ai_models: {repo} ready in {srv.load_seconds:.0f} s", file=sys.stderr, flush=True)
    _servers[name] = srv
    return srv


def reference(voice: str) -> tuple[str, str] | None:
    """(`data:` URI, transcript) of a reference recording `voice`, None for `DEFAULT_VOICE`. The transcript is the
    `.txt` file of the same stem."""
    if voice == DEFAULT_VOICE:
        return None
    audio = Path(voice).expanduser()
    if not audio.is_file():
        raise AIModelsError(f"voice {voice!r} is neither {DEFAULT_VOICE!r} nor a reference recording (a file)")
    text = audio.with_suffix(".txt")
    if not text.is_file():
        raise AIModelsError(f"reference recording {audio} has no transcript {text}")
    mime = mimetypes.guess_type(audio.name)[0] or "audio/wav"
    return f"data:{mime};base64,{base64.b64encode(audio.read_bytes()).decode()}", text.read_text().strip()


def styled(spec: VllmOmniProvider, name: str, text: str, instructions: str | None) -> str:
    """`text` with `instructions` put in by the provider's `style` format; `text` alone without instructions."""
    if not instructions:
        return text
    fmt = spec.style
    if not fmt:
        raise AIModelsError(f"provider {name!r} has no `style` format, so it takes no instructions")
    return fmt.format(instructions=instructions.strip(), text=text)


def data_uri(wav: bytes) -> str:
    return f"data:audio/wav;base64,{base64.b64encode(wav).decode()}"


# The fields `request_body` sets; a caller's `params` cannot replace them.
BUILT_FIELDS = frozenset({"model", "input", "response_format", "ref_audio", "ref_text"})


def request_body(model: str, text: str, voice: str, take: tuple[bytes, str] | None = None,
                 params: dict[str, Any] | None = None) -> dict[str, Any]:
    """The speech request; with `DEFAULT_VOICE` and a first take (WAV, text), that take as the reference; `params`
    added (`AIModelsError` for one of `BUILT_FIELDS`)."""
    if taken := sorted(set(params or {}) & BUILT_FIELDS):
        raise AIModelsError(f"request parameters {', '.join(taken)} are set from the text, voice and model")
    body: dict[str, Any] = {"model": model, "input": text, "response_format": "wav"}
    if ref := reference(voice):
        body["ref_audio"], body["ref_text"] = ref
    elif take:
        body["ref_audio"], body["ref_text"] = data_uri(take[0]), take[1]
    return {**body, **(params or {})}


def first_take(name: str, speaker: str | None = None) -> tuple[bytes, str] | None:
    """(WAV, text) of provider `name`'s first answer with `DEFAULT_VOICE` for `speaker` in this process, None
    before it."""
    return _takes.get((name, speaker))


def keep_take(name: str, speaker: str | None, voice: str, wav: bytes, said: str) -> None:
    """Keep `wav` (the answer to `said`) as `speaker`'s first take when the voice is `DEFAULT_VOICE` and it has
    none yet."""
    if voice == DEFAULT_VOICE:
        _takes.setdefault((name, speaker), (wav, said))


async def aspeak(name: str, spec: VllmOmniProvider, model: str, text: str, voice: str, instructions: str | None,
                 speed: float, speaker: str | None = None, params: dict[str, Any] | None = None) -> bytes:
    """A WAV file of `text` at the model's own rate from the provider's server (Drama 3 refuses `sample_rate`).
    With `DEFAULT_VOICE`, `speaker`'s first take is the reference of its later requests, so each speaker keeps one
    voice. `params` are more request fields (`request_body`; Drama 3: `seed`, `max_new_tokens`, `extra_params` with
    `temperature`, `top_p`, `top_k`); the server ignores fields it does not know. The first call starts the server
    in the calling thread, the event loop's, which blocks the loop while it loads: `PR_SET_PDEATHSIG` stops the
    server when the thread that started it exits, and the loop's thread lives as long as the caller. The request
    itself is asynchronous."""
    import httpx

    if speed != 1.0:
        raise AIModelsError(f"{name}:{model} has no speed setting")
    said = styled(spec, name, text, instructions)
    body = request_body(model, said, voice, first_take(name, speaker) if voice == DEFAULT_VOICE else None, params)
    srv = server(name, spec, model)
    async with httpx.AsyncClient(trust_env=False, timeout=spec.timeout) as client:
        r = await client.post(f"{srv.url}/v1/audio/speech", json=body)
    if r.status_code != 200:
        raise AIModelsError(f"{name}:{model} answered {r.status_code}: {r.text[:500]}")
    keep_take(name, speaker, voice, r.content, said)
    return r.content
