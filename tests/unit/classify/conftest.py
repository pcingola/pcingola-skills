from pathlib import Path

import pytest

from tests.settings_env import write_config


@pytest.fixture
def chat_config(tmp_path) -> Path:
    """A `config.yaml` whose `tasks.chat` routes to an Ollama model id that no test calls, with no `tasks.system1`
    and no user settings."""
    return write_config(tmp_path / "config.yaml", providers={"ollama": {"kind": "ollama"}}, tasks={"chat": "ollama:x"})
