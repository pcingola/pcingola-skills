"""Chatterbox Turbo (provider kind `chatterbox`): local speech with zero-shot voice cloning, in its own environment.

chatterbox-tts pins torch 2.6, so the model runs in a separate Python environment (`python` of the provider), in
one worker process per calling process (`chatterbox_worker.py`), started on the first `speak` and stopped at exit
(`atexit`). When the caller dies, the worker's stdin reaches its end and the worker's request loop ends. The worker runs on the CPU, so it
takes no GPU lock. Requests and answers are JSON lines over the worker's stdin and stdout, read by a thread so that
a wait has a limit: `start_timeout` (seconds, default 600) for the load, `timeout` (default 600) per answer. Its
stderr goes to a log file whose tail an error quotes; the log's directory is removed when the worker ends cleanly.

The model files are `files` under the repository URL `url`, downloaded by this process to `weights.model_dir`.
A voice is `default` (the model's built-in voice) or the path of a reference recording longer than 5 s; the model
uses its first 10 to 15 s and copies the speaker and also the delivery, microphone and room. The output is a
24 kHz WAV file with Resemble's Perth watermark (inaudible). There is no speed or style control.
"""

from __future__ import annotations

import atexit
import json
import queue
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import omni, weights
from .config import required
from .errors import AIModelsError, ConfigError

KIND = "chatterbox"
DEFAULT_VOICE = "default"
WORKER = Path(__file__).with_name("chatterbox_worker.py")
STOP_SECONDS = 30.0
TIMEOUT = 600.0  # seconds for the load (provider key start_timeout) and for each answer (timeout)

_workers: dict[str, "Worker"] = {}
_lock = threading.Lock()  # one worker start or request at a time


@dataclass
class Worker:
    """A running worker: its process, its stderr log, and the queue its stdout lines arrive on ("" at the end)."""

    proc: subprocess.Popen
    log: Path
    lines: queue.Queue = field(default_factory=queue.Queue)

    def __post_init__(self) -> None:
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put("")

    def ask(self, request: dict[str, Any], seconds: float) -> dict[str, Any]:
        """Send one request line (none for an empty `request`) and return the answer line; `AIModelsError` when the
        worker has exited or gave no answer in `seconds`, which then stops it."""
        try:
            if request:
                self.proc.stdin.write(json.dumps(request) + "\n")
                self.proc.stdin.flush()
            line = self.lines.get(timeout=seconds)
        except (BrokenPipeError, OSError):
            line = ""
        except queue.Empty:
            self.stop()
            raise AIModelsError(f"the Chatterbox worker gave no answer in {seconds:.0f} s:\n{omni.tail(self.log)}")
        if not line:
            self.proc.wait()
            raise AIModelsError(f"the Chatterbox worker exited with code {self.proc.returncode}:\n"
                                f"{omni.tail(self.log)}")
        return json.loads(line)

    def stop(self) -> None:
        """Close its stdin, which ends it, and remove the log's directory when it exits with code 0; kill it after
        `STOP_SECONDS`, keeping the log."""
        try:
            self.proc.stdin.close()
            self.proc.wait(STOP_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
            self.proc.wait()
        if self.proc.returncode == 0:
            shutil.rmtree(self.log.parent, ignore_errors=True)


def fetch(spec: dict[str, Any], name: str, model: str) -> Path:
    """The directory of the model files, each downloaded when missing."""
    files = required(spec, "files", name)
    if not isinstance(files, list) or not files:
        raise ConfigError(f"provider {name!r}: `files` must be a list of the file names under `url`")
    base = str(required(spec, "url", name)).rstrip("/")
    d = weights.model_dir(spec, model)
    for f in files:
        weights.ensure_file(f"{base}/{f}", d / str(f))
    return d


def worker(spec: dict[str, Any], name: str, model: str) -> Worker:
    """The worker of provider `name`, started on the first call of the process. Callers in several threads
    (`asyncio.to_thread`) share it, one request at a time (`_lock`)."""
    if name in _workers and _workers[name].proc.poll() is None:
        return _workers[name]
    python = str(Path(str(required(spec, "python", name))).expanduser())
    d = fetch(spec, name, model)
    log = Path(tempfile.mkdtemp(prefix="ai-models-chatterbox-")) / "worker.log"
    with log.open("wb") as err:
        try:
            proc = subprocess.Popen([python, "-I", str(WORKER), str(d)], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=err, text=True, start_new_session=True)
        except OSError as e:
            raise ConfigError(f"provider {name!r}: cannot run {python}: {e}") from e
    w = Worker(proc, log)
    atexit.register(w.stop)
    w.ask({}, float(spec.get("start_timeout", TIMEOUT)))  # the ready line
    _workers[name] = w
    return w


def reference(voice: str) -> str | None:
    """The recording path of `voice`, None for `DEFAULT_VOICE`."""
    if voice == DEFAULT_VOICE:
        return None
    p = Path(voice).expanduser()
    if not p.is_file():
        raise AIModelsError(f"voice {voice!r} is neither {DEFAULT_VOICE!r} nor a reference recording (a file)")
    return str(p.resolve())


def speak(spec: dict[str, Any], name: str, model: str, text: str, voice: str) -> bytes:
    """A 24 kHz WAV file of `text` in `voice`."""
    ref = reference(voice)
    with _lock, tempfile.TemporaryDirectory(prefix="ai-models-chatterbox-") as tmp:
        out = Path(tmp) / "speech.wav"
        answer = worker(spec, name, model).ask({"text": text, "reference": ref, "out": str(out)},
                                               float(spec.get("timeout", TIMEOUT)))
        if "error" in answer:
            raise AIModelsError(f"{name}:{model}: {answer['error']}")
        return out.read_bytes()
