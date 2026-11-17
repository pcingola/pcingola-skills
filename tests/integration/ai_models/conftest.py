"""The tiny Fish checkpoint of the `fish` provider of tests/config.yaml, written to its folder when missing."""

from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

from tests import tiny_fish
from tests.settings_env import MODELS_CONFIG, kind_entry
from tests.tiny_folder import built


@pytest.fixture(scope="session")
def tiny_fish_folder() -> Path:
    """The folder `repo` of the fish model of TEST_CONFIG, built with `tiny_fish.build` from the Drama 3 repository
    of the fish model of MODELS_CONFIG when missing."""
    repo = kind_entry("fish", MODELS_CONFIG)["repo"]
    return built(Path(kind_entry("fish")["repo"]), partial(tiny_fish.build, repo=repo))
