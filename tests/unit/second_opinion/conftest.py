import subprocess

import pytest

from tests.settings_env import write_config
from tests.subproc import child_env, run_module


@pytest.fixture
def cli_env(tmp_path) -> dict[str, str]:
    """The environment of a CLI subprocess with a `config.yaml` whose `tasks.chat` and `tasks.vision` route to
    Ollama model ids that no test calls, and no user settings."""
    cfg = write_config(tmp_path / "config.yaml", providers={"ollama": {"kind": "ollama"}},
                       tasks={"chat": "ollama:c", "vision": "ollama:v"})
    return child_env(SKILLS_CONFIG=str(cfg))


def run(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    """`python -m second_opinion_tool <argv>` in a subprocess with `env`."""
    return run_module("second_opinion_tool", argv, env)
