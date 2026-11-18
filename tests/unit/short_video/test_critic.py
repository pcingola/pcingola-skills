"""The film critic's model: `settings.critic_model` and the `critic` command (short-video SKILL.md, Commands and
step 9)."""
from __future__ import annotations

import pytest
from ai_models.errors import AIModelsError

from short_video_tool import settings
from tests.integration.short_video import cli
from tests.settings_env import use_settings, write_config


@pytest.fixture
def film(tmp_path):
    """A project folder `film`, and a config.yaml whose task `film_critic` is `g:gemini-x`, applied in this process;
    the skill's default settings are read again after the test."""
    project = tmp_path / "film"
    project.mkdir()
    config = write_config(tmp_path / "config.yaml", providers={"g": {"kind": "google", "api_key": "k"}},
                          tasks={"film_critic": "g:gemini-x"})
    with use_settings(config):
        yield project
    settings.use_project(None)


def test_critic_model(film, tmp_path):
    """critic_model is task `film_critic` of config.yaml; a project's `critic.model` replaces it, `critic.model:
    null` is None (the critic is off), and a config without the task raises AIModelsError naming the task. Guards
    where the film critic's model comes from."""
    settings.use_project(film)
    assert settings.critic_model() == "g:gemini-x"
    (film / "settings.yaml").write_text("critic: {model: g:gemini-y}\n")
    settings.use_project(film)
    assert settings.critic_model() == "g:gemini-y"
    (film / "settings.yaml").write_text("critic: {model: null}\n")
    settings.use_project(film)
    assert settings.critic_model() is None
    (film / "settings.yaml").unlink()
    settings.use_project(film)
    with use_settings(write_config(tmp_path / "empty.yaml", providers={}, tasks={})):
        with pytest.raises(AIModelsError, match="film_critic"):
            settings.critic_model()


def test_cli_critic(film, tmp_path):
    """`critic -p` prints the model of the project in -p, `off` when `critic.model` is null, and a config without
    task `film_critic` is a one-line error with exit code 1. Guards the output step 9 of SKILL.md reads."""
    done = cli("critic", "-p", str(film))
    assert done.returncode == 0 and done.stdout.strip() == "g:gemini-x", done.stderr
    (film / "settings.yaml").write_text("critic: {model: g:gemini-y}\n")
    assert cli("critic", "-p", str(film)).stdout.strip() == "g:gemini-y"
    (film / "settings.yaml").write_text("critic: {model: null}\n")
    assert cli("critic", "-p", str(film)).stdout.strip() == "off"
    (film / "settings.yaml").unlink()
    with use_settings(write_config(tmp_path / "empty.yaml", providers={}, tasks={})):
        done = cli("critic", "-p", str(film))
    assert done.returncode == 1 and "film_critic" in done.stderr and "Traceback" not in done.stderr
