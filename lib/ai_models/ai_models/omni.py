"""Speech models of vLLM-Omni (provider kind `vllm-omni`), served by a vLLM-Omni server in its own environment.

vLLM-Omni pins its own torch and transformers, so it runs in a separate Python environment (`python` of the
provider) and the skill process talks to it over HTTP. The server serves one model (`repo`) for the life of the
calling process: the first `speak` takes the local-model lock (`local.hold_lock`), reads the free memory
(`local.free_memory`; after waiting for the lock, once it settles, `local.wait_for_settled_memory`; on an
integrated GPU at most `torch.cuda.mem_get_info`'s free bytes, `vllm_free_memory`, after dropping the page cache of
the model files, `local.drop_page_cache`, because `mem_get_info` counts that cache as used), writes a deploy overlay and
starts `vllm serve <repo> --omni` on a free loopback port. `atexit` stops the server's process group, also after a
SIGTERM (`exit_on_sigterm`), and the kernel stops its main process when the caller dies (`PR_SET_PDEATHSIG`).
`args` (optional) lists more server arguments, `env` (optional) environment variables of the server. So no memory
stays held after the command.

The overlay (`overlay`) inherits the model's deploy config (`deploy`: a file of vLLM-Omni's `deploy/` directory or
a path), turns the CUDA MPS daemon off and scales every stage's `gpu_memory_utilization` so that together they
take `memory_share` of the memory free before the start, in the stages' original proportions. Without MPS the
stages share the GPU by time-slicing.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import local
from .config import required
from .errors import AIModelsError, ConfigError

KIND = "vllm-omni"
DEFAULT_VOICE = "default"
START_TIMEOUT = 1800.0  # seconds a server may take to load before `start` gives up (provider key start_timeout)
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


def memory_share(spec: dict[str, Any], name: str, free: int, total: int) -> float:
    """The share of the device memory the server may take: `memory_share` of the free bytes, over the total."""
    share = float(required(spec, "memory_share", name))
    if not 0 < share <= 1:
        raise ConfigError(f"provider {name!r}: memory_share must be in (0, 1], got {share}")
    return share * free / total


def vllm_free_memory(free: int, dev: str) -> int:
    """The free bytes the vLLM share is sized from: `free` (`local.free_memory`), on an integrated GPU at most
    `torch.cuda.mem_get_info`'s free bytes, the figure vLLM checks its share against at start."""
    if not local.integrated(dev):
        return free
    import torch

    return min(free, torch.cuda.mem_get_info()[0])


def command(python: str, repo: str, deploy: Path, port: int, model: str, args: list[str] = ()) -> list[str]:
    """`vllm serve <repo> --omni` on loopback, then the provider's `args` (more server arguments)."""
    return [python, "-m", "vllm.entrypoints.cli.main", "serve", repo, "--omni", "--deploy-config", str(deploy),
            "--host", "127.0.0.1", "--port", str(port), "--served-model-name", model, *map(str, args)]


def server_env(spec: dict[str, Any]) -> dict[str, str]:
    """This process's environment plus the provider's `env` mapping (variables vLLM reads)."""
    return {**os.environ, **{str(k): str(v) for k, v in (spec.get("env") or {}).items()}}


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
    try:
        return log.read_text(errors="replace")[-LOG_TAIL:]
    except OSError:
        return ""


