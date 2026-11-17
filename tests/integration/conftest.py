"""After each integration test, the test process drops the local models it loaded and releases their lock, so a
later child process that loads a local model does not wait for the test process to exit."""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _unload_local_models():
    """Call `ai_models.local.unload()` after the test when the test process imported `ai_models.local`."""
    yield
    if (local := sys.modules.get("ai_models.local")) is not None:
        local.unload()
