"""The `critic` command: the film critic's model (short-video SKILL.md, Commands and step 9)."""
from __future__ import annotations

import subprocess
import sys

from tests.settings_env import write_config
from tests.subproc import child_env


def _critic(project, config) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "short_video_tool", "critic", "-p", str(project)],
                          capture_output=True, text=True, env=child_env(SKILLS_CONFIG=str(config)), timeout=25)


def test_critic_model(tmp_path):
    """`critic` prints task `film_critic` of config.yaml; a project's `critic.model` replaces it, `critic.model: null`
    prints `off`, and a config without the task is a one-line error. Guards where the film critic's model comes
    from."""
    config = write_config(tmp_path / "config.yaml", providers={"g": {"kind": "google", "api_key": "k"}},
                          tasks={"film_critic": "g:gemini-x"})
    project = tmp_path / "film"
    project.mkdir()
    done = _critic(project, config)
    assert done.returncode == 0 and done.stdout.strip() == "g:gemini-x", done.stderr
    (project / "settings.yaml").write_text("critic: {model: g:gemini-y}\n")
    assert _critic(project, config).stdout.strip() == "g:gemini-y"
    (project / "settings.yaml").write_text("critic: {model: null}\n")
    assert _critic(project, config).stdout.strip() == "off"
    (project / "settings.yaml").unlink()
    done = _critic(project, write_config(tmp_path / "empty.yaml", providers={}, tasks={}))
    assert done.returncode == 1 and "film_critic" in done.stderr and "Traceback" not in done.stderr
