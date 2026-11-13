"""A config file per test, set with `config.use`."""

from __future__ import annotations

import json
import urllib.request

import pytest
import yaml

from ai_models import config

OLLAMA = "http://localhost:11434"


@pytest.fixture
def write_config(tmp_path):
    """Write a config mapping to a file and point the layer at it."""
    path = tmp_path / "config.yaml"

    def write(data: dict) -> None:
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        config.use(path)

    yield write
    config.use(None)


def ollama_models() -> set[str]:
    """The tags Ollama on this machine holds; empty when it does not answer."""
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
            tags = json.load(r)["models"]
    except (OSError, KeyError, ValueError):
        return set()
    return {m["name"] for m in tags}


def require_ollama(*tags: str) -> None:
    """Fail the test when Ollama does not answer or lacks one of `tags`."""
    held = ollama_models()
    if not held:
        pytest.fail(f"Ollama does not answer at {OLLAMA}; start it")
    missing = [t for t in tags if t not in held and f"{t}:latest" not in held]
    if missing:
        pytest.fail(f"Ollama at {OLLAMA} lacks {', '.join(missing)}: run ollama pull {' '.join(missing)}")


def require_gpu() -> None:
    """Fail the test when torch sees neither CUDA nor MPS."""
    import torch

    if not (torch.cuda.is_available() or torch.backends.mps.is_available()):
        pytest.fail(f"local diffusers models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")
