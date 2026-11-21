"""The tests that need an NVIDIA GPU (CUDA): Fish Audio Drama 3 through fish-speech, which runs only there, and the
GPU memory checks of `ai_models.local`. `scripts/tests.sh cuda` runs them; `unit`, `integration` and `all` never
collect them. The tiny Fish checkpoint of the `fish` provider of tests/config.yaml (`tiny_fish_folder`) is built
when missing, from the Drama 3 repository of tests/models/config.yaml. The model server fixtures come from
tests/integration/model_server/conftest.py."""

from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

from tests import tiny_fish
from tests.integration.conftest import _unload_local_models  # noqa: F401 (autouse fixture)
from tests.integration.model_server.conftest import running  # noqa: F401 (fixture)
from tests.settings_env import MODELS_CONFIG, kind_entry
from tests.tiny_folder import built


@pytest.fixture(scope="session")
def tiny_fish_folder() -> Path:
    """The folder `repo` of the fish model of TEST_CONFIG, built with `tiny_fish.build` from the Drama 3 repository
    of the fish model of MODELS_CONFIG when missing."""
    repo = kind_entry("fish", MODELS_CONFIG)["repo"]
    return built(Path(kind_entry("fish")["repo"]), partial(tiny_fish.build, repo=repo))
