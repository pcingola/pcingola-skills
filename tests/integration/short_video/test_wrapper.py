"""Tests of the short-video wrapper `scripts/short-video.sh` run as a process.

The subject is the wrapper, the `uv_env.sh` it sources and the skill's locked environment: `short-video.sh` finds
the plugin directory, sets up the environment outside `plugins/`, chooses `--extra local` from the settings file,
starts `python -m short_video_tool` and passes the arguments and the exit code through. These are the only
short_video tests that start `short-video.sh`; every other test calls the code in process.

The child gets an explicit environment: `settings_env.isolated` (temporary HOME, config and plugin data
directories, so the wrapper builds its environment there) with SKILLS_CONFIG naming a written config.yaml without
a diffusers provider, and no PYTHONPATH, so the CLI imports only the skill's locked environment.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from short_video_tool import config
from tests.integration.short_video.wrapper_env import UV_ENV
from tests.settings_env import isolated, write_config

WRAPPER = config.SCRIPTS_DIR / "short-video.sh"
TIMEOUT_S = 25


@pytest.fixture(scope="module")
def env(tmp_path_factory) -> dict[str, str]:
    """The wrapper's environment: isolated settings directories, SKILLS_CONFIG naming a config.yaml with no
    diffusers provider (so no `--extra local`), and no PYTHONPATH."""
    cfg = write_config(tmp_path_factory.mktemp("wrapper") / "config.yaml", providers={}, tasks={})
    out = {k: v for k, v in isolated().items() if k != "PYTHONPATH"}
    out["SKILLS_CONFIG"] = str(cfg)
    return out


def run_wrapper(env: dict[str, str], *args: str | Path) -> subprocess.CompletedProcess:
    """Run `short-video.sh <args>` in environment `env`, for at most TIMEOUT_S seconds."""
    return subprocess.run([str(WRAPPER), *map(str, args)], capture_output=True, text=True, env=env,
                          timeout=TIMEOUT_S)


def test_help(env):
    """`short-video.sh --help` exits 0 and prints the usage of the `short-video` parser with its commands. Guards
    that the wrapper builds the skill's environment and starts `short_video_tool` in it."""
    r = run_wrapper(env, "--help")
    assert r.returncode == 0, r.stderr
    assert "usage: short-video" in r.stdout
    assert "validate" in r.stdout and "init" in r.stdout


def test_init_then_validate(env, tmp_path):
    """`short-video.sh init` creates a project with settings.yaml and storyboard.md, and `short-video.sh validate`
    on it exits 0 and prints the scene count and estimated length of the template storyboard. Guards that the
    wrapper passes arguments through and that a command runs end to end with the skill's locked dependencies."""
    project = tmp_path / "film"
    r = run_wrapper(env, "init", project)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines() == [str(project), "  settings.yaml", "  storyboard.md"]
    assert (project / "settings.yaml").is_file() and (project / "storyboard.md").is_file()

    r = run_wrapper(env, "validate", "-p", project)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines()[-1] == "scenes: 2, estimated length: 10 s"
    assert "error:" not in r.stdout


def test_error_exit_code(env, tmp_path):
    """`short-video.sh validate` on a missing project exits 1 and prints the error on stderr. Guards that the
    wrapper (`exec uv run ...`) returns the CLI's exit code and stream to the caller."""
    missing = tmp_path / "missing"
    r = run_wrapper(env, "validate", "-p", missing)
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"Error: project {missing} does not exist" in r.stderr


@pytest.mark.parametrize("text, extra", [
    ("providers:\n  local: {kind: diffusers}\n", "--extra local"),
    ("providers:\n  # local: {kind: diffusers}\n  o: {kind: ollama}\n", ""),
    (None, ""),
])
def test_local_extra(tmp_path, text, extra):
    """The wrapper adds `--extra local` to `uv run` exactly when the config of SKILLS_CONFIG has a provider of kind
    diffusers; a commented line or a missing file adds nothing. Runs the wrapper's own lines from `CONFIG=` up to
    `exec` in bash, since running the wrapper with a diffusers provider would install torch and diffusers."""
    cfg = tmp_path / "config.yaml"
    if text is not None:
        cfg.write_text(text)
    lines = WRAPPER.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("CONFIG="))
    end = next(i for i, line in enumerate(lines) if line.startswith("exec "))
    script = "\n".join([f"source {UV_ENV}", *lines[start:end], 'printf %s "$EXTRA"'])
    r = subprocess.run(["bash", "-euc", script], env={"PATH": os.environ["PATH"], "HOME": str(tmp_path),
                                                      "SKILLS_CONFIG": str(cfg)},
                       capture_output=True, text=True, timeout=TIMEOUT_S)
    assert r.returncode == 0 and r.stdout == extra, r.stderr
