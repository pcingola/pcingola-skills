"""The tiny ACE-Step pipeline of the `music` task of tests/config.yaml, written to its folder when missing."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from tests import tiny_ace_step
from tests.settings_env import model_entry


@pytest.fixture(scope="session")
def tiny_ace_step_folder() -> Path:
    """The folder `repo` of the `music` model of TEST_CONFIG, built with `tiny_ace_step.build` when missing. The
    pipeline is written to a temporary folder beside it and renamed, so an interrupted build leaves no partial
    folder."""
    folder = Path(model_entry("music")["repo"])
    if not folder.is_dir():
        folder.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f"{folder.name}-", dir=folder.parent))
        try:
            tiny_ace_step.build(tmp).rename(folder)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return folder
