"""Chatterbox Turbo (provider kind `chatterbox`): local speech with zero-shot voice cloning, in its own environment.

chatterbox-tts pins torch 2.6, so the model runs in a separate Python environment (`python` of the provider), in
one worker process per calling process (`chatterbox_worker.py`), started on the first `speak` and stopped at exit
(`atexit`; the kernel also stops it when the caller dies, `PR_SET_PDEATHSIG`). The worker runs on the CPU, so it
takes no GPU lock. Requests and answers are JSON lines over the worker's stdin and stdout; its stderr goes to a log
file whose tail an error quotes.

The model files are `files` under the repository URL `url`, downloaded by this process to `weights.model_dir`.
A voice is `default` (the model's built-in voice) or the path of a reference recording longer than 5 s; the model
uses its first 10 to 15 s and copies the speaker and also the delivery, microphone and room. The output is a
24 kHz WAV file with Resemble's Perth watermark (inaudible). There is no speed or style control.
"""

from __future__ import annotations

import atexit
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import omni, weights
from .config import required
from .errors import AIModelsError, ConfigError

KIND = "chatterbox"
DEFAULT_VOICE = "default"
WORKER = Path(__file__).with_name("chatterbox_worker.py")
STOP_SECONDS = 30.0

_workers: dict[str, "Worker"] = {}


@dataclass
class Worker:
    """A running worker: its process and its stderr log."""

    proc: subprocess.Popen
    log: Path

    def ask(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send one request line, return the answer line; `AIModelsError` when the worker has exited."""
        try:
            if request:
                self.proc.stdin.write(json.dumps(request) + "\n")
                self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        except (BrokenPipeError, OSError):
            line = ""
        if not line:
            self.proc.wait()
            raise AIModelsError(f"the Chatterbox worker exited with code {self.proc.returncode}:\n"
                                f"{omni.tail(self.log)}")
        return json.loads(line)

    def stop(self) -> None:
        """Close its stdin, which ends it; kill it after `STOP_SECONDS`."""
        try:
            self.proc.stdin.close()
            self.proc.wait(STOP_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
            self.proc.wait()


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
    """The worker of provider `name`, started on the first call of the process."""
    if name in _workers and _workers[name].proc.poll() is None:
        return _workers[name]
    python = str(Path(str(required(spec, "python", name))).expanduser())
    d = fetch(spec, name, model)
    log = Path(tempfile.mkdtemp(prefix="ai-models-chatterbox-")) / "worker.log"
    with log.open("wb") as err:
        try:
            proc = subprocess.Popen([python, "-I", str(WORKER), str(d)], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=err, text=True, start_new_session=True,
                                    preexec_fn=omni.die_with_parent)
        except OSError as e:
            raise ConfigError(f"provider {name!r}: cannot run {python}: {e}") from e
    w = Worker(proc, log)
    atexit.register(w.stop)
    w.ask({})  # the ready line
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
    with tempfile.TemporaryDirectory(prefix="ai-models-chatterbox-") as tmp:
        out = Path(tmp) / "speech.wav"
        answer = worker(spec, name, model).ask({"text": text, "reference": ref, "out": str(out)})
        if "error" in answer:
            raise AIModelsError(f"{name}:{model}: {answer['error']}")
        return out.read_bytes()
