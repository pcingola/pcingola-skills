"""Every unit test reads an explicit config: the settings file of the test process is a missing file until a test
writes its own, so no in-process test reads the user's config.yaml."""

from __future__ import annotations

import plugin_settings
import pytest


@pytest.fixture(autouse=True)
def _no_user_config(tmp_path):
    """Point `plugin_settings` at a missing file in the test's temporary directory; reset after the test."""
    plugin_settings.use(tmp_path / "no-config.yaml")
    yield
    plugin_settings.use(None)
