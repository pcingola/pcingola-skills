"""Run a skill CLI's `routes` command in process (`main_rows`), against a config with an Ollama provider, a google one
and a diffusers one with a video and a presenter model, and a user `routes.md` holding one escalation row of every
task, each with a model of a kind the task takes, and, with `tasks.speech` set, the default row of `speech`, so the
output shows which tasks the skill routes."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tests.inproc import run_main
from tests.settings_env import write_config

HEADER = "| task | model | when | why |"
TASKS = ("chat", "vision", "system1", "image", "image_edit", "image_best", "image_multi_ref", "speech", "music",
         "audio", "video", "presenter", "film_critic")
# The model of the escalation row of the tasks that take no ollama model.
MODELS = {"music": "g:lyria-3", "video": "local:v", "presenter": "local:p"}
PROVIDERS = {"o": {"kind": "ollama"}, "g": {"kind": "google", "api_key": "k"},
             "local": {"kind": "diffusers", "models": {
                 "v": {"repo": "r", "pipeline": "P", "fps": 24, "size_multiple": 32, "frame_step": 8, "width": 64,
                       "height": 64, "max_frames": 9},
                 "p": {"repo": "r", "pipeline": "P", "fps": 25, "buckets": [[64, 64]], "audio_rate": 16000,
                       "output": "videos"}}}}


def _write_settings(tmp_path: Path) -> Path:
    """Write the config.yaml and the routes.md beside it in `tmp_path`; return the config path."""
    cfg = write_config(tmp_path / "config.yaml", providers=PROVIDERS, tasks={"speech": "o:tts"})
    rows = "| speech | o:tts | default | test |\n"
    rows += "".join(f"| {t} | {MODELS.get(t, f'o:{t}-model')} | only when tested | test |\n" for t in TASKS)
    (tmp_path / "routes.md").write_text(HEADER + "\n|---|---|---|---|\n" + rows, encoding="utf-8")
    return cfg


def _rows(stdout: str) -> list[list[str]]:
    """The cells `[task, model, when, why]` of each row of the printed routes table `stdout`."""
    lines = stdout.splitlines()
    assert lines[0] == HEADER, stdout
    return [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines[2:]]


def main_rows(main: Callable[[list[str]], int], tmp_path: Path, *argv: str) -> list[list[str]]:
    """The rows, as cells `[task, model, when, why]`, that the CLI entry `main(argv) -> int` prints for
    `routes *argv`, in order, called in process with the settings of `_write_settings`."""
    done = run_main(main, "routes", *argv, settings=_write_settings(tmp_path))
    assert done.returncode == 0, done.stderr
    return _rows(done.stdout)


def main_tasks(main: Callable[[list[str]], int], tmp_path: Path, *argv: str) -> list[str]:
    """The tasks of the rows that `main` prints for `routes *argv`, in order, called in process (`main_rows`)."""
    return [row[0] for row in main_rows(main, tmp_path, *argv)]
