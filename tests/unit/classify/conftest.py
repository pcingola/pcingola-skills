import subprocess

import pytest

from tests.settings_env import write_config
from tests.subproc import child_env, run_module


@pytest.fixture
def cli_env(tmp_path) -> dict[str, str]:
    """The environment of a CLI subprocess with a `config.yaml` whose `tasks.chat` routes to an Ollama model id
    that no test calls, and no user settings."""
    cfg = write_config(tmp_path / "config.yaml", providers={"ollama": {"kind": "ollama"}}, tasks={"chat": "ollama:x"})
    return child_env(SKILLS_CONFIG=str(cfg))


def run(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    """`python -m classify_tool <argv>` in a subprocess with `env`."""
    return run_module("classify_tool", argv, env)
