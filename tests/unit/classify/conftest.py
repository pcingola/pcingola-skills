import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

import classify_tool

SCRIPTS = str(Path(classify_tool.__file__).resolve().parents[1])

OLLAMA = "http://localhost:11434"
# Small local models of the tests: a System-1 model and a chat model.
SYSTEM1_MODEL = "d3:4b"
CHAT_MODEL = "phi4-mini"


def pulled() -> set[str]:
    """The models the local Ollama server holds, with and without `:latest`; empty when it is down."""
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
            names = [m["name"] for m in json.load(r)["models"]]
    except OSError:
        return set()
    return {*names, *(n.removesuffix(":latest") for n in names)}


def require(model: str) -> None:
    assert model in pulled(), f"Ollama at {OLLAMA} does not hold {model}; run `ollama pull {model}`"


@pytest.fixture
def models_env(tmp_path) -> dict[str, str]:
    """The environment of a CLI subprocess with a `config.yaml` of the local Ollama
    (`models.system1` SYSTEM1_MODEL, `models.chat` CHAT_MODEL) and no user settings."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"providers:\n  ollama: {{kind: ollama, base_url: {OLLAMA}/v1}}\n"
                   f"models:\n  system1: ollama:{SYSTEM1_MODEL}\n  chat: ollama:{CHAT_MODEL}\n")
    return {**os.environ, "SKILLS_CONFIG": str(cfg), "HOME": str(tmp_path / "home"),
            "CLAUDE_PLUGIN_DATA": str(tmp_path / "plugin-data"),
            "PYTHONPATH": os.pathsep.join([SCRIPTS, os.environ.get("PYTHONPATH", "")])}


def run(argv: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    """`python -m classify_tool <argv>` in a subprocess with `env`."""
    return subprocess.run([sys.executable, "-m", "classify_tool", *argv], env=env, capture_output=True, text=True,
                          timeout=300)
