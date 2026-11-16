import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

import second_opinion_tool

OLLAMA = "http://localhost:11434"
CHAT_MODEL = "phi4-mini"
SCRIPTS = str(Path(second_opinion_tool.__file__).resolve().parents[1])


def require(model: str) -> None:
    """Fail unless the local Ollama server holds `model`."""
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
            names = {m["name"].removesuffix(":latest") for m in json.load(r)["models"]}
    except OSError:
        names = set()
    assert model in names, f"Ollama at {OLLAMA} does not hold {model}; run `ollama pull {model}`"


@pytest.fixture
def models_env(tmp_path) -> dict[str, str]:
    """The environment of a CLI subprocess with a `config.yaml` of the local Ollama (`tasks.chat`
    CHAT_MODEL) and no user settings."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"providers:\n  ollama: {{kind: ollama, base_url: {OLLAMA}/v1}}\n"
                   f"tasks:\n  chat: ollama:{CHAT_MODEL}\n  vision: ollama:gemma4:31b\n")
    return {**os.environ, "SKILLS_CONFIG": str(cfg), "HOME": str(tmp_path / "home"),
            "CLAUDE_PLUGIN_DATA": str(tmp_path / "plugin-data"),
            "PYTHONPATH": os.pathsep.join([SCRIPTS, os.environ.get("PYTHONPATH", "")])}


def run(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    """`python -m second_opinion_tool <argv>` in a subprocess with `env`."""
    return subprocess.run([sys.executable, "-m", "second_opinion_tool", *argv], env=env, capture_output=True,
                          text=True, timeout=300)
