"""A config file per test, set with `config.use`."""

from __future__ import annotations

import pytest
import yaml

from ai_models import config


@pytest.fixture
def write_config(tmp_path):
    """Write a config mapping to a file and point the layer at it."""
    path = tmp_path / "config.yaml"

    def write(data: dict) -> None:
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        config.use(path)

    yield write
    config.use(None)

