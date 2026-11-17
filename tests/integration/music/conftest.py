"""The tiny ACE-Step pipeline of the `music` task of tests/config.yaml, written to its folder when missing."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import tiny_ace_step
from tests.settings_env import model_entry
from tests.tiny_folder import built


@pytest.fixture(scope="session")
def tiny_ace_step_folder() -> Path:
    """The folder `repo` of the `music` model of TEST_CONFIG, built with `tiny_ace_step.build` when missing."""
    return built(Path(model_entry("music")["repo"]), tiny_ace_step.build)
