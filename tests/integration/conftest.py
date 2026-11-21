"""After each integration test, the test process drops the local models it loaded and releases their lock, so a
later child process that loads a local model does not wait for the test process to exit. The tiny ACE-Step
pipeline of the `music` task (`tiny_ace_step_folder`) is written to its folder when missing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests import tiny_ace_step
from tests.settings_env import model_entry
from tests.tiny_folder import built


@pytest.fixture(autouse=True)
def _unload_local_models():
    """Call `ai_models.local.unload()` after the test when the test process imported `ai_models.local`."""
    yield
    if (local := sys.modules.get("ai_models.local")) is not None:
        local.unload()


@pytest.fixture(scope="session")
def tiny_ace_step_folder() -> Path:
    """The folder `repo` of the `music` model of TEST_CONFIG, built with `tiny_ace_step.build` when missing."""
    return built(Path(model_entry("music")["repo"]), tiny_ace_step.build)
