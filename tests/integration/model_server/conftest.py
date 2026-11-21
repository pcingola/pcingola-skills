"""The model server running in this process: the real app (`model_server.create_app`) on uvicorn, on a free port of
127.0.0.1 in a thread, with tests/config.yaml in use, and clients of it: the `openai` SDK and httpx."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import openai
import plugin_settings
import pytest
import uvicorn

from model_server import create_app
from model_server.server import Server
from tests.settings_env import TEST_CONFIG, use_settings

START_SECONDS = 10.0
CLIENT_TIMEOUT_SECONDS = 25.0


@dataclass
class Running:
    """A running server: its base URL (`http://127.0.0.1:<port>`), its `Server` and two clients of it."""

    url: str
    server: Server
    client: openai.OpenAI
    http: httpx.Client


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def serve(settings: Path) -> Iterator[Running]:
    """The server of the settings file `settings` (its `model_server` section; the models of its providers), in a
    thread until the block ends; the settings file stays in use in this process for the block."""
    with use_settings(settings):
        app = create_app(plugin_settings.load_config().model_server)
        port = free_port()
        uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        thread = threading.Thread(target=uv.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + START_SECONDS
        while not uv.started:
            assert thread.is_alive() and time.monotonic() < deadline, "the model server did not start"
            time.sleep(0.05)
        url = f"http://127.0.0.1:{port}"
        client = openai.OpenAI(base_url=f"{url}/v1", api_key="none", timeout=CLIENT_TIMEOUT_SECONDS, max_retries=0)
        http = httpx.Client(base_url=url, timeout=CLIENT_TIMEOUT_SECONDS)
        try:
            yield Running(url, app.state.server, client, http)
        finally:
            http.close()
            client.close()
            uv.should_exit = True
            thread.join(timeout=START_SECONDS)


@pytest.fixture(scope="module")
def running() -> Iterator[Running]:
    """The server of TEST_CONFIG, for the tests of a module."""
    with serve(TEST_CONFIG) as r:
        yield r
