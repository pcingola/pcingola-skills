from pathlib import Path

import pytest

from tests.settings_env import use_settings, write_config


@pytest.fixture
def cli_settings(tmp_path) -> Path:
    """A `config.yaml` whose `tasks.chat` and `tasks.vision` route to Ollama model ids that no test calls, set as
    the settings file of this process for the test (`use_settings`)."""
    cfg = write_config(tmp_path / "config.yaml", providers={"ollama": {"kind": "ollama"}},
                       tasks={"chat": "ollama:c", "vision": "ollama:v"})
    with use_settings(cfg):
        yield cfg
