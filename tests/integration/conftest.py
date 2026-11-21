"""After each integration test, the test process drops the local models it loaded and releases their lock, so a
later child process that loads a local model does not wait for the test process to exit. The tiny Fish checkpoint
of the `fish` provider of tests/config.yaml (`tiny_fish_folder`) and the tiny ACE-Step pipeline of the `music` task
(`tiny_ace_step_folder`) are written to their folders when missing."""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

import pytest

from tests import tiny_ace_step, tiny_fish
from tests.settings_env import MODELS_CONFIG, kind_entry, model_entry
from tests.tiny_folder import built


@pytest.fixture(autouse=True)
def _unload_local_models():
    """Call `ai_models.local.unload()` after the test when the test process imported `ai_models.local`."""
    yield
    if (local := sys.modules.get("ai_models.local")) is not None:
        local.unload()


@pytest.fixture(scope="session")
def tiny_fish_folder() -> Path:
    """The folder `repo` of the fish model of TEST_CONFIG, built with `tiny_fish.build` from the Drama 3 repository
    of the fish model of MODELS_CONFIG when missing."""
    repo = kind_entry("fish", MODELS_CONFIG)["repo"]
    return built(Path(kind_entry("fish")["repo"]), partial(tiny_fish.build, repo=repo))


@pytest.fixture(scope="session")
def tiny_ace_step_folder() -> Path:
    """The folder `repo` of the `music` model of TEST_CONFIG, built with `tiny_ace_step.build` when missing."""
    return built(Path(model_entry("music")["repo"]), tiny_ace_step.build)