def server(name: str, spec: dict[str, Any], model: str) -> Server:
    """The server of provider `name`, started on the first call of the process."""
    if name in _servers and _servers[name].proc.poll() is None:
        return _servers[name]
    import httpx
    import torch

    python = str(Path(str(required(spec, "python", name))).expanduser())
    repo = str(required(spec, "repo", name))
    base = deploy_path(python, str(required(spec, "deploy", name)))
    exit_on_sigterm()
    waited = local.hold_lock() or name in _servers
    started = time.monotonic()
    dev = local.device()
    if local.integrated(dev):
        local.drop_page_cache(local.model_dirs())  # mem_get_info, which vLLM checks, counts the page cache as used
    free = vllm_free_memory(local.wait_for_settled_memory(dev) if waited else local.free_memory(dev), dev)
    share = memory_share(spec, name, free, torch.cuda.mem_get_info()[1] if dev == "cuda" else free)
    work = Path(tempfile.mkdtemp(prefix="ai-models-omni-"))
    deploy = work / "deploy.yaml"
    deploy.write_text(yaml.safe_dump(overlay(base, share)))
    log = work / "server.log"
    port = free_port()
    print(f"ai_models: starting {repo} with vLLM-Omni ({share:.0%} of the device memory, log {log})",
          file=sys.stderr, flush=True)
    with log.open("wb") as out:
        proc = subprocess.Popen(command(python, repo, deploy, port, model, spec.get("args") or []), stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True, preexec_fn=die_with_parent,
                                env=server_env(spec))
    srv = Server(proc, f"http://127.0.0.1:{port}", log, model)
    atexit.register(srv.stop)
    deadline = started + float(spec.get("start_timeout", START_TIMEOUT))
    while True:
        if proc.poll() is not None:
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


def styled(spec: dict[str, Any], name: str, text: str, instructions: str | None) -> str:
    """`text` with `instructions` put in by the provider's `style` format; `text` alone without instructions."""
    if not instructions:
        return text
    fmt = spec.get("style")
    if not fmt:
        raise AIModelsError(f"provider {name!r} has no `style` format, so it takes no instructions")
    return fmt.format(instructions=instructions.strip(), text=text)


def data_uri(wav: bytes) -> str:
    return f"data:audio/wav;base64,{base64.b64encode(wav).decode()}"


def request_body(model: str, text: str, voice: str, take: tuple[bytes, str] | None = None) -> dict[str, Any]:
    """The speech request; with `DEFAULT_VOICE` and a first take (WAV, text), that take as the reference."""
    body: dict[str, Any] = {"model": model, "input": text, "response_format": "wav"}
    if ref := reference(voice):
        body["ref_audio"], body["ref_text"] = ref
    elif take:
        body["ref_audio"], body["ref_text"] = data_uri(take[0]), take[1]
    return body


def first_take(name: str, speaker: str | None = None) -> tuple[bytes, str] | None:
    """(WAV, text) of provider `name`'s first answer with `DEFAULT_VOICE` for `speaker` in this process, None
    before it."""
    return _takes.get((name, speaker))


def speak(name: str, spec: dict[str, Any], model: str, text: str, voice: str, instructions: str | None,
          speed: float, speaker: str | None = None, params: dict[str, Any] | None = None) -> bytes:
    """A WAV file of `text` at the model's own rate from the provider's server (Drama 3 refuses `sample_rate`).
    With `DEFAULT_VOICE`, `speaker`'s first take is the reference of its later requests, so each speaker keeps one
    voice. `params` are more request fields, over the ones built here (Drama 3: `seed`, `max_new_tokens`,
    `extra_params` with `temperature`, `top_p`, `top_k`); the server ignores fields it does not know."""
    import httpx

    if speed != 1.0:
        raise AIModelsError(f"{name}:{model} has no speed setting")
    said = styled(spec, name, text, instructions)
    body = request_body(model, said, voice, _takes.get((name, speaker)) if voice == DEFAULT_VOICE else None)
    body.update(params or {})
    srv = server(name, spec, model)
    r = httpx.post(f"{srv.url}/v1/audio/speech", json=body, timeout=float(spec.get("timeout", 600)),
                   trust_env=False)
    if r.status_code != 200:
        raise AIModelsError(f"{name}:{model} answered {r.status_code}: {r.text[:500]}")
    if voice == DEFAULT_VOICE:
        _takes.setdefault((name, speaker), (r.content, said))
    return r.content
