"""A client of the model server in this process: the real server (`tests.integration.model_server.conftest.serve`)
on tests/config.yaml, and a settings file in use for the module that has the providers of tests/config.yaml (so the
server keeps serving its models) plus `SERVER`, a provider of kind `openai` at the server's `/v1`, with every task
on a model of `SERVER`."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.integration.model_server.conftest import Running, serve
from tests.settings_env import TEST_CONFIG, config_sections, use_settings, write_config

# The client's provider of the model server.
SERVER = "srv"


@dataclass
class Client:
    """The running server and the settings file of its client."""

    running: Running
    config: Path


def client_id(task: str) -> str:
    """The client's model id of the model of `task` in tests/config.yaml, on `SERVER`: the server's ids are the
    tasks' ids, `ollama:<tag>` for an Ollama model (the server's provider of kind `ollama` is named `ollama`) and
    `<provider>:<model>` for a local one."""
    return f"{SERVER}:{config_sections()['tasks'][task]}"


def client_sections(url: str) -> dict:
    """The sections of tests/config.yaml with `SERVER` at `url` (`/v1` of the server) and every task on it."""
    sections = config_sections(TEST_CONFIG)
    sections["providers"][SERVER] = {"kind": "openai", "base_url": f"{url}/v1"}
    sections["tasks"] = {task: client_id(task) for task in sections["tasks"]}
    return sections


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> Iterator[Client]:
    """The server of TEST_CONFIG, and the client's settings file (`client_sections`) in use for the module."""
    with serve(TEST_CONFIG) as running:
        path = write_config(tmp_path_factory.mktemp("client") / "config.yaml", **client_sections(running.url))
        with use_settings(path):
            yield Client(running, path)
